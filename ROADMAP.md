# Roadmap

Updated 2026-04-30. Order roughly reflects priority within each section, not commitment.

## Next

- **Real eval baseline.** `eval_baseline.json` currently reflects a synthetic run. Capture numbers from `make eval-full` against the curated fixtures, commit them, and let `--accept-zero-baseline` retire.
- **SHA-pin axe.min.js.** `scripts/download_axe.py` already verifies SHA256. Populate `EXPECTED_SHA256` for axe-core 4.10.2 and remove the placeholder.
- **Hash-pinned lockfile.** `pyproject.toml` doesn't pin transitive deps. Switch to `uv pip compile --generate-hashes` and check the `requirements.txt` into the repo so install is reproducible.
- **Test the `Auditor` class directly.** Today we cover `axe_runner`, `llm_client` shape, and the regression gate. `auditor.audit` is exercised only end-to-end via fixtures. Add a unit test that injects a `MockClient` and a fake violation list.

## Later

- **Batch mode.** A single `wcag-auditor batch fixtures/` that takes a directory and emits one combined report. Avoids the bash for-loop in the README.
- **Multiple LLM providers.** The `LLMClientProtocol` seam exists; we just don't use it. Add `LMStudioClient` or `LocalAIClient` once someone asks. No cloud APIs (see Won't-do).
- **Custom rule packs.** axe lets you register custom rules at runtime. Expose a CLI flag to load a JS file. Useful for in-house WCAG interpretations.
- **JUnit / SARIF output.** Shell out from `--output json` users today. SARIF would make GitHub code-scanning take it natively.
- **Caching of LLM fixes.** Same violation, same context, same fix. A content-addressed cache by (rule_id, html_hash) saves Ollama calls. Probably a sqlite table next to `audits`.

## Won't-do

These are explicit. Saying no is part of the design.

- **Microservices.** This is a CLI. One process, one lifetime, six modules. Splitting into services adds RPC, deployment, and observability for zero user-visible gain. The boring tech wins.
- **Kubernetes / Helm chart / operator.** Wrong shape entirely. If you want to run this at scale, run it in a job runner with a real result store. We will not own a k8s component.
- **GraphQL API.** No API. There's a CLI and a SQLite file. If you want a server, write one against the SQLite file.
- **Cloud LLM backends (OpenAI, Anthropic).** Local-only by design. Adds dependency on a paid API and ships node HTML to a third party. Hard line.
- **Auto-applying fixes to the source file.** A11y fixes are judgement calls; "it passes axe" is not the same as "it works for users with assistive tech." We will only suggest.
- **LLM-as-judge in CI.** Flaky, expensive, hard to reproduce. Deterministic structural metrics only.
- **Browser other than Chromium.** Three browsers triple Playwright surface for marginal coverage. axe behaves the same on all of them.
- **A web UI.** Out of scope. If someone wants one, they can read the JSON output and build it.
