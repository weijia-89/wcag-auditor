from __future__ import annotations

import json
import os
import re
from typing import Protocol, runtime_checkable

from wcag_auditor.models import AuditResult, ImpactLevel, ViolationFix, ViolationInput

_SYSTEM_PROMPT = """You are an accessibility expert specializing in WCAG 2.2.
Given an accessibility violation detected by axe-core, produce a JSON fix suggestion.

Rules:
- Only reference WCAG 2.2 criteria that directly apply to the specific violation provided.
- fix_html MUST resolve the described violation and must be syntactically valid HTML.
- Do not invent violations or criteria not present in the input.
- Do not include prose, markdown fences, or any text outside the JSON object.
- Return ONLY the JSON object matching the schema exactly.
- confidence_score is your estimate of how certain the fix is correct (0.0 to 1.0).
- element_selector should be a CSS selector that uniquely identifies the element.
- fix_explanation should be a concise 1-2 sentence explanation of why this fix resolves the violation.
"""

_FIX_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "element_selector": {"type": "string"},
        "original_html": {"type": "string"},
        "fix_html": {"type": "string"},
        "fix_explanation": {"type": "string"},
        "wcag_criterion": {"type": "string"},
        "impact": {"type": "string", "enum": ["critical", "serious", "moderate", "minor"]},
        "explanation": {"type": "string"},
        "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": [
        "element_selector",
        "original_html",
        "fix_html",
        "fix_explanation",
        "wcag_criterion",
        "impact",
        "explanation",
        "confidence_score",
    ],
}

# Cap on bytes we'll json.loads from an LLM. Picked 64KB because a single fix
# rarely exceeds 2-3KB; anything an order of magnitude bigger is either a runaway
# response or a prompt-injection trying to OOM the parser. See B5 in CHANGELOG.
_MAX_LLM_BYTES = 64_000

# Regex for lines that look like prompt-injection role headers.
_ROLE_HEADER_RE = re.compile(
    r"^(#{1,6}\s|system:|assistant:|human:|user:|ignore\b)",
    re.IGNORECASE | re.MULTILINE,
)
# Matches <script ...>...</script> blocks including across newlines.
_SCRIPT_TAG_RE = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
# Role-tag style injections like <|system|> or </s>.
_ROLE_TAG_RE = re.compile(r"<\|[^|>]{1,32}\|>|</?s>", re.IGNORECASE)


