"""Shared types and tunable constants for the exam generator pipeline."""

from __future__ import annotations

from typing import TypedDict


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
