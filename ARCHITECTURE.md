# Architecture

One Python package, six modules. Each module encapsulates one concern. Swapping an implementation means editing one file, not hunting through a call graph figuring out how many places assumed something about the old implementation. No magic, no framework.

## Diagram

```
 +-----------+
 | cli.py | Typer commands: audit / history / report
 +-----+-----+
       |
       v
 +-----+-----+
 | auditor.py| Auditor class: orchestrates the run
 +--+--+--+--+
    |  |  |
 +--+  |  +-------------+
 |     |                |
 v     v                v
+--+----+ +--+--------+ +-----+-----+
| axe_  | | llm_      | | database  |
| runner| | client    | | (sqlite)  |
+-------+ +-----------+ +-----------+
              |
              v
         +--+----+
         |models | Pydantic shapes shared by everything
         +-------+

eval_metrics.py: sits beside auditor; consumes AuditResult/AuditReport.
scripts/check_regression.py: CI gate, reads pytest-json-report output.
```

## Modules

### `axe_runner`

Hides: how axe-core runs against a page, and how a URL/path becomes a target.

- `run_axe(page, url_or_path)` runs axe inside a Playwright `Page`.
- `run_axe_from_json(path)` parses a recorded result file.
- `_path_to_url` confines local paths to cwd (B2).
- `_check_http_url_safe` is the SSRF guard (B11).
- `_extract_wcag_criterion` parses axe tags `wcag111` -> `1.1.1`.

Trade-off: axe is bundled, not loaded from CDN. Works on file:// pages without network access. It does mean we ship a 500KB JS file in the wheel, but a CDN fetch that fails at 2am when someone is debugging a regression before a deadline is worse than a slightly larger package. The SHA-pin in `download_axe.py` means you know exactly which version of axe you have.

### `auditor`

Hides: the orchestration order. Browser launch lives here (not in `axe_runner`) so a mock-only run never imports Playwright.

- One browser per `audit()` call. Cheap enough; safer than sharing.
- LLM failures on a single violation log and continue. Total result count drops, which signals trouble without aborting the entire run.
- `WCAG_MOCK_AXE=1` short-circuits Playwright entirely and reads a `.axe.json` sidecar if present.

Trade-off: per-violation fix-engine call (no batching). For the in-process `RuleEngine` the cost is microseconds, but the structure is preserved because a future async or LLM-backed engine would want the same per-violation retry seam.

### `fix_engine`

Hides: the fix-generation strategy. `FixEngineProtocol` is the seam. Swap in a different engine without touching `auditor`. Renamed from `llm_client` in 0.3.1 once the module had stopped containing an LLM client; the old names (`LLMClientProtocol`, `get_client`) survive as BC aliases until 0.4.0.

- Contains `RuleEngine`, the sole `FixEngineProtocol` implementation. Deterministic, no external calls. Per-rule fix templates for known axe rule IDs; fallback template handles unknowns. `confidence_score` fixed at 0.95. `_sanitize_html_for_prompt` is a utility function used by `auditor.py`.

Trade-off: deterministic rule templates mean fix quality is bounded by what's in the template set, not by model capability. For a local tool whose primary value is making the axe 30-40% faster to act on, the trade is correct: predictable output, no network, no model variance in CI.

### `database`

Hides: persistence shape. Today SQLite via sqlite-utils. If we ever want Postgres, only this module changes. Nothing else needs to know.

- WAL mode + 0600 permissions enforced on every open.
- `WCAG_DB_PATH` env override.
- One table, one row per audit, full report stored as JSON in `report_json`.

Trade-off: storing JSON blobs is denormalised. We get reads-by-id for free and don't pay for relational ergonomics we don't use. If you never join the reports table to anything, normalising it costs more than it buys.

### `eval_metrics`

Hides: how good is good? Six metrics:

- 4 deterministic (no browser, no LLM): schema_compliance, criterion_accuracy, impact_accuracy, hallucination.
- 1 Playwright-based: fix_applicability. Apply the fix, re-run axe, check the violation is gone.
- (false_negative is the inverse view of fix_applicability against a known-bad fixture set.)

Trade-off: hallucination metric is structural, not LLM-as-judge. Cheap and zero non-determinism, though the coverage is narrower. LLM-as-judge in CI is a recipe for flaky gates, and flaky gates are worse than no gates.

### `cli`

Hides: how the user invokes the thing. Typer + Rich. No business logic past argument parsing and output rendering. Keep it that way.

Trade-off: Rich tables aren't machine-readable; that's why `--output json` exists.

## Data flow

```
target (str) -> Auditor.audit
  -> [mock] Auditor._get_violations_mock -> run_axe_from_json
  -> [real] Auditor._get_violations_real -> Playwright.launch
                                         -> run_axe -> axe.run -> _parse_violations
  -> for each ViolationInput:
       LLMClientProtocol.generate_fix -> AuditResult
  -> AuditReport.from_results
  -> save_report (optional)
  -> Rich table or JSON
```

## Build system

`pyproject.toml` uses hatchling as the build backend, and the wheel package root is `src/wcag_auditor`. `[tool.pytest.ini_options]` sets `pythonpath = ["src"]` so tests import directly from the source tree without an editable install, which keeps CI setup simpler than it would otherwise be.

## CI

`.github/workflows/ci.yml` runs on push and PR to `main`.

- Runner: `ubuntu-latest`, Python 3.11 via `astral-sh/setup-uv@v4`.
- Install: `uv sync --all-groups` (pulls dev group: pytest, ruff, etc.).
- Test step: `uv run pytest tests/unit/ -v`. Unit tests use `RuleEngine` and recorded axe output; no Playwright binary and no model server needed in CI.
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` is set at the workflow level.

The full eval (`make eval-full`) is not in CI because it requires a Playwright-installed Chromium. Run it locally before tagging a release. Don't skip this step.

## What we deliberately did not do

Explicit choices, not oversights.

- No async. The sync Playwright API is intentional, one browser, one page, one violation list, in order, with predictable teardown. Async would complicate error handling for marginal throughput gain on a tool that isn't bottlenecked on network I/O.
- No plugin system for LLM providers. The Protocol is enough; users write a class and pass it in.
- No streaming. axe finishes, we ask LLM, we render. Streaming added complexity for negligible UX gain on a tool this fast.
- No batching across violations. See trade-off above.