def _sanitize_html_for_prompt(html: str) -> str:
    """Sanitize arbitrary page HTML before including it in an LLM prompt.

    Steps applied in order:
    1. Strip null bytes and ASCII control characters (except newline/tab).
    2. Remove <script>...</script> blocks.
    3. Remove role-tag style sequences used by some model tokenizers.
    4. Redact lines that begin with prompt-injection markers
       (###, System:, Assistant:, Human:, Ignore ...).
    5. Truncate to 2000 chars so a huge page never blows the context window.

    The result is still HTML — we are not HTML-escaping the whole blob,
    just neutering the patterns that commonly show up in prompt-injection PoCs.
    """
    # Step 1: drop null bytes + control chars (keep \n \t \r)
    html = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", html)
    # Step 2: strip script blocks
    html = _SCRIPT_TAG_RE.sub("<!-- script removed -->", html)
    # Step 3: strip model-specific role tags
    html = _ROLE_TAG_RE.sub("", html)
    # Step 4: redact injection-looking lines
    html = _ROLE_HEADER_RE.sub("[REDACTED] ", html)
    # Step 5: truncate
    return html[:2000]


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Anything that turns a ViolationInput into a fully-populated AuditResult.

    Implementations: OllamaClient (real), MockClient (deterministic, for tests
    and CI). Both accept an html_context snippet and a file_path label.
    """

    def generate_fix(
        self,
        violation: ViolationInput,
        html_context: str,
        file_path: str,
    ) -> AuditResult: ...


class OllamaClient:
    def __init__(self, model: str = "llama3.1:8b") -> None:
        # Lazy import: when MOCK_LLM=1 we never need the ollama package, and on
        # some dev machines its proxy detection fails at import time. Pulling
        # the import inside __init__ keeps `pytest tests/unit/` clean.
        import ollama as _ollama
        self._model = model
        self._client = _ollama.Client()

    def generate_fix(
        self,
        violation: ViolationInput,
        html_context: str,
        file_path: str,
    ) -> AuditResult:
        # Trim node HTML so a single noisy violation can't blow the context window.
        nodes_summary = []
        for node in violation.nodes[:3]:
            trimmed = {k: (v[:500] if isinstance(v, str) else v) for k, v in node.items()}
            nodes_summary.append(trimmed)

        user_content = json.dumps(
            {
                "rule_id": violation.id,
                "description": violation.description,
                "help_url": violation.help_url,
                "impact": violation.impact.value,
                "wcag_criterion": violation.wcag_criterion,
                "nodes": nodes_summary,
                "html_context_snippet": _sanitize_html_for_prompt(html_context) if html_context else "",
            },
            ensure_ascii=False,
        )

        response = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            format=_FIX_SCHEMA,
        )

        raw = response.message.content
        if raw is None:
            raise ValueError("LLM response had no content")
        if len(raw) > _MAX_LLM_BYTES:
            raise ValueError(f"LLM response too large: {len(raw)} chars (cap: {_MAX_LLM_BYTES})")
        data = json.loads(raw)

        fix = ViolationFix(
            element_selector=data["element_selector"],
            original_html=data["original_html"],
            fix_html=data["fix_html"],
            fix_explanation=data["fix_explanation"],
            wcag_criterion=data.get("wcag_criterion", violation.wcag_criterion),
            impact=ImpactLevel(data.get("impact", violation.impact.value)),
        )

        return AuditResult(
            file_path=file_path,
            wcag_criterion=data.get("wcag_criterion", violation.wcag_criterion),
            rule_id=violation.id,
            impact=ImpactLevel(data.get("impact", violation.impact.value)),
            fixes=[fix],
            explanation=data.get("explanation", ""),
            confidence_score=float(data.get("confidence_score", 0.5)),
        )


# Per-rule mock fix shapes. We hand-wrote these so the mock client returns
# something a human would recognise as a plausible fix for that rule, not a
# generic placeholder. Keeps schema_compliance eval tests honest.
_MOCK_FIX_RULES: dict[str, dict[str, str]] = {
    "image-alt": {
        "selector": "img",
        "fix_template": "<img src='{src}' alt='[Descriptive alternative text]'>",
        "explanation": "Add a descriptive alt attribute to convey the image content to screen reader users.",
    },
    "label": {
        "selector": "input",
        "fix_template": "<label for='input-id'>Field label</label>\n<input id='input-id' {attrs}>",
        "explanation": "Associate a <label> element with the input using matching for/id attributes.",
    },
    "button-name": {
        "selector": "button",
        "fix_template": "<button aria-label='[Action description]'>{content}</button>",
        "explanation": "Add an aria-label or visible text content to identify the button's purpose.",
    },
    "link-name": {
        "selector": "a",
        "fix_template": "<a href='{href}'>[Descriptive link text]</a>",
        "explanation": "Add descriptive text content or aria-label to identify the link's destination.",
    },
    "duplicate-id": {
        "selector": "[id]",
        "fix_template": "<{tag} id='{unique_id}' {attrs}>",
        "explanation": "Replace duplicate id values with unique identifiers across the page.",
    },
    "html-has-lang": {
        "selector": "html",
        "fix_template": "<html lang='en'>",
        "explanation": "Add a lang attribute to the <html> element to identify the page language.",
    },
    "scrollable-region-focusable": {
        "selector": "[tabindex='-1']",
        "fix_template": "<div tabindex='0' role='region' aria-label='[Region label]'>",
        "explanation": "Make scrollable regions keyboard accessible by setting tabindex='0'.",
    },
    "color-contrast": {
        "selector": "*",
        "fix_template": "<!-- Increase contrast ratio to at least 4.5:1 for normal text -->",
        "explanation": "Adjust foreground or background color to meet minimum contrast ratio requirements.",
    },
}

_DEFAULT_MOCK_FIX = {
    "selector": "*",
    "fix_template": "<!-- Fix: address the {rule_id} violation per WCAG {criterion} -->",
    "explanation": "Address the accessibility violation to meet WCAG {criterion} requirements.",
}


class MockClient:
    """Deterministic stand-in for OllamaClient used in tests and CI.

    Returns the same shape OllamaClient would, with confidence_score fixed at
    0.95 and explanation prefixed with "[MOCK]" so a fixture leaking into a
    real audit is obvious in the report.
    """

    def generate_fix(
        self,
        violation: ViolationInput,
        html_context: str,
        file_path: str,
    ) -> AuditResult:
        original_html = "<element>"
        if violation.nodes:
            original_html = violation.nodes[0].get("html", "<element>")

        rule_hints = _MOCK_FIX_RULES.get(violation.id, _DEFAULT_MOCK_FIX)

        fix_html = rule_hints["fix_template"].format(
            src="image.png",
            href="#",
            tag="div",
            unique_id=f"{violation.id}-fixed",
            attrs="",
            content="Button",
            rule_id=violation.id,
            criterion=violation.wcag_criterion,
        )

        explanation = rule_hints["explanation"].format(
            rule_id=violation.id,
            criterion=violation.wcag_criterion,
        )

        fix = ViolationFix(
            element_selector=rule_hints["selector"],
            original_html=original_html,
            fix_html=fix_html,
            fix_explanation=explanation,
            wcag_criterion=violation.wcag_criterion,
            impact=violation.impact,
        )

        return AuditResult(
            file_path=file_path,
            wcag_criterion=violation.wcag_criterion,
            rule_id=violation.id,
            impact=violation.impact,
            fixes=[fix],
            explanation=f"[MOCK] {explanation}",
            confidence_score=0.95,
        )


def get_client(model: str = "llama3.1:8b") -> LLMClientProtocol:
    """Return MockClient when MOCK_LLM=1, otherwise OllamaClient(model)."""
    if os.environ.get("MOCK_LLM") == "1":
        return MockClient()
    return OllamaClient(model=model)
