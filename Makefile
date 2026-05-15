.PHONY: install download-axe eval eval-full test-unit lint audit

install:
	uv sync
	uv run playwright install chromium --with-deps
	$(MAKE) download-axe

# B8: download-axe now goes through the SHA256-pinned script. The script
# fails closed if EXPECTED_SHA256 is the placeholder — populate it before
# the first real download.
download-axe:
	uv run python scripts/download_axe.py

eval:
	WCAG_MOCK_AXE=1 uv run pytest tests/eval/ -v \
	  --json-report --json-report-file=eval_results.json \
	  -k "not test_fix_accuracy and not test_hallucination and not test_criterion_accuracy"

eval-full:
	@echo "Requires: Playwright-installed Chromium. No model server needed since 0.3.0."
	uv run pytest tests/eval/ -v --json-report --json-report-file=eval_results_full.json

test-unit:
	uv run pytest tests/unit/ -v

lint:
	uv run ruff check src/ tests/

check-regression:
	@uv run python -c "\
import json, sys; \
b = json.loads(open('eval_baseline.json').read()); \
vals = [v for k, v in b.items() if not k.startswith('_')]; \
is_zero = vals and all(v == 0.0 for v in vals); \
print('WARNING: eval_baseline.json is all-zeros. Run \"make eval-full\" against the curated fixtures first to generate a meaningful baseline. Regression gate is SKIPPING (not failing) until baseline is populated.', file=sys.stderr) if is_zero else None; \
sys.exit(3) if is_zero else None"  || [ $$? -eq 3 ] && exit 0
	uv run python scripts/check_regression.py \
	  --results eval_results.json \
	  --baseline eval_baseline.json \
	  --max-drop 0.05 \
	  --ci

# Supply-chain audit. Assumes pip-audit is installed (e.g. `uv tool install pip-audit`).
# Tip: combine with `uv lock` for hash-pinned reproducible deps.
audit:
	pip-audit
