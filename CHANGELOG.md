# Changelog

All notable changes go here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: SemVer.

## [0.2.3] - 2026-05-06

### Fixed

- **`_read_html_context` bypassed the CWD confinement guard.** `auditor.py` reads the first 3 KB of a local file to give the LLM context about the HTML being audited. That read happened before `run_axe` was called and before `_reject_if_outside_cwd` ran. A path like `../../etc/passwd` or `../../.env` would cause Playwright to refuse the `file://` URL, but the file content would already have been read into memory and embedded in the LLM prompt. Playwright blocking the browser and the LLM receiving the file are two different enforcement points, and only one of them was wired. Added `_reject_if_outside_cwd(abs_path)` inside `_read_html_context`, caught under `(OSError, ValueError)` so a path outside cwd just returns an empty string the same way an unreadable file does. Imported `_reject_if_outside_cwd` from `axe_runner` where it was already defined and tested.

## [0.2.2] - 2026-05-06

### Fixed

- **`_get_db()` ran WAL setup and `chmod` on every call.** Every database operation, `save_report`, `list_reports`, `get_report`, calls `_get_db()`, which was doing `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `db_path.chmod(0o600)`, and table creation on every single call. The chmod is the problem: two concurrent processes (the CLI and pytest, say) both starting at the same time will race on the `chmod` syscall. Extracted `_ensure_db_initialized(db_path)`, protected by a module-level `_initialized_paths: set[Path]` set, so the one-time work runs exactly once per path per process. Subsequent `_get_db()` calls skip straight to `sqlite_utils.Database(str(db_path))`.

- **`FixApplicabilityMetric` wrote temp HTML to `/tmp`, which failed the SSRF CWD guard.** The metric patches the input HTML and runs axe on the result, which means the patched file has to be reachable as a `file://` URL from Chromium. `wcag-auditor audit` runs with a CWD confinement guard that rejects local paths outside the working directory. `/tmp/tmpXXXXXX.html` is outside the working directory by definition. Changed `tempfile.NamedTemporaryFile(...)` to pass `dir=Path.cwd()` so the temp file lands where the guard expects it.

## [0.2.1] - 2026-05-06

Five findings from the second health audit (H1-H5) addressed. All closed.

### Added

- `_sanitize_html_for_prompt` in `llm_client.py` (H2). Found that `html_context[:2000]` was
  going into Ollama prompts verbatim, which meant a malicious HTML file could slip `System:` or `###`
  headers past the system prompt without any resistance. Turned out regex redaction of those line-start patterns was
  enough to close the practical injection path without mangling normal HTML, which was a relief because the alternative was full HTML parsing. Also strips script
  blocks, model role-tags (`<|system|>`), null bytes, and control characters. Applied in both
  `OllamaClient.generate_fix` and `Auditor.audit` (which now calls the sanitizer on the raw
  file read, not just at the LLM boundary).
- `WCAG_LLM_BATCH_SIZE` env var in `auditor.py` (H4). The N+1 sequential LLM loop is still
  sequential; wiring in real async concurrency would require rewriting the
  `LLMClientProtocol` interface, which isn't a one-line change. Added the env var and the
  per-batch progress log so the interface exists for a future `asyncio.gather` pass without
  any caller needing to change. Small investment now, bigger payoff later.
- `tests/unit/test_database.py`: 11 new tests for `save_report`, `list_reports`, `get_report`,
  the `WCAG_DB_PATH` override, and the 0600 chmod (H3). Found that none of the three public
  database functions had any unit coverage at all, which meant a schema migration would have silently broken
  persistence in CI without tripping a single assertion.
- `tests/unit/test_auditor.py`: 10 new tests for `Auditor` orchestration: mock-mode path,
  sidecar loading, LLM failure swallowing, report assembly, batch-size env var, and
  html_context sanitization end-to-end (H3).
