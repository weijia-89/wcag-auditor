# Roadmap

Updated 2026-04-30. Order within each section reflects priority, not commitment. None of this is a release schedule.

## Next

Housekeeping first. There's a small set of items that block the eval numbers from being trustworthy, and until these land, `make eval-full` is informative but not a gate. The baseline is synthetic, the axe hash is a placeholder, and the install path isn't reproducible. None of those are blocking in the sense that the tool won't run, but they are blocking in the sense that you can't trust the numbers, and a tool whose eval results you can't trust is harder to defend when it matters.

- **Real eval baseline.** `eval_baseline.json` currently reflects a synthetic run. Capture numbers from `make eval-full` against the curated fixtures with the deterministic `RuleEngine`, commit them, and let `--accept-zero-baseline` retire. The regression gate isn't useful until the baseline reflects a real run.
- **SHA-pin axe.min.js.** `scripts/download_axe.py` already verifies SHA256. The `EXPECTED_SHA256` constant is still the placeholder value. Populate it with the hash for axe-core 4.10.2, which is what `download-axe` targets.
- **Hash-pinned lockfile.** `pyproject.toml` doesn't pin transitive deps right now, which means the install path is not reproducible across machines, which means "it works on my laptop" is doing too much work. Switch to `uv pip compile --generate-hashes` and check the resulting `requirements.txt` into the repo.
- **Test the `Auditor` class directly.** Today `axe_runner`, the fix engine shape, and the regression gate all have unit coverage. `auditor.audit` is exercised only end-to-end. Add a unit test that injects a stub `FixEngineProtocol` implementation and a fake violation list, so an `auditor.py` refactor shows up in tests before it shows up in prod.

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
