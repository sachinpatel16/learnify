"""Agentic, multi-chapter exam-paper generator built on LangGraph.

Pipeline (one node per step):

    load_all_chapters -> split_sections -> generate_candidates
        -> dedup_candidates -> sample_to_spec -> format_paper

State carries a list of *chapter payloads*: text + sub-sections + per-chapter
quotas. Generation over-generates per (chapter, sub-section), then a global
embedding-based dedup runs, then sampling spreads picks across chapters
first (so a 10-MCQ paper from chapters 5 and 6 doesn't end up lopsided).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from app.config import get_chat_model, get_embeddings
from app.logger import get_logger
from app.schemas import (
    ExamSpec,
    GeneratedBatch,
    MCQ,
    ShortAnswer,
)
from app.utils import rag_pipeline

logger = get_logger(__name__)


DEFAULT_NUM_SUBSECTIONS = 3
DEFAULT_OVER_GENERATE = 1.7
DEFAULT_DEDUP_THRESHOLD = 0.85
SECTION_MIN_CHARS = 800


# ── State ────────────────────────────────────────────────────────────────────


class _ChapterPayload(TypedDict, total=False):
    document_id: str
    chapter_number: int
    chapter_title: str
    vector_namespace: str
    text: str
    sub_sections: list[str]


class _Candidate(TypedDict):
    type: str
    chapter_number: int
    chapter_title: str
    section_index: int
    payload: dict
    target_section_index: int


class ExamState(TypedDict, total=False):
    spec: dict
    book: dict
    chapters: list[_ChapterPayload]
    candidates: list[_Candidate]
    selected: list[_Candidate]
    final_paper: dict
    error: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _split_into_sub_sections(text: str, max_sections: int) -> list[str]:
    """Split chapter text into roughly equal sub-sections by length."""
    text = text.strip()
    if not text:
        return []

    n = max(1, min(max_sections, max(1, len(text) // SECTION_MIN_CHARS)))
    if n == 1:
        return [text]

    target = math.ceil(len(text) / n)
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return [text]

    out: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for para in paragraphs:
        buf.append(para)
        buf_len += len(para) + 2
        if buf_len >= target and len(out) < n - 1:
            out.append("\n\n".join(buf))
            buf, buf_len = [], 0
    if buf:
        out.append("\n\n".join(buf))
    return [s for s in out if s.strip()]


def _allocate_proportional(target: int, weights: list[float]) -> list[int]:
    """Distribute ``target`` integer units across N bins by weights.

    Largest-remainder rounding: every bin gets at least floor(weight share),
    leftovers go to the bins with the largest fractional remainder.
    """
    if target <= 0 or not weights:
        return [0] * len(weights)

    total = sum(weights)
    if total <= 0:
        base, rem = divmod(target, len(weights))
        out = [base] * len(weights)
        for i in range(rem):
            out[i] += 1
        return out

    raw = [target * (w / total) for w in weights]
    floored = [int(x) for x in raw]
    leftover = target - sum(floored)
    fractions = sorted(
        ((raw[i] - floored[i], i) for i in range(len(weights))),
        key=lambda p: p[0],
        reverse=True,
    )
    for _, i in fractions[:leftover]:
        floored[i] += 1
    return floored


def _allocate_evenly(target: int, n: int) -> list[int]:
    if target <= 0 or n <= 0:
        return [0] * max(n, 0)
    base, rem = divmod(target, n)
    out = [base] * n
    for i in range(rem):
        out[i] += 1
    return out


def _build_system_prompt(spec: ExamSpec, book: dict, chapter_title: str) -> str:
    standard = spec.standard or book.get("standard") or "general"
    subject = spec.subject or book.get("subject") or "general"
    board = book.get("board")
    where = f"Class {standard}" + (f" {board}" if board else "")
    return (
        f"You are an experienced exam paper setter for {where} {subject}, "
        f"working in {spec.language}.\n\n"
        f"Chapter: {chapter_title}\n"
        f"Difficulty: {spec.difficulty}\n\n"
        "Rules for every question:\n"
        "1. Must be answerable strictly from the source text below.\n"
        "2. Calibrate vocabulary and complexity to the stated class level.\n"
        "3. For MCQs: provide exactly 4 options of similar length and form; "
        "exactly one option must be defensibly correct; distractors must be "
        "plausible misconceptions but clearly wrong on careful reading.\n"
        "4. For short-answer questions: keep them open enough to need 1-3 "
        "sentences but specific enough to have a single expected answer.\n"
        "5. Do not copy more than 6 consecutive words verbatim from the text "
        "(paraphrase instead).\n"
        "6. Do not produce duplicates or near-duplicates.\n"
        "7. Return JSON matching the schema exactly."
    )


def _build_user_prompt(
    section_text: str,
    n_mcq: int,
    n_short: int,
    short_marks: int,
) -> str:
    parts: list[str] = []
    if n_mcq > 0:
        parts.append(f"{n_mcq} MCQs worth 1 mark each")
    if n_short > 0:
        parts.append(f"{n_short} short-answer questions worth {short_marks} marks each")
    instruction = " and ".join(parts) if parts else "no questions"

    return (
        f"From the source text below, generate {instruction}.\n\n"
        "Return ONLY a single JSON object (no prose, no markdown fences) "
        "matching this exact shape:\n"
        "{\n"
        '  "mcqs": [\n'
        "    {\n"
        '      "question": "string",\n'
        '      "options": ["opt 1", "opt 2", "opt 3", "opt 4"],\n'
        '      "correct_index": 0,            // ZERO-BASED index of the correct option\n'
        '      "explanation": "short reason why correct_index is right",\n'
        '      "marks": 1\n'
        "    }\n"
        "  ],\n"
        '  "short_answers": [\n'
        "    {\n"
        '      "question": "string",\n'
        '      "expected_answer": "the model answer 1-3 sentences",\n'
        f'      "marks": {short_marks}\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Hard constraints:\n"
        "- Use the exact keys above. Do NOT use 'answer'. MCQs MUST include "
        '"correct_index" as an integer in [0, len(options)-1].\n'
        '- Short-answer items MUST include "expected_answer" (string).\n'
        "- Output must be valid JSON parseable by json.loads.\n\n"
        "----- SOURCE TEXT -----\n"
        f"{section_text}\n"
        "----- END SOURCE TEXT -----"
    )


def _extract_json_object(text: str) -> Optional[dict]:
    """Best-effort parse of a JSON object from model text output."""
    text = text.strip()
    if not text:
        return None

    # Strip markdown fences when present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    # Fallback: parse the first top-level JSON object slice.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _index_from_answer(options: list[str], answer: Any) -> Optional[int]:
    """Infer MCQ correct index from flexible answer formats."""
    if not options:
        return None

    if isinstance(answer, int):
        if 0 <= answer < len(options):
            return answer
        if 1 <= answer <= len(options):
            return answer - 1
        return None

    text = str(answer or "").strip()
    if not text:
        return None

    # Handle labels like "A", "B.", "(C)".
    first = text[0].upper()
    if "A" <= first <= "Z":
        candidate = ord(first) - ord("A")
        if 0 <= candidate < len(options):
            return candidate

    # Match against option text.
    lowered = text.lower()
    for idx, option in enumerate(options):
        opt = str(option).strip()
        if not opt:
            continue
        if lowered == opt.lower() or lowered in opt.lower() or opt.lower() in lowered:
            return idx
    return None


def _normalize_generated_batch(raw: dict, short_marks: int) -> GeneratedBatch:
    """Normalize flexible LLM JSON into strict GeneratedBatch schema.

    Items that cannot be repaired (e.g. MCQ with no inferable correct_index, or
    short-answer with no expected answer) are silently dropped instead of
    failing validation for the whole batch.
    """
    normalized: dict[str, list[dict]] = {"mcqs": [], "short_answers": []}

    for item in raw.get("mcqs") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        options = [str(opt).strip() for opt in (item.get("options") or []) if str(opt).strip()]
        if not question or len(options) < 2:
            continue

        correct_index = item.get("correct_index")
        if not isinstance(correct_index, int):
            correct_index = _index_from_answer(
                options,
                item.get("answer") or item.get("correct_answer") or item.get("correct_option"),
            )
        if not isinstance(correct_index, int) or not (0 <= correct_index < len(options)):
            # No reliable correct answer -> cannot use this MCQ.
            continue

        normalized["mcqs"].append(
            {
                "question": question,
                "options": options,
                "correct_index": correct_index,
                "explanation": str(item.get("explanation") or ""),
                "marks": int(item.get("marks", 1) or 1),
            }
        )

    for item in raw.get("short_answers") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        expected = (
            item.get("expected_answer")
            or item.get("answer")
            or item.get("model_answer")
        )
        expected_str = str(expected or "").strip()
        if not question or not expected_str:
            continue
        normalized["short_answers"].append(
            {
                "question": question,
                "expected_answer": expected_str,
                "marks": int(item.get("marks", short_marks) or short_marks),
            }
        )

    return GeneratedBatch.model_validate(normalized)


def _cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def _is_valid_mcq(mcq: MCQ) -> bool:
    if not mcq.question.strip():
        return False
    if len(mcq.options) < 2:
        return False
    if not (0 <= mcq.correct_index < len(mcq.options)):
        return False
    if any(not opt.strip() for opt in mcq.options):
        return False
    return True


def _is_valid_short(sa: ShortAnswer) -> bool:
    return bool(sa.question.strip() and sa.expected_answer.strip())


def _spread_pick(pool: list[_Candidate], n: int) -> list[_Candidate]:
    """Round-robin across chapters (outer); drain sub-sections in order (inner)."""
    if n <= 0 or not pool:
        return []

    by_chapter: dict[int, list[_Candidate]] = {}
    for c in pool:
        by_chapter.setdefault(int(c["chapter_number"]), []).append(c)
    for ch in by_chapter:
        by_chapter[ch].sort(key=lambda c: int(c.get("section_index", 0)))

    chapter_keys = sorted(by_chapter.keys())
    picked: list[_Candidate] = []
    while len(picked) < n:
        progressed = False
        for ch in chapter_keys:
            if by_chapter[ch]:
                picked.append(by_chapter[ch].pop(0))
                progressed = True
                if len(picked) >= n:
                    break
        if not progressed:
            break
    return picked


# ── Generator ────────────────────────────────────────────────────────────────


class _ExamGenerator:
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

    # ---- nodes ----

    def _load_all_chapters(self, state: ExamState) -> ExamState:
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
            return {"error": "Could not load text for any requested chapter."}
        return {"chapters": loaded}

    def _split_sections(self, state: ExamState) -> ExamState:
        if state.get("error"):
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
            return {"error": "Chapter text was empty after splitting."}
        logger.info(
            "Split chapters: "
            + ", ".join(
                f"ch{c['chapter_number']}={len(c.get('sub_sections') or [])}" for c in updated
            )
        )
        return {"chapters": updated}

    def _generate_candidates(self, state: ExamState) -> ExamState:
        if state.get("error"):
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
            return {"error": f"LLM does not support structured output: {e}"}

        def _count_by_type(items: list[_Candidate]) -> tuple[int, int]:
            mcq_count = sum(1 for item in items if item["type"] == "mcq")
            short_count = sum(1 for item in items if item["type"] == "short_answer")
            return mcq_count, short_count

        def _run_generation_round(
            round_mcq_per_ch: list[int],
            round_short_per_ch: list[int],
            factor: float,
        ) -> list[_Candidate]:
            generated: list[_Candidate] = []
            for ch_idx, ch in enumerate(chapters):
                sub_sections = ch.get("sub_sections") or []
                k = max(1, len(sub_sections))
                mcq_ch_target = round_mcq_per_ch[ch_idx]
                short_ch_target = round_short_per_ch[ch_idx]
                mcq_per_sub = math.ceil(mcq_ch_target * factor / k) if mcq_ch_target else 0
                short_per_sub = (
                    math.ceil(short_ch_target * factor / k) if short_ch_target else 0
                )

                sys_msg = SystemMessage(
                    content=_build_system_prompt(spec, book, ch["chapter_title"])
                )

                for s_idx, section_text in enumerate(sub_sections):
                    if mcq_per_sub == 0 and short_per_sub == 0:
                        continue
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
                    except (ValidationError, Exception) as e:
                        logger.warning(
                            f"Structured parse failed for ch{ch['chapter_number']} "
                            f"section {s_idx}: {type(e).__name__}: {e}. "
                            "Retrying with tolerant JSON normalization."
                        )

                    if batch is None:
                        try:
                            raw_response = base_llm.invoke([sys_msg, user_msg])
                            raw_content = getattr(raw_response, "content", str(raw_response))
                            if not isinstance(raw_content, str):
                                raw_content = str(raw_content)
                            payload = _extract_json_object(raw_content)
                            if payload is None:
                                raise ValueError(
                                    "No JSON object found in fallback model output"
                                )
                            batch = _normalize_generated_batch(
                                payload, short_marks=short_marks
                            )
                        except Exception as fallback_error:
                            logger.warning(
                                f"Fallback parse failed for ch{ch['chapter_number']} "
                                f"section {s_idx}: {type(fallback_error).__name__}: {fallback_error}"
                            )
                            continue

                    if not batch.mcqs and not batch.short_answers:
                        logger.info(
                            f"ch{ch['chapter_number']} section {s_idx}: model returned "
                            "no usable items after normalization"
                        )
                        continue

                    for mcq in (batch.mcqs[:mcq_per_sub] if mcq_per_sub else []):
                        if not _is_valid_mcq(mcq):
                            continue
                        generated.append(
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
                        generated.append(
                            {
                                "type": "short_answer",
                                "chapter_number": int(ch["chapter_number"]),
                                "chapter_title": ch["chapter_title"],
                                "section_index": s_idx,
                                "payload": sa.model_dump(),
                                "target_section_index": -1,
                            }
                        )
            return generated

        candidates = _run_generation_round(mcq_per_ch, short_per_ch, self.over_generate)
        max_recovery_rounds = 3
        for recovery_round in range(1, max_recovery_rounds + 1):
            mcq_generated, short_generated = _count_by_type(candidates)
            mcq_missing = max(0, target_mcq - mcq_generated)
            short_missing = max(0, target_short - short_generated)
            if mcq_missing == 0 and short_missing == 0:
                break

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
            factor = max(1.0, self.over_generate) + (0.6 * recovery_round)
            recovery_candidates = _run_generation_round(
                recovery_mcq_per_ch,
                recovery_short_per_ch,
                factor,
            )
            if not recovery_candidates:
                break
            candidates.extend(recovery_candidates)

        logger.info(f"Generated {len(candidates)} raw candidate(s) before dedup")
        if not candidates:
            return {"error": "LLM produced no usable candidates."}
        return {"candidates": candidates}

    def _dedup_candidates(self, state: ExamState) -> ExamState:
        if state.get("error"):
            return {}

        candidates = state["candidates"]
        if len(candidates) < 2:
            return {"candidates": candidates}

        try:
            texts = [c["payload"]["question"] for c in candidates]
            vectors = self._embeddings.embed_documents(texts)
        except Exception as e:
            logger.warning(f"Embedding failed during dedup, skipping: {e}")
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
                return {"candidates": candidates}
        except Exception:
            # If spec parsing fails here, keep existing dedup behavior.
            pass
        return {"candidates": kept}

    def _sample_to_spec(self, state: ExamState) -> ExamState:
        if state.get("error"):
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
            return {"error": "No questions could be sampled to match the spec."}
        return {"selected": selected}

    def _format_paper(self, state: ExamState) -> ExamState:
        if state.get("error"):
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
        return {"final_paper": paper}

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
