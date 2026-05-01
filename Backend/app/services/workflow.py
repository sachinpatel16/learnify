"""Agentic, multi-chapter exam-paper generator built on LangGraph.

Pipeline (one node per step):

    load_all_chapters -> split_sections -> generate_candidates
        -> dedup_candidates -> sample_to_spec -> format_paper

State carries a list of *chapter payloads*: text + sub-sections + per-chapter
quotas. Generation over-generates per (chapter, sub-section), then a global
embedding-based dedup runs, then sampling spreads picks across chapters
first (so a 10-MCQ paper from chapters 5 and 6 doesn't end up lopsided).

The node implementations live in ``node.py``; this module wires them into a
LangGraph ``StateGraph`` and exposes the public ``get_exam_generator()``
accessor used by the HTTP layer.
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import END, StateGraph

from app.config import EXAM_GEN_MAX_WORKERS, get_embeddings
from app.logger import get_logger
from app.schemas import ExamSpec

from app.services.node import _NodeMixin
from app.services.schema import (
    DEFAULT_DEDUP_THRESHOLD,
    DEFAULT_NUM_SUBSECTIONS,
    DEFAULT_OVER_GENERATE,
    ExamState,
)

logger = get_logger(__name__)


# ── Generator ────────────────────────────────────────────────────────────────


class _ExamGenerator(_NodeMixin):
    def __init__(
        self,
        num_sub_sections: int = DEFAULT_NUM_SUBSECTIONS,
        over_generate: float = DEFAULT_OVER_GENERATE,
        dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD,
    ) -> None:
        self.num_sub_sections = num_sub_sections
        self.over_generate = over_generate
        self.dedup_threshold = dedup_threshold
        self._embeddings = get_embeddings()
        self._graph = self._build_graph()
        self._max_workers = max(1, int(EXAM_GEN_MAX_WORKERS))

    # ---- graph wiring ----

    def _build_graph(self):
        graph = StateGraph(ExamState)
        graph.add_node("load_all_chapters", self._load_all_chapters)
        graph.add_node("split_sections", self._split_sections)
        graph.add_node("generate_candidates", self._generate_candidates)
        graph.add_node("dedup_candidates", self._dedup_candidates)
        graph.add_node("sample_to_spec", self._sample_to_spec)
        graph.add_node("format_paper", self._format_paper)

        graph.set_entry_point("load_all_chapters")
        graph.add_edge("load_all_chapters", "split_sections")
        graph.add_edge("split_sections", "generate_candidates")
        graph.add_edge("generate_candidates", "dedup_candidates")
        graph.add_edge("dedup_candidates", "sample_to_spec")
        graph.add_edge("sample_to_spec", "format_paper")
        graph.add_edge("format_paper", END)
        return graph.compile()

    # ---- public entry point ----

    def run(self, spec: ExamSpec, snapshot: dict) -> dict:
        """Execute the graph against a book + chapter snapshot.

        ``snapshot`` shape:
            {
              "book": {"id","title","standard","subject","board","language"},
              "chapters": [
                {"document_id","chapter_number","chapter_title","vector_namespace"},
                ...
              ]
            }
        """
        initial: ExamState = {
            "spec": spec.model_dump(),
            "book": snapshot.get("book") or {},
            "chapters": list(snapshot.get("chapters") or []),
        }
        try:
            final_state = self._graph.invoke(initial)
        except Exception as e:
            logger.exception("Exam generation graph failed")
            raise RuntimeError(f"Exam generation failed: {e}") from e

        if final_state.get("error"):
            raise RuntimeError(final_state["error"])

        paper = final_state.get("final_paper")
        if not paper:
            raise RuntimeError("Exam generator produced no paper.")
        return {"paper": paper, "total_marks": paper.get("total_marks", 0)}


exam_generator: Optional[_ExamGenerator] = None


def get_exam_generator() -> _ExamGenerator:
    global exam_generator
    if exam_generator is None:
        exam_generator = _ExamGenerator()
    return exam_generator
