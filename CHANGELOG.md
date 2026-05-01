# Changelog

All notable changes go here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: SemVer.

## [Unreleased]

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

[Unreleased]: https://example.com/wcag-auditor/compare/0.2.0...HEAD
[0.2.0]: https://example.com/wcag-auditor/compare/0.1.0...0.2.0
[0.1.0]: https://example.com/wcag-auditor/releases/tag/0.1.0
