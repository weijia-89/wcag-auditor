# Roadmap

Updated 2026-05-28. Order within each section reflects priority, not commitment. None of this is a release schedule.

## Next

Housekeeping first. A few items still block treating `make eval-full` as a hard gate everywhere.

**Done (2026-05):** SHA-pinned `axe.min.js` via jsDelivr/npm bundle + SHA256 verify in `scripts/download_axe.py` (axe-core 4.10.2).

**Done (2026-05-28):** **Real eval baseline** — [#5](https://github.com/weijia-89/wcag-auditor/pull/5) committed fixture-run metrics to `eval_baseline.json` (Playwright + axe + `RuleEngine`).

**Done (2026-05-28):** **Auditor unit coverage** — [#6](https://github.com/weijia-89/wcag-auditor/pull/6) extends `tests/unit/test_auditor.py` for orchestration with `RuleEngine` (still not a full injected `FixEngineProtocol` fake-violation harness).

- **Hash-pinned lockfile.** `pyproject.toml` doesn't pin transitive deps right now, which means the install path is not reproducible across machines. Switch to `uv pip compile --generate-hashes` and check the resulting `requirements.txt` into the repo.
- **Test the `Auditor` class with injected violations.** Add a unit test that injects a stub `FixEngineProtocol` and a fake violation list (no browser), so an `auditor.py` refactor fails in unit tests before CI's fixture smoke.

## Later

Lower priority. These depend on the Next items landing first, or they're design problems that need more thought before code gets written.

- **Batch mode.** A single `wcag-auditor batch fixtures/` that takes a directory and emits one combined report. The README currently shows a bash for-loop; that works, but it's the wrong ergonomic for someone auditing 50 pages and wanting a single summary at the end rather than 50 individual terminal outputs to scroll through.
- **Pluggable fix engines.** The `FixEngineProtocol` seam exists. Adding a second engine — for example, an LLM-backed implementation behind a flag for users who want it — is implementing a second class, not redesigning anything. No cloud APIs, see Won't-do.
- **Custom rule packs.** axe supports custom rules registered at runtime. Expose a CLI flag to load a JS file. Useful for in-house WCAG interpretations that differ from the axe defaults.
- **JUnit / SARIF output.** Right now, `--output json` users shell out to whatever CI they have. SARIF would let GitHub code-scanning ingest results natively, which is probably worth it for the projects that already have code-scanning enabled.
- **Caching of fix output.** Same violation, same HTML context, same fix template result. A content-addressed cache keyed by `(rule_id, html_hash)` is a small win for in-process `RuleEngine` and a meaningful one if a future engine is more expensive. Probably a sqlite table next to `audits.db`.

## Won't-do

Explicit non-goals. Won't be reconsidered.

- **Microservices.** This is a CLI: one process, one lifetime, six modules. Splitting into services adds RPC, deployment, and observability overhead for zero user-visible gain.
- **Kubernetes / Helm chart / operator.** Wrong shape. If you want to run this at scale, run it in a job runner with a real result store. The project won't own a k8s component.
- **GraphQL API.** There's a CLI and a SQLite file. If you want a server, write one against the SQLite file. That's genuinely better than us maintaining an API surface.
- **Cloud LLM backends (OpenAI, Anthropic, etc.).** Local-only by design. Adds a paid API dependency and ships node HTML to a third party. Hard line.
- **Auto-applying fixes to source files.** Accessibility fixes are judgment calls, and "it passes axe" isn't the same as "it works for a screen reader user who navigates by heading." Suggestions only. Always.
- **LLM-as-judge in CI.** Flaky, expensive, hard to reproduce. Deterministic structural metrics only. If you want non-determinism in your quality gate, that's your call, not this project's.
- **Browser other than Chromium.** Three browsers triple Playwright surface for marginal coverage gain. axe behaves the same across all three; this isn't a cross-browser testing tool.
- **A web UI.** Out of scope. The JSON output is the interface. Build the UI yourself if you want one, the schema is stable.
