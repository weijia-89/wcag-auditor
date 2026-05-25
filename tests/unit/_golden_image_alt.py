"""Shared golden strings for image-alt template regression and fixture smoke.

# sdk-review F3: single source of truth so template + smoke gates cannot drift.
"""
from __future__ import annotations

GOLDEN_FIX_HTML = "<img src='image.png' alt='[Descriptive alternative text]'>"
GOLDEN_FIX_EXPLANATION = (
    "Add a descriptive alt attribute to convey the image content to screen reader users."
)
GOLDEN_RESULT_EXPLANATION = f"[RULE] {GOLDEN_FIX_EXPLANATION}"
