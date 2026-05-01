"""Public entry point for the exam-paper generator.

The implementation now lives in dedicated modules:

- ``schema.py``   - shared TypedDicts and tunable constants
- ``utiles.py``   - pure helpers (text splitting, prompts, JSON parsing, ...)
- ``node.py``     - LangGraph node methods (the six pipeline stages)
- ``workflow.py`` - graph wiring + ``_ExamGenerator`` orchestrator

This module preserves the historical import path used by the HTTP layer:

    from app.services.exam_generator import get_exam_generator
"""

from __future__ import annotations

from app.services.workflow import (
    _ExamGenerator,
    exam_generator,
    get_exam_generator,
)

__all__ = ["_ExamGenerator", "exam_generator", "get_exam_generator"]
