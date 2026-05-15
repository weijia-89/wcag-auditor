# wcag-auditor

[![CI](https://github.com/weijia-89/wcag-auditor/actions/workflows/ci.yml/badge.svg)](https://github.com/weijia-89/wcag-auditor/actions/workflows/ci.yml)

The standard WCAG workflow is: run axe-core, read the violation ID, look up the criterion, figure out what to actually change. This shortens the last step. Playwright injects axe-core into the page; violations come back as structured objects; each one goes through a per-rule fix engine (`RuleEngine`) that returns a hand-written fix template for that axe rule ID, with selector, suggested HTML, and a plain-language explanation. Pydantic validates the output before it hits your terminal. HTML stays on your machine.

The 0.2.x line ran each violation through a local Ollama LLM. The 0.3.0 release replaced that with deterministic per-rule templates for two reasons. First, against the curated fixture set, the templates were already accurate enough that the LLM call wasn't adding signal. Second, a deterministic engine removes the network surface, the prompt-injection class, and the model-dependent CI variance that came with running a local model. The trade is real: fix quality is now bounded by what's in the template set rather than by model capability. For axe rules outside that set, a generic fallback runs; the report still surfaces the violation, with less-specific remediation text.

The fixes don't apply themselves. That's intentional.

axe-core catches roughly 30-40% of WCAG 2.2 issues. This doesn't change that number. It makes the 30-40% faster to act on, which is a different and more honest thing to claim.

Results land in a SQLite history at `~/.local/share/wcag-auditor/audits.db`. That's it. No account, no sync, no SaaS dashboard with usage metrics, just a local file you can query yourself if you want to.

## Install

```bash
make install
make download-axe # fetches the axe-core bundle (SHA256-pinned)
```

No external model server required. The fix engine is deterministic and runs in-process.

## Usage

```bash
# local file
wcag-auditor audit path/to/page.html

# URL
wcag-auditor audit https://example.com

# JSON out
wcag-auditor audit page.html --output json > results.json

# loop a directory
for f in tests/fixtures/html/*.html; do wcag-auditor audit "$f"; done

# don't write to the DB
wcag-auditor audit page.html --no-save

# CI-friendly: no browser required (uses .axe.json sidecar if present)
WCAG_MOCK_AXE=1 wcag-auditor audit tests/fixtures/html/missing_alt_001.html
```

History:

```bash
wcag-auditor history # 20 most recent
wcag-auditor history --limit 50
wcag-auditor report 3 # one report
wcag-auditor report 3 --output json
```

## Env vars

| Var | What it does |
|-----|--------------|
| `WCAG_MOCK_AXE=1` | Skip Playwright + axe. Use a `.axe.json` sidecar next to the HTML if present. |
| `WCAG_DB_PATH` | Override the SQLite path. |
| `WCAG_ALLOW_FILE_OUTSIDE_CWD=1` | Let local paths escape the cwd subtree. Default: blocked. |
| `WCAG_ALLOW_LOCALHOST=1` | Let `localhost` / `127.0.0.1` URLs through the SSRF guard. |
| `WCAG_ALLOW_PRIVATE_NET=1` | Let RFC1918 hosts through. Cloud metadata (169.254/16) stays blocked. |
| `WCAG_NO_SANDBOX=1` | Launch Chromium with `--no-sandbox`. Required in Docker; risky on a laptop. |

## Troubleshooting

**`playwright: command not found`**
Run `make install` or `uv run playwright install chromium --with-deps`.

**`axe-core not installed`**
Run `make download-axe`. The tool refuses to load axe from a CDN because file:// pages block remote scripts.

**`No module named wcag_auditor`**
`uv sync`, then `uv run wcag-auditor` or activate the venv.

**`Refusing to fetch ... loopback address`**
The SSRF guard tripped. Set `WCAG_ALLOW_LOCALHOST=1` if you really meant it.

**`Refusing to read ... outside the current working directory`**
Set `WCAG_ALLOW_FILE_OUTSIDE_CWD=1` if you meant it. Otherwise move the fixture inside cwd.

**DB permission errors**
File lives at `~/.local/share/wcag-auditor/audits.db` with mode 0600. Override with `WCAG_DB_PATH=/somewhere/else.db`.

## Non-goals

- **No auto-applied fixes.** Suggestions only. You read them, you decide, you change the code.
- **No cloud, no model server.** Fix generation runs in-process via `RuleEngine`. The HTML never leaves your machine because nothing is sent anywhere.
- **Not a replacement for manual a11y testing.** axe-core is automated and catches roughly 30-40% of real-world WCAG issues. The rest requires keyboard navigation, screen reader passes, and a human who knows what they're doing. This tool doesn't pretend otherwise.
- **No CI reporter.** Pipe `--output json` into whatever you've got.
