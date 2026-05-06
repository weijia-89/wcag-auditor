# Security

This is a local CLI that pulls user-supplied URLs and files into a headless Chromium instance, injects axe-core, and pipes the violation list through a local LLM. Small attack surface. But real, and worth mapping explicitly before you point this at anything sensitive or run it in an environment where "headless browser with DOM execution" sounds alarming, because it should sound a little alarming, and the defaults are designed with that in mind.

## Reporting

Report: [GitHub Security Advisory](https://github.com/weijia-89/wcag-auditor/security/advisories/new)

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

A user who opts into every override at once (`WCAG_NO_SANDBOX=1`, `WCAG_ALLOW_FILE_OUTSIDE_CWD=1`, `WCAG_ALLOW_PRIVATE_NET=1`) is on their own. Each flag exists for a legitimate reason, Docker needs no-sandbox, tests need file access outside cwd, staging audits need private net. But combining all three against untrusted input in a single session is genuinely unsafe, and the README doesn't warn against it loudly enough.

The local LLM model itself is trusted. If you run a tampered Ollama model, fix suggestions can recommend bad HTML, though schema validation will still reject malformed shapes.

DNS rebinding against a public hostname that resolves to a private IP is not mitigated because we don't re-validate post-resolution. The practical mitigation is simple: don't set `WCAG_ALLOW_PRIVATE_NET=1` on machines that audit untrusted URLs.

## Env override rationale

Separate flags. Deliberate. A CI environment that needs no-sandbox shouldn't have to also accept private-net access to get there; each flag controls one boundary and only one, so you can enable exactly what your environment requires without dragging in the others.

- **`WCAG_ALLOW_FILE_OUTSIDE_CWD`**: for legitimate `tests/fixtures/...` paths in a sibling repo. Default off so `wcag-auditor audit /etc/...` just fails.
- **`WCAG_ALLOW_LOCALHOST`**: for `wcag-auditor audit http://localhost:3000` against your own dev server. Default off so a malicious link can't pivot the auditor onto your local-only services.
- **`WCAG_ALLOW_PRIVATE_NET`**: for scanning internal staging hosts. Default off so the SSRF guard catches the obvious cases. 169.254/16 (cloud metadata) is never allowed regardless.
- **`WCAG_NO_SANDBOX`**: Docker / CI need it; laptops don't. Default off because Chromium's sandbox is the only thing standing between a malicious page and the host. That's not a hyperbole.

## Reproducing the hardening tests

```bash
make test-unit
# Specifically:
pytest tests/unit/test_axe_runner.py::TestPathToUrlConfinement
pytest tests/unit/test_axe_runner.py::TestHttpUrlSsrfGuard
pytest tests/unit/test_llm_client.py::TestOllamaClientSizeCap
pytest tests/unit/test_check_regression.py::TestZeroBaselineGate
```