- `tests/unit/test_llm_sanitizer.py`: 16 targeted tests for `_sanitize_html_for_prompt`:
  script removal, role-header redaction, role-tag removal, control char stripping, truncation,
  and clean passthrough (H2).
- Ruff lint step added to `.github/workflows/ci.yml` before the test run (H5). The number of unused imports that had accumulated across the test files was surprising: 10 fixable violations, all
  auto-corrected.

### Changed

- `Makefile` `check-regression` target now detects an all-zeros `eval_baseline.json` and
  prints a clear warning before skipping, rather than running a gate that can never fail
  (H1). The `--ci` flag is also passed so only `schema_compliance_rate` is checked under
  `MOCK_LLM=1`, which is the only metric that means anything without a real Ollama instance.

## [0.2.0] - 2026-04-30

Hardening pass. Six findings from the launch review (B1, B2, B5, B8, B9, B11) closed.

### Added

- `_path_to_url` cwd confinement (B2). Local paths must resolve under cwd. Override: `WCAG_ALLOW_FILE_OUTSIDE_CWD=1`.
- `_check_http_url_safe` SSRF guard (B11). Blocks loopback, link-local, and RFC1918 hosts when the URL host is an IP literal. Cloud metadata (169.254/16) is never overridable.
- 64KB hard cap on LLM response bytes before `json.loads` in `OllamaClient.generate_fix` (B5). Defends against pathological / prompt-injected responses.
- `--accept-zero-baseline` flag in `scripts/check_regression.py` (B1). Without it, a baseline of all zeros is rejected. A gate that always passes is worse than no gate.
- `scripts/download_axe.py` SHA256 verification (B8). URL is pinned to a tagged release. Refuses to write the file when `EXPECTED_SHA256` is the placeholder.
- `--unsafe-no-sandbox` CLI flag and `WCAG_NO_SANDBOX=1` env (B9). Chromium sandbox is on by default. Opt in for Docker / CI.
- New `SECURITY.md` with threat model.
- New `ARCHITECTURE.md` covering module decisions.
- New `ROADMAP.md`.

### Changed

- Default Chromium launch no longer passes `--no-sandbox`. Existing CI will need `WCAG_NO_SANDBOX=1`.
- `auditor.py` import of Playwright is now local to `_get_violations_real`. Lets `MOCK_LLM=1` work on machines without the browser binary.

### Fixed

- `_extract_wcag_criterion` correctly parses 4-digit WCAG tags via the existing regex. (Already worked; covered with explicit tests.)

### Security

- Database file is chmod'd to 0600 on every open in `_get_db`.
- Lazy import of `ollama` in `OllamaClient.__init__` so MOCK_LLM tests never reach the proxy detection that fails on some dev machines.

## [0.1.0] - 2026-04-28

Initial scaffold.

### Added

- `Auditor` class orchestrating Playwright + axe-core + LLM fix generation.
- `OllamaClient`, `MockClient`, `LLMClientProtocol`, `get_client()`.
- Pydantic models: `ImpactLevel`, `ViolationInput`, `ViolationFix`, `AuditResult`, `AuditReport`.
- Typer CLI: `audit`, `history`, `report`.
- SQLite history via sqlite-utils, WAL mode.
- 6 deterministic eval metrics: schema compliance, criterion accuracy, impact accuracy, hallucination, fix applicability, false-negative.
- `make` targets: `install`, `test-unit`, `eval`, `eval-full`, `check-regression`, `lint`, `download-axe`.
- 6 curated HTML fixtures covering image-alt, label, button-name, link-name, color-contrast, html-has-lang.
- Golden dataset for eval (positive + negative criteria lists).

[0.2.1]: https://example.com/wcag-auditor/compare/0.2.0...0.2.1
[0.2.0]: https://example.com/wcag-auditor/compare/0.1.0...0.2.0
[0.1.0]: https://example.com/wcag-auditor/releases/tag/0.1.0
