# Security

This is a local CLI that pulls user-supplied URLs/files into a headless browser and pipes results through a local LLM. The interesting attack surface is small but real.

## Reporting

Email: wei_jia@intuit.com

Please don't open public issues for suspected security bugs. Give me 90 days before disclosure.

## Threat model

### Who could attack this

- Someone who hands you a malicious HTML file and asks you to audit it.
- Someone who hands you a malicious URL and asks you to audit it.
- A malicious model server impersonating Ollama on localhost.
- A package-supply attacker swapping out axe-core.
- Anyone with shell access to the machine running the auditor.

### What they could do, and what's mitigated

| Attack | Mitigation |
|--------|------------|
| `wcag-auditor audit /etc/shadow` reading host secrets via file:// | Local paths must resolve inside cwd. Override: `WCAG_ALLOW_FILE_OUTSIDE_CWD=1`. See `_path_to_url` / `_reject_if_outside_cwd`. |
| SSRF to cloud metadata (`http://169.254.169.254/`) | Always blocked. No env override exists. |
| SSRF to loopback / RFC1918 | Blocked by default. Opt in with `WCAG_ALLOW_LOCALHOST=1` or `WCAG_ALLOW_PRIVATE_NET=1`. |
| Browser sandbox escape from a malicious page | Chromium sandbox stays on by default. `--no-sandbox` is opt-in via `WCAG_NO_SANDBOX=1` or `--unsafe-no-sandbox`. |
| Prompt-injected LLM response that exhausts memory | Hard 64KB cap in `OllamaClient.generate_fix` before `json.loads`. |
| Modified `axe.min.js` shipping malicious JS | `scripts/download_axe.py` pulls a tagged release URL and SHA256-checks it; refuses to write on mismatch or unset hash. |
| DB world-readable on a shared host | Database is chmod'd to 0600 on every open in `_get_db`. |
| Audit output exposing scanned content via shared logs | History DB and reports stay local. Nothing is uploaded. |
| Untrusted input to `FixApplicabilityMetric` (writes temp HTML, launches browser) | Documented as DANGER in CLAUDE.md. Don't run on untrusted HTML. |

### What's NOT mitigated

- A user who opts into every override (`WCAG_NO_SANDBOX=1`, `WCAG_ALLOW_FILE_OUTSIDE_CWD=1`, `WCAG_ALLOW_PRIVATE_NET=1`) is on their own. The flags exist for a reason; the defaults exist for a bigger reason.
- The local LLM model itself is trusted. If you run a tampered Ollama model, fix suggestions can recommend bad HTML. Schema validation will still reject malformed shapes.
- DNS rebinding against a public hostname that resolves to a private IP. We do not re-validate post-resolution. Mitigation: don't `WCAG_ALLOW_PRIVATE_NET=1` on machines that audit untrusted URLs.

## Env override rationale

These are deliberately separate flags so a CI environment can opt into exactly what it needs.

- **`WCAG_ALLOW_FILE_OUTSIDE_CWD`**: for legitimate `tests/fixtures/...` paths in a sibling repo. Default off so `wcag-auditor audit /etc/...` just fails.
- **`WCAG_ALLOW_LOCALHOST`**: for `wcag-auditor audit http://localhost:3000` against your own dev server. Default off so a malicious link can't pivot the auditor onto your local-only services.
- **`WCAG_ALLOW_PRIVATE_NET`**: for scanning internal staging hosts. Default off so the SSRF guard catches the obvious cases. 169.254/16 (cloud metadata) is never allowed regardless.
- **`WCAG_NO_SANDBOX`**: Docker / CI need it; laptops don't. Default off because Chromium's sandbox is the only thing standing between a malicious page and the host.

## Reproducing the hardening tests

```bash
make test-unit
# Specifically:
pytest tests/unit/test_axe_runner.py::TestPathToUrlConfinement
pytest tests/unit/test_axe_runner.py::TestHttpUrlSsrfGuard
pytest tests/unit/test_llm_client.py::TestOllamaClientSizeCap
pytest tests/unit/test_check_regression.py::TestZeroBaselineGate
```
