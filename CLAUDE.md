# CLAUDE.md: wcag-auditor

## Stack

| Layer | Tech |
|-------|------|
| Language | Python 3.11.9 |
| Package manager | uv |
| Browser automation | Playwright (sync API, Chromium) |
| Accessibility engine | axe-core (bundled, no CDN) |
| Fix engine | Deterministic per-rule templates (`RuleEngine`). 0.2.x ran Ollama; removed in 0.3.0. |
| Data validation | Pydantic v2 |
| CLI | Typer + Rich |
| Database | SQLite via sqlite-utils, WAL mode |
| Testing | pytest + pytest-asyncio + pytest-json-report |

## Layout

```
src/wcag_auditor/
  __init__.py          empty
  models.py            Pydantic: ViolationInput, AuditResult, AuditReport
  fix_engine.py        RuleEngine, FixEngineProtocol, get_engine(), _sanitize_html_for_prompt; BC aliases for the old llm_client names kept until 0.4.0
  axe_runner.py        run_axe(), run_axe_from_json(), _extract_wcag_criterion()
  auditor.py           Auditor: drives Playwright + axe + LLM
  database.py          SQLite via sqlite-utils
  eval_metrics.py      Deterministic + Playwright-based eval metrics
  cli.py               Typer commands: audit, history, report
  static/axe.min.js    axe-core (gitignored; run `make download-axe`)

tests/
  unit/                Fast, no browser, no network
  eval/                Metric-driven; CI subset + full run
  fixtures/
    html/              6 curated violation fixtures
    golden_dataset.json

scripts/
  check_regression.py  CI gate: compare eval scores to baseline
  download_axe.py      Pull axe.min.js, SHA256-verified
```

## Test commands

```bash
make test-unit        # always fast, no deps
make eval             # CI eval (WCAG_MOCK_AXE=1, no browser; uses .axe.json sidecars)
make eval-full        # full eval (Playwright + Chromium; no model server)
make check-regression # gate
make lint
```

## Context-window strategy

- axe output can be large; `auditor.py` truncates `html_context` to 3000 chars.
- `ViolationInput.nodes` is passed through; `RuleEngine` reads only the first node's `html` field. No external prompt is constructed.
- `AuditResult` is produced deterministically by `RuleEngine`. No prose parsing.
- One `RuleEngine` call per violation, no batching. Keeps per-violation retry tractable.

## Don't-do list

- Don't load axe-core from a CDN. Breaks file:// pages on Chromium.
- Don't auto-apply fix_html. Suggestions only.
- Don't log node HTML at INFO. May contain user data.
- Don't add openai or anthropic as deps.
- Don't use async Playwright. The sync API is intentional.
- Don't share a browser across audit() calls.
- Don't update `eval_baseline.json` from a script. Manual only.
- Don't read paths outside cwd subtree without `WCAG_ALLOW_FILE_OUTSIDE_CWD=1`. `_path_to_url` confines local paths to defend against `wcag-auditor audit /etc/shadow`.
- Don't scan link-local / loopback / RFC1918 hosts without `WCAG_ALLOW_LOCALHOST=1` / `WCAG_ALLOW_PRIVATE_NET=1`. SSRF guard for cloud metadata exfil (169.254.169.254).
- Don't launch Chromium with `--no-sandbox` by default. Gated behind `WCAG_NO_SANDBOX=1` or `--unsafe-no-sandbox`.

## Vibe-safety map

| Area | Rating | Notes |
|------|--------|-------|
| `models.py` | SAFE | Pure Pydantic, no I/O. |
| `axe_runner.py` `_path_to_url` | REVIEW | Reads user paths; cwd-confined (B2). |
| `axe_runner.py` `_check_http_url_safe` | REVIEW | SSRF guard (B11). Always blocks 169.254/16. |
| `axe_runner.py` (rest) | SAFE | Read-only page evaluation. |
| `database.py` | REVIEW | chmod 600 + WAL on first open. |
| `fix_engine.py` | SAFE | RuleEngine only. No external calls, no network surface. `_sanitize_html_for_prompt` is retained as a defensive HTML normalizer for axe `html_context` snippets. |
| `auditor.py` | REVIEW | Playwright launch. `--no-sandbox` is opt-in (B9). |
| `cli.py` | SAFE | Typer handles shell escaping; no subprocess. |
| `eval_metrics.py` `FixApplicabilityMetric` | DANGER | Launches browser + writes temp files. Untrusted HTML = no. |
| `scripts/download_axe.py` | DANGER | Downloads + writes axe-core. SHA256-pinned (B8); fails closed when hash unset. |

## CI vs local eval

| Run | WCAG_MOCK_AXE | Browser | Gate |
|-----|---------------|---------|------|
| `make test-unit` | not needed | no | always |
| `make eval` (CI) | yes | no | schema_compliance_rate only |
| `make eval-full` | no | yes | all 6 metrics |

CI only enforces `schema_compliance_rate`. The remaining 5 metrics (criterion accuracy, impact accuracy, hallucination rate, fix applicability, false-negative rate) require `make eval-full`, which needs a Playwright-installed Chromium but no model server.

## Session log

- 2026-04-28: scaffold created. Source, tests, fixtures, scripts.
- 2026-04-30: hardening pass. B1, B2, B5, B8, B9, B11 fixed. See CHANGELOG.md.
