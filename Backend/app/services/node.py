"""LangGraph node methods for the exam generator pipeline.

Each method maps to one stage of the graph defined in ``workflow.py``:

    load_all_chapters -> split_sections -> generate_candidates
        -> dedup_candidates -> sample_to_spec -> format_paper

The methods live on a mixin so they can share instance state
(``self.num_sub_sections``, ``self._embeddings``, ``self._max_workers`` ...)
with the orchestrating ``_ExamGenerator`` class without re-wiring closures.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import time
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.config import get_chat_model
from app.logger import get_logger
from app.schemas import ExamSpec, GeneratedBatch
from app.utils import rag_pipeline

from app.services.schema import ExamState, _Candidate, _ChapterPayload
from app.services.utiles import (
    _allocate_evenly,
    _allocate_proportional,
    _build_system_prompt,
    _build_user_prompt,
    _cosine,
    _extract_json_object,
    _is_valid_mcq,
    _is_valid_short,
    _normalize_generated_batch,
    _split_into_sub_sections,
    _spread_pick,
)

logger = get_logger(__name__)


class _NodeMixin:
    """Holds the LangGraph node implementations.

    Concrete subclasses must provide the following attributes (set in
    ``_ExamGenerator.__init__``):

    - ``num_sub_sections: int``
    - ``over_generate: float``
    - ``dedup_threshold: float``
    - ``_embeddings``
    - ``_max_workers: int``
    """

    num_sub_sections: int
    over_generate: float
    dedup_threshold: float
    _embeddings: Any
    _max_workers: int

    @staticmethod
    def _log_stage_timing(stage: str, started_at: float) -> None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(f"[exam-gen] stage={stage} duration_ms={elapsed_ms:.1f}")

    @staticmethod
    def _adaptive_over_generate(total_questions: int, default_factor: float) -> float:
        # Smaller exams generally need less over-generation pressure.
        if total_questions <= 10:
            return max(1.15, min(default_factor, 1.25))
        if total_questions <= 25:
            return max(1.25, min(default_factor, 1.5))
        return max(1.4, default_factor)

    # ---- nodes ----

    def _load_all_chapters(self, state: ExamState) -> ExamState:
        t0 = time.perf_counter()
        chapters_in = state.get("chapters") or []
        loaded: list[_ChapterPayload] = []
        for ch in chapters_in:
            namespace = ch.get("vector_namespace")
            number = int(ch["chapter_number"])
            text = rag_pipeline.get_chapter_text(namespace, number) if namespace else ""
            if not text.strip():
                logger.warning(
                    f"No text loaded for chapter {number} ({ch.get('chapter_title')!r}); "
                    "it will be skipped."
                )
                continue
            loaded.append(
                {
                    "document_id": ch.get("document_id", ""),
                    "chapter_number": number,
                    "chapter_title": ch.get("chapter_title") or f"Chapter {number}",
                    "vector_namespace": namespace,
                    "text": text,
                }
            )
        if not loaded:
            self._log_stage_timing("load_all_chapters", t0)
            return {"error": "Could not load text for any requested chapter."}
        self._log_stage_timing("load_all_chapters", t0)
        return {"chapters": loaded}

    def _split_sections(self, state: ExamState) -> ExamState:
        t0 = time.perf_counter()
        if state.get("error"):
            self._log_stage_timing("split_sections", t0)
            return {}
        updated: list[_ChapterPayload] = []
        for ch in state["chapters"]:
            subs = _split_into_sub_sections(ch["text"], self.num_sub_sections)
            if not subs:
                logger.warning(
                    f"Chapter {ch['chapter_number']} produced no sub-sections, skipping"
                )
                continue
            updated.append({**ch, "sub_sections": subs})
        if not updated:
            self._log_stage_timing("split_sections", t0)
            return {"error": "Chapter text was empty after splitting."}
        logger.info(
            "Split chapters: "
            + ", ".join(
                f"ch{c['chapter_number']}={len(c.get('sub_sections') or [])}" for c in updated
            )
        )
        self._log_stage_timing("split_sections", t0)
        return {"chapters": updated}

    def _generate_candidates(self, state: ExamState) -> ExamState:
        t0 = time.perf_counter()
        if state.get("error"):
            self._log_stage_timing("generate_candidates", t0)
            return {}

        spec = ExamSpec.model_validate(state["spec"])
        book = state.get("book") or {}
        chapters = state["chapters"]

        target_mcq = sum(s.count for s in spec.sections if s.type == "mcq")
        target_short = sum(s.count for s in spec.sections if s.type == "short_answer")
        short_marks = next(
            (s.marks_each for s in spec.sections if s.type == "short_answer"),
            2,
        )
        if target_mcq == 0 and target_short == 0:
            self._log_stage_timing("generate_candidates", t0)
            return {"error": "Spec requested zero questions."}

        weights = [float(len(c["text"])) for c in chapters]
        if spec.per_chapter_distribution == "evenly_split":
            mcq_per_ch = _allocate_evenly(target_mcq, len(chapters))
            short_per_ch = _allocate_evenly(target_short, len(chapters))
        else:
            mcq_per_ch = _allocate_proportional(target_mcq, weights)
            short_per_ch = _allocate_proportional(target_short, weights)

        try:
            base_llm = get_chat_model()
            llm = base_llm.with_structured_output(GeneratedBatch)
        except Exception as e:
            logger.exception("Could not bind structured output to chat model")
            self._log_stage_timing("generate_candidates", t0)
            return {"error": f"LLM does not support structured output: {e}"}

        stats = {
            "prompts": 0,
            "structured_success": 0,
            "structured_validation_fail": 0,
            "structured_other_fail": 0,
            "fallback_success": 0,
            "fallback_fail": 0,
            "recovery_rounds": 0,
        }

        def _count_by_type(items: list[_Candidate]) -> tuple[int, int]:
            mcq_count = sum(1 for item in items if item["type"] == "mcq")
            short_count = sum(1 for item in items if item["type"] == "short_answer")
            return mcq_count, short_count

        def _run_generation_round(
            round_mcq_per_ch: list[int],
            round_short_per_ch: list[int],
            factor: float,
        ) -> list[_Candidate]:
            def _invoke_for_subsection(
                ch: _ChapterPayload,
                s_idx: int,
                section_text: str,
                mcq_per_sub: int,
                short_per_sub: int,
                sys_msg: SystemMessage,
            ) -> tuple[list[_Candidate], dict[str, int]]:
                local_stats = {
                    "prompts": 1,
                    "structured_success": 0,
                    "structured_validation_fail": 0,
                    "structured_other_fail": 0,
                    "fallback_success": 0,
                    "fallback_fail": 0,
                }
                generated_local: list[_Candidate] = []
                user_msg = HumanMessage(
                    content=_build_user_prompt(
                        section_text=section_text,
                        n_mcq=mcq_per_sub,
                        n_short=short_per_sub,
                        short_marks=short_marks,
                    )
                )

                batch: Optional[GeneratedBatch] = None
                try:
                    batch = llm.invoke([sys_msg, user_msg])
                    local_stats["structured_success"] += 1
                except ValidationError as e:
                    local_stats["structured_validation_fail"] += 1
                    logger.warning(
                        f"Structured parse failed for ch{ch['chapter_number']} "
                        f"section {s_idx}: {type(e).__name__}: {e}. "
                        "Retrying with tolerant JSON normalization."
                    )
                except Exception as e:
                    local_stats["structured_other_fail"] += 1
                    logger.warning(
                        f"Structured generation call failed for ch{ch['chapter_number']} "
                        f"section {s_idx}: {type(e).__name__}: {e}. "
                        "Skipping fallback to avoid duplicate failed calls."
                    )
                    return generated_local, local_stats

                if batch is None:
                    try:
                        raw_response = base_llm.invoke([sys_msg, user_msg])
                        raw_content = getattr(raw_response, "content", str(raw_response))
                        if not isinstance(raw_content, str):
                            raw_content = str(raw_content)
                        payload = _extract_json_object(raw_content)
                        if payload is None:
                            raise ValueError("No JSON object found in fallback model output")
                        batch = _normalize_generated_batch(payload, short_marks=short_marks)
                        local_stats["fallback_success"] += 1
                    except Exception as fallback_error:
                        local_stats["fallback_fail"] += 1
                        logger.warning(
                            f"Fallback parse failed for ch{ch['chapter_number']} "
                            f"section {s_idx}: {type(fallback_error).__name__}: {fallback_error}"
                        )
                        return generated_local, local_stats

                if not batch.mcqs and not batch.short_answers:
                    logger.info(
                        f"ch{ch['chapter_number']} section {s_idx}: model returned "
                        "no usable items after normalization"
                    )
                    return generated_local, local_stats

                for mcq in (batch.mcqs[:mcq_per_sub] if mcq_per_sub else []):
                    if not _is_valid_mcq(mcq):
                        continue
                    generated_local.append(
                        {
                            "type": "mcq",
                            "chapter_number": int(ch["chapter_number"]),
                            "chapter_title": ch["chapter_title"],
                            "section_index": s_idx,
                            "payload": mcq.model_dump(),
                            "target_section_index": -1,
                        }
                    )

                for sa in (batch.short_answers[:short_per_sub] if short_per_sub else []):
                    if not _is_valid_short(sa):
                        continue
                    generated_local.append(
                        {
                            "type": "short_answer",
                            "chapter_number": int(ch["chapter_number"]),
                            "chapter_title": ch["chapter_title"],
                            "section_index": s_idx,
                            "payload": sa.model_dump(),
                            "target_section_index": -1,
                        }
                    )
                return generated_local, local_stats

            generated: list[_Candidate] = []
            futures = []
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                for ch_idx, ch in enumerate(chapters):
                    sub_sections = ch.get("sub_sections") or []
                    k = max(1, len(sub_sections))
                    mcq_ch_target = round_mcq_per_ch[ch_idx]
                    short_ch_target = round_short_per_ch[ch_idx]
                    mcq_per_sub = math.ceil(mcq_ch_target * factor / k) if mcq_ch_target else 0
                    short_per_sub = (
                        math.ceil(short_ch_target * factor / k) if short_ch_target else 0
                    )
                    if mcq_per_sub == 0 and short_per_sub == 0:
                        continue

                    sys_msg = SystemMessage(
                        content=_build_system_prompt(spec, book, ch["chapter_title"])
                    )
                    for s_idx, section_text in enumerate(sub_sections):
                        futures.append(
                            executor.submit(
                                _invoke_for_subsection,
                                ch,
                                s_idx,
                                section_text,
                                mcq_per_sub,
                                short_per_sub,
                                sys_msg,
                            )
                        )

                for fut in as_completed(futures):
                    generated_local, local_stats = fut.result()
                    generated.extend(generated_local)
                    for key, value in local_stats.items():
                        stats[key] += int(value)

            generated.sort(
                key=lambda c: (
                    int(c["chapter_number"]),
                    int(c.get("section_index", 0)),
                    0 if c["type"] == "mcq" else 1,
                )
            )
            return generated

        total_requested_questions = target_mcq + target_short
        initial_factor = self._adaptive_over_generate(
            total_requested_questions, self.over_generate
        )
        candidates = _run_generation_round(mcq_per_ch, short_per_ch, initial_factor)
        max_recovery_rounds = 3
        for recovery_round in range(1, max_recovery_rounds + 1):
            mcq_generated, short_generated = _count_by_type(candidates)
            mcq_missing = max(0, target_mcq - mcq_generated)
            short_missing = max(0, target_short - short_generated)
            if mcq_missing == 0 and short_missing == 0:
                break
            stats["recovery_rounds"] += 1

            logger.info(
                f"Generation deficit after round {recovery_round - 1}: "
                f"mcq_missing={mcq_missing}, short_missing={short_missing}; "
                f"running recovery round {recovery_round}"
            )
            if spec.per_chapter_distribution == "evenly_split":
                recovery_mcq_per_ch = _allocate_evenly(mcq_missing, len(chapters))
                recovery_short_per_ch = _allocate_evenly(short_missing, len(chapters))
            else:
                recovery_mcq_per_ch = _allocate_proportional(mcq_missing, weights)
                recovery_short_per_ch = _allocate_proportional(short_missing, weights)

            # Increase request pressure each round so large requests are more likely
            # to be satisfied in a single API call.
            factor = max(1.0, initial_factor) + (0.6 * recovery_round)
            recovery_candidates = _run_generation_round(
                recovery_mcq_per_ch,
                recovery_short_per_ch,
                factor,
            )
            if not recovery_candidates:
                break
            candidates.extend(recovery_candidates)

        mcq_generated, short_generated = _count_by_type(candidates)
        logger.info(
            "[exam-gen] generation_stats "
            f"prompts={stats['prompts']} "
            f"structured_success={stats['structured_success']} "
            f"structured_validation_fail={stats['structured_validation_fail']} "
            f"structured_other_fail={stats['structured_other_fail']} "
            f"fallback_success={stats['fallback_success']} "
            f"fallback_fail={stats['fallback_fail']} "
            f"recovery_rounds={stats['recovery_rounds']} "
            f"candidates_total={len(candidates)} "
            f"candidates_mcq={mcq_generated} "
            f"candidates_short={short_generated}"
        )
        logger.info(f"Generated {len(candidates)} raw candidate(s) before dedup")
        if not candidates:
            self._log_stage_timing("generate_candidates", t0)
            return {"error": "LLM produced no usable candidates."}
        self._log_stage_timing("generate_candidates", t0)
        return {"candidates": candidates}

    def _dedup_candidates(self, state: ExamState) -> ExamState:
        t0 = time.perf_counter()
        if state.get("error"):
            self._log_stage_timing("dedup_candidates", t0)
            return {}

        candidates = state["candidates"]
        if len(candidates) < 2:
            self._log_stage_timing("dedup_candidates", t0)
            return {"candidates": candidates}

        try:
            texts = [c["payload"]["question"] for c in candidates]
            vectors = self._embeddings.embed_documents(texts)
        except Exception as e:
            logger.warning(f"Embedding failed during dedup, skipping: {e}")
            self._log_stage_timing("dedup_candidates", t0)
            return {"candidates": candidates}

        kept: list[_Candidate] = []
        kept_vecs: list[list[float]] = []
        for cand, vec in zip(candidates, vectors):
            if any(_cosine(vec, kv) >= self.dedup_threshold for kv in kept_vecs):
                continue
            kept.append(cand)
            kept_vecs.append(vec)

        logger.info(
            f"Dedup kept {len(kept)} of {len(candidates)} candidates "
            f"(threshold={self.dedup_threshold})"
        )
        # Keep strict quality by default, but avoid over-pruning that prevents
        # satisfying the requested exam shape.
        try:
            spec = ExamSpec.model_validate(state["spec"])
            required_mcq = sum(s.count for s in spec.sections if s.type == "mcq")
            required_short = sum(
                s.count for s in spec.sections if s.type == "short_answer"
            )
            kept_mcq = sum(1 for c in kept if c["type"] == "mcq")
            kept_short = sum(1 for c in kept if c["type"] == "short_answer")
            if kept_mcq < required_mcq or kept_short < required_short:
                raw_mcq = sum(1 for c in candidates if c["type"] == "mcq")
                raw_short = sum(1 for c in candidates if c["type"] == "short_answer")
                logger.info(
                    "Dedup reduced candidates below requested counts; "
                    f"using raw pool (raw mcq={raw_mcq}, raw short={raw_short}, "
                    f"kept mcq={kept_mcq}, kept short={kept_short})"
                )
                self._log_stage_timing("dedup_candidates", t0)
                return {"candidates": candidates}
        except Exception:
            # If spec parsing fails here, keep existing dedup behavior.
            pass
        self._log_stage_timing("dedup_candidates", t0)
        return {"candidates": kept}

    def _sample_to_spec(self, state: ExamState) -> ExamState:
        t0 = time.perf_counter()
        if state.get("error"):
            self._log_stage_timing("sample_to_spec", t0)
            return {}

        spec = ExamSpec.model_validate(state["spec"])
        candidates = state["candidates"]

        by_type: dict[str, list[_Candidate]] = {"mcq": [], "short_answer": []}
        for c in candidates:
            by_type.setdefault(c["type"], []).append(c)

        selected: list[_Candidate] = []
        for section_idx, section in enumerate(spec.sections):
            pool = by_type.get(section.type, [])
            picked = _spread_pick(pool, section.count)
            if len(picked) < section.count:
                self._log_stage_timing("sample_to_spec", t0)
                return {
                    "error": (
                        f"Could not generate enough {section.type} questions. "
                        f"Requested {section.count}, generated {len(picked)}. "
                        "Try processed chapters with more content or reduce question counts."
                    )
                }
            picked_ids = {id(item) for item in picked}
            by_type[section.type] = [
                item for item in by_type.get(section.type, []) if id(item) not in picked_ids
            ]
            for cand in picked:
                marked = {
                    **cand,
                    "payload": {**cand["payload"], "marks": section.marks_each},
                    "target_section_index": section_idx,
                }
                selected.append(marked)  # type: ignore[arg-type]

        if not selected:
            self._log_stage_timing("sample_to_spec", t0)
            return {"error": "No questions could be sampled to match the spec."}
        self._log_stage_timing("sample_to_spec", t0)
        return {"selected": selected}

    def _format_paper(self, state: ExamState) -> ExamState:
        t0 = time.perf_counter()
        if state.get("error"):
            self._log_stage_timing("format_paper", t0)
            return {}

        spec = ExamSpec.model_validate(state["spec"])
        selected = state["selected"]

        paper_sections: list[dict[str, Any]] = []
        q_no = 1
        total_marks = 0

        for section_idx, section in enumerate(spec.sections):
            picks = [
                c
                for c in selected
                if c["type"] == section.type
                and int(c.get("target_section_index", -1)) == section_idx
            ][: section.count]

            questions: list[dict[str, Any]] = []
            for c in picks:
                payload = dict(c["payload"])
                payload["q_no"] = q_no
                payload["chapter_number"] = c["chapter_number"]
                payload["chapter_title"] = c["chapter_title"]
                questions.append(payload)
                q_no += 1
                total_marks += section.marks_each

            label = "MCQ" if section.type == "mcq" else "Short Answer"
            paper_sections.append(
                {
                    "title": (
                        f"Section: {label} "
                        f"({section.count} x {section.marks_each} mark"
                        f"{'s' if section.marks_each > 1 else ''} = "
                        f"{section.count * section.marks_each} marks)"
                    ),
                    "type": section.type,
                    "marks_each": section.marks_each,
                    "questions": questions,
                }
            )

        chapter_index = [
            {"number": ch["chapter_number"], "title": ch["chapter_title"]}
            for ch in (state.get("chapters") or [])
        ]

        paper = {
            "book": state.get("book") or {},
            "chapters": chapter_index,
            "difficulty": spec.difficulty,
            "language": spec.language,
            "total_marks": total_marks,
            "sections": paper_sections,
        }
        self._log_stage_timing("format_paper", t0)
        return {"final_paper": paper}
