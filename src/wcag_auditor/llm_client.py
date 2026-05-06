from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from wcag_auditor.models import AuditResult, ViolationFix, ViolationInput

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
    """Sanitize arbitrary page HTML before including it in an audit context.

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
    """Anything that turns a ViolationInput into a fully-populated AuditResult."""

    def generate_fix(
        self,
        violation: ViolationInput,
        html_context: str,
        file_path: str,
    ) -> AuditResult: ...


# Per-rule fix shapes. Hand-written so the engine returns something a human
# would recognise as a plausible fix for that rule.
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


class RuleEngine:
    """Deterministic rule-based fix generator. No external dependencies.

    Returns the same shape as the former OllamaClient, with confidence_score
    fixed at 0.95 and explanation prefixed with "[RULE]" so a test fixture
    leaking into a real audit is obvious in the report.
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
            explanation=f"[RULE] {explanation}",
            confidence_score=0.95,
        )


def get_client(model: str = "llama3.1:8b") -> LLMClientProtocol:
    """Returns a RuleEngine instance."""
    return RuleEngine()
