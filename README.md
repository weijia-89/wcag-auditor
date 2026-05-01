# wcagAuditor

Scan an HTML file or URL for WCAG 2.2 violations with axe-core, then ask a local LLM (Ollama) to suggest a fix for each one. Results land in a SQLite history at `~/.local/share/wcag-auditor/audits.db`.

## Install

```bash
make install
ollama serve         # separate terminal
ollama pull llama3.1:8b
make download-axe    # fetches the axe-core bundle (SHA256-pinned)
```

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

# CI-friendly: no browser, no Ollama
MOCK_LLM=1 wcag-auditor audit tests/fixtures/html/missing_alt_001.html
```

History:

```bash
wcag-auditor history             # 20 most recent
wcag-auditor history --limit 50
wcag-auditor report 3            # one report
wcag-auditor report 3 --output json
```

## Env vars

| Var | What it does |
|-----|--------------|
| `MOCK_LLM=1` | Skip Playwright + Ollama. Use a `.axe.json` sidecar next to the HTML if present. |
| `WCAG_DB_PATH` | Override the SQLite path. |
| `WCAG_ALLOW_FILE_OUTSIDE_CWD=1` | Let local paths escape the cwd subtree. Default: blocked. |
| `WCAG_ALLOW_LOCALHOST=1` | Let `localhost` / `127.0.0.1` URLs through the SSRF guard. |
| `WCAG_ALLOW_PRIVATE_NET=1` | Let RFC1918 hosts through. Cloud metadata (169.254/16) stays blocked. |
| `WCAG_NO_SANDBOX=1` | Launch Chromium with `--no-sandbox`. Required in Docker; risky on a laptop. |

## Troubleshooting

**`playwright: command not found`**
Run `make install` or `uv run playwright install chromium --with-deps`.

**`Connection refused` from Ollama**
Start it: `ollama serve`. Check the model: `ollama list`.

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

- No auto-applied fixes. Suggestions only.
- No cloud API. Ollama is the only LLM backend.
- Not a replacement for manual a11y testing. axe-core catches roughly 30-40% of WCAG issues. Pair it with keyboard + screen-reader passes.
- No CI reporter. Pipe `--output json` into your own tooling.
