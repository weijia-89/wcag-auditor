from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import pathname2url

from playwright.sync_api import Page

from wcag_auditor.models import ImpactLevel, ViolationInput

AXE_JS_PATH = Path(__file__).parent / "static" / "axe.min.js"

# Run axe-core against the live document. Tag set covers WCAG 2.0/2.1/2.2 AA
# plus axe's best-practice rules (best-practice items show up with no impact
# field; _parse_violations defaults those to MINOR).
_AXE_RUNNER_JS = """
async () => {
    const results = await axe.run(document, {
        runOnly: {
            type: 'tag',
            values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice']
        }
    });
    return JSON.stringify(results.violations);
}
"""

# axe tags look like wcag111 / wcag143 / wcag412. First digit is the
# principle, next is the guideline, last is the criterion. Always 3 digits
# in 2.2.
_WCAG_TAG_RE = re.compile(r"^wcag(\d)(\d{1,2})(\d{1,2})$")


def _extract_wcag_criterion(tags: list[str]) -> str:
    """First wcagXYZ tag wins. Returns 'unknown' if none match."""
    for tag in tags:
        m = _WCAG_TAG_RE.match(tag)
        if m:
            return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return "unknown"


def _reject_if_outside_cwd(abs_path: Path) -> None:
    """Block `wcag-auditor audit /etc/shadow` and friends.

    Resolves to an absolute path and checks it's under cwd. Override with
    WCAG_ALLOW_FILE_OUTSIDE_CWD=1 for the legitimate case (developer pointing
    at a fixture in a sibling directory). Without the override the obvious
    path-traversal vector (file:///etc/shadow served to Playwright) just fails.
    """
    if os.environ.get("WCAG_ALLOW_FILE_OUTSIDE_CWD") == "1":
        return
    cwd = Path.cwd().resolve()
    try:
        abs_path.relative_to(cwd)
    except ValueError:
        raise ValueError(
            f"Refusing to read {abs_path}: path is outside the current working "
            f"directory ({cwd}). Set WCAG_ALLOW_FILE_OUTSIDE_CWD=1 to override."
        )


def _path_to_url(path_or_url: str) -> str:
    """Turn a local path into a file:// URI, leaving http(s)/file:// alone."""
    if path_or_url.startswith(("http://", "https://", "file://")):
        return path_or_url
    abs_path = Path(path_or_url).resolve()
    _reject_if_outside_cwd(abs_path)
    return "file://" + pathname2url(str(abs_path))


def _check_http_url_safe(url: str) -> None:
    """SSRF guard for user-supplied http(s) URLs.

    Rejects loopback, link-local, and RFC1918 hosts when the host portion is an
    IP literal. Hostnames are NOT resolved here on purpose: we don't want a DNS
    round-trip just to validate, and Playwright will fail fast on a bad target.

    The big one is link-local 169.254.0.0/16: cloud metadata services live
    there and we never allow that, env override or not. Loopback and private
    nets are gated behind WCAG_ALLOW_LOCALHOST / WCAG_ALLOW_PRIVATE_NET so
    `wcag-auditor audit http://localhost:3000` still works when you opt in.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return
    host = parsed.hostname
    if not host:
        raise ValueError(f"Refusing to fetch {url}: no host could be parsed.")

    allow_localhost = os.environ.get("WCAG_ALLOW_LOCALHOST") == "1"
    allow_private = os.environ.get("WCAG_ALLOW_PRIVATE_NET") == "1"

    if host == "localhost":
        if allow_localhost:
            return
        raise ValueError(
            f"Refusing to fetch {url}: localhost is blocked. "
            "Set WCAG_ALLOW_LOCALHOST=1 to override."
        )

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP literal. Treat as a public hostname and let the request go.
        return

    if ip.is_loopback:
        if allow_localhost:
            return
        raise ValueError(
            f"Refusing to fetch {url}: loopback address ({ip}) is blocked. "
            "Set WCAG_ALLOW_LOCALHOST=1 to override."
        )
    if ip.is_link_local:
        # 169.254/16 covers cloud metadata. No env override.
        raise ValueError(
            f"Refusing to fetch {url}: link-local address ({ip}) is blocked "
            "(SSRF guard for cloud metadata services)."
        )
    if ip.is_private:
        if allow_private:
            return
        raise ValueError(
            f"Refusing to fetch {url}: private RFC1918 address ({ip}) is blocked. "
            "Set WCAG_ALLOW_PRIVATE_NET=1 to override."
        )


def _check_axe_installed() -> None:
    if not AXE_JS_PATH.exists():
        # GitHub release assets no longer ship axe.min.js; use scripts/download_axe.py.
        raise FileNotFoundError(
            f"axe-core not found at {AXE_JS_PATH}. "
            "Run: make download-axe\n"
            "Or:  uv run python scripts/download_axe.py"
        )
    content = AXE_JS_PATH.read_text(encoding="utf-8", errors="replace")
    # sdk-review F2: axe.min.js is gitignored — fresh clones have no file; run download-axe.
    # If a local placeholder stub exists, detect it by marker (not bundled in git).
    if "axe-core placeholder" in content:
        raise FileNotFoundError(
            f"axe.min.js at {AXE_JS_PATH} is still the placeholder file. "
            "Run: make download-axe"
        )


def _parse_violations(violations_json: str) -> list[ViolationInput]:
    violations_data = json.loads(violations_json)
    results: list[ViolationInput] = []

    for v in violations_data:
        # axe sets impact=None for best-practice rules. Default to MINOR so
        # downstream code can rely on a real ImpactLevel everywhere.
        raw_impact = v.get("impact") or "minor"
        try:
            impact = ImpactLevel(raw_impact)
        except ValueError:
            impact = ImpactLevel.MINOR

        tags = v.get("tags", [])
        results.append(
            ViolationInput(
                id=v["id"],
                description=v.get("description", ""),
                help_url=v.get("helpUrl", ""),
                impact=impact,
                nodes=v.get("nodes", []),
                wcag_criterion=_extract_wcag_criterion(tags),
            )
        )

    return results


def run_axe(
    page: Page,
    url_or_path: str,
    timeout_ms: int = 15_000,
) -> list[ViolationInput]:
    """Run axe-core on a page and return its violations.

    The caller owns the Playwright Page lifecycle. ``url_or_path`` can be a
    real URL or a filesystem path; paths are normalised to file:// URIs so
    axe-core can scan them with no web server involved.
    """
    _check_axe_installed()

    target_url = _path_to_url(url_or_path)
    if target_url.startswith(("http://", "https://")):
        _check_http_url_safe(target_url)
    page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)

    # Bundled axe only, never CDN. file:// pages block remote scripts on
    # Chromium, so any CDN approach silently breaks local fixture scans.
    page.add_script_tag(path=str(AXE_JS_PATH))

    violations_json: str = page.evaluate(_AXE_RUNNER_JS)
    return _parse_violations(violations_json)


def run_axe_from_json(json_path: str) -> list[ViolationInput]:
    """Load a recorded axe results file and return its violations.

    Accepts either a bare violations array or a full axe results object with a
    ``violations`` key. Useful for CI / mock mode where launching a browser
    isn't an option.
    """
    abs_path = Path(json_path).resolve()
    _reject_if_outside_cwd(abs_path)
    data = json.loads(abs_path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        violations_data = data
    elif isinstance(data, dict) and "violations" in data:
        violations_data = data["violations"]
    else:
        raise ValueError(
            f"Cannot parse axe JSON from {json_path}: "
            "expected a list of violations or a dict with a 'violations' key."
        )

    return _parse_violations(json.dumps(violations_data))
