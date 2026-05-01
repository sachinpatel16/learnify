"""Pure helpers for the exam generator: text splitting, allocation, prompt
builders, JSON parsing/normalization, similarity, validators, and sampling.

These functions hold no LangGraph state and no instance state; they are
imported by ``node.py`` (graph nodes) and ``workflow.py`` (orchestration).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Optional

from app.schemas import (
    ExamSpec,
    GeneratedBatch,
    MCQ,
    ShortAnswer,
)

from app.services.schema import SECTION_MIN_CHARS, _Candidate


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
