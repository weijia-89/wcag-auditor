# Architecture

One Python package, six modules. Each module encapsulates one concern; the intent is that swapping an implementation means editing one file.

## Diagram

```
       +-----------+
       |   cli.py  |   Typer commands: audit / history / report
       +-----+-----+
             |
             v
       +-----+-----+
       | auditor.py|   Auditor class: orchestrates the run
       +--+--+--+--+
          |  |  |
   +------+  |  +-------------+
   |         |                |
   v         v                v
+--+----+ +--+--------+ +-----+-----+
| axe_  | | llm_      | | database  |
| runner| | client    | | (sqlite)  |
+-------+ +-----------+ +-----------+
   |
   v
+--+----+
|models |   Pydantic shapes shared by everything
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

Trade-off: axe is bundled, not loaded from CDN. Works on file:// pages; means we ship a 500KB JS file. We chose ship-it over runtime fragility.

### `auditor`

Hides: the orchestration order. Browser launch lives here (not in `axe_runner`) so a mock-only run never imports Playwright.

- One browser per `audit()` call. Cheap enough; safer than sharing.
- LLM failures on a single violation log and continue. Total result count drops, signals trouble without aborting.
- `MOCK_LLM=1` short-circuits Playwright entirely and reads a `.axe.json` sidecar if present.

Trade-off: per-violation LLM call (no batching). Slower for noisy pages, lets each fix retry independently.

### `llm_client`

Hides: the LLM provider. `LLMClientProtocol` is the seam. Swap in a different backend without touching `auditor`.

- `OllamaClient` talks to a local Ollama server. Lazy-imports `ollama` so MOCK_LLM stays clean.
- `MockClient` is deterministic, prefixes `[MOCK]` on explanation.
- 64KB cap on response bytes before parse (B5).

Trade-off: structured-output via the `format=` schema. Locks us to Ollama's JSON-schema support; that's fine for now.

### `database`

Hides: persistence shape. Today SQLite via sqlite-utils. If we ever want Postgres, only this module changes.

- WAL mode + 0600 permissions enforced on every open.
- `WCAG_DB_PATH` env override.
- One table, one row per audit, full report stored as JSON in `report_json`.

Trade-off: storing JSON blobs is denormalised. We get reads-by-id for free and don't pay for relational ergonomics we don't use.

### `eval_metrics`

Hides: how good is good? Six metrics:

- 4 deterministic (no browser, no LLM): schema_compliance, criterion_accuracy, impact_accuracy, hallucination.
- 1 Playwright-based: fix_applicability. Apply the fix, re-run axe, check the violation is gone.
- (false_negative is the inverse view of fix_applicability against a known-bad fixture set.)

Trade-off: hallucination metric is structural, not LLM-as-judge. Cheap, zero non-determinism, narrower coverage. We accept the narrower view because LLM-as-judge in CI is a recipe for flaky gates.

### `cli`

Hides: how the user invokes the thing. Typer + Rich. No business logic past argument parsing and output rendering.

Trade-off: Rich tables aren't machine-readable; that's why `--output json` exists.

## Data flow

```
target (str) -> Auditor.audit
    -> [mock]  Auditor._get_violations_mock -> run_axe_from_json
    -> [real]  Auditor._get_violations_real -> Playwright.launch
                                            -> run_axe -> axe.run -> _parse_violations
    -> for each ViolationInput:
           LLMClientProtocol.generate_fix -> AuditResult
    -> AuditReport.from_results
    -> save_report (optional)
    -> Rich table or JSON
```

## Build system

`pyproject.toml` uses hatchling as the build backend. The wheel package root is `src/wcag_auditor`. `[tool.pytest.ini_options]` sets `pythonpath = ["src"]` so tests import directly from the source tree without an editable install.

## CI

`.github/workflows/ci.yml` runs on push and PR to `main`.

- Runner: `ubuntu-latest`, Python 3.11 via `astral-sh/setup-uv@v4`.
- Install: `uv sync --all-groups` (pulls dev group: pytest, ruff, etc.).
- Test step: `uv run pytest tests/unit/ -v`. Unit tests use `MockClient` and recorded axe output; no Playwright binary or live Ollama needed in CI.
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` is set at the workflow level.

The full eval (`make eval-full`) is not in CI because it requires a running Ollama server and a Playwright-installed Chromium. Run it locally before tagging a release.

## What we deliberately did not do

- No async. The sync Playwright API is intentional. One browser, one page, one violation list, in order.
- No plugin system for LLM providers. The Protocol is enough; users write a class.
- No streaming. axe finishes, we ask LLM, we render. Streaming added complexity for negligible UX gain on a tool this fast.
- No batching across violations. See trade-off above.
