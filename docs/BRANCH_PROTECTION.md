# Branch protection (`main`)

GitHub rules for **wcag-auditor** (`weijia-89/wcag-auditor`). Apply only after the remote exists and the operator confirms `GH_REPO`.

**Default target:** `weijia-89/wcag-auditor` (set explicitly; never assume from cwd alone).

## Current state (2026-05-25)

| Check | Result |
| ----- | ------ |
| Default branch | `main` |
| Classic branch protection GET | **404** — not configured |
| Active repository rulesets | **none** (`[]`) |
| CI workflows | **CI** (`.github/workflows/ci.yml`, job `test`) |

`main` is currently **unprotected**. Direct pushes and force-pushes are allowed until protection is applied.

## Policy (script / recommended)

| Rule | Setting | Notes |
| ---- | ------- | ----- |
| Default branch | `main` | Confirmed via `gh repo view weijia-89/wcag-auditor`. |
| Require PR before merge | yes | Direct pushes to `main` blocked once protection is on. |
| Require approvals | 1 (script default) | See [Solo maintainer tradeoff](#solo-maintainer-tradeoff). |
| Dismiss stale reviews | yes | New commits invalidate prior approvals. |
| Require conversation resolution | yes | Unresolved review threads block merge. |
| Require linear history | optional (off in script) | Enable if you squash-merge only and want a straight line. |
| Force pushes | block on `main` | Aligns with safetybar: no `--force` to shared default branch. |
| Branch deletions | block on `main` | Prevents accidental removal of the default branch. |
| Enforce for admins | off (default) | Repo admins can bypass classic rules; turn on if you want rules to bind you too. |
| Required status checks | none (placeholder) | Add when CI gate is required — see [Status checks (future)](#status-checks-future). |

## Solo maintainer tradeoff

With **required approving review count = 1**, GitHub expects someone other than the PR author to approve. On a solo personal repo that usually means:

- **Option A (strict):** keep `required_approving_review_count: 1` and use a second account, bot, or org rule exception — merges stay review-gated.
- **Option B (pragmatic solo):** set count to `0` but keep **require PR** + stale dismissal + conversation resolution — you still open a PR for audit trail, but you can merge without a second human.
- **Option C:** use GitHub's "Allow specified actors to bypass required pull requests" (if available on your plan) for your user only — document who is on that list.

The bundled script defaults to **count = 1** (recommended policy table). Lower it in the JSON payload before apply if you choose Option B.

## Prerequisites

1. Remote repo exists: `gh repo view "$GH_REPO"`.
2. `gh` authenticated to **github.com** (not only an enterprise host): `gh auth status`.
3. Default branch is `main` (or edit the script branch name).
4. Operator confirms **`GH_REPO=owner/name`** matches the intended repo (safetybar — wrong repo PUT is hard to undo cleanly).
5. For live apply: set **`APPLY=1`** in the environment before `DRY_RUN=0`.

## Apply via script (preferred)

From repo root (SDK stub or product clone):

```bash
cd ~/Projects/wcag-auditor   # or SDK stub cwd
export GH_REPO=weijia-89/wcag-auditor

# Dry run (default) — prints JSON only
./scripts/apply_branch_protection.sh

# Apply (only after repo exists + operator intent + APPLY=1)
APPLY=1 DRY_RUN=0 ./scripts/apply_branch_protection.sh
```

The script is idempotent when classic protection is in use: repeated `APPLY=1 DRY_RUN=0` runs send the same PUT payload. It refuses apply if `gh repo view` fails or `APPLY=1` is unset.

## Manual UI steps

1. Open `https://github.com/weijia-89/wcag-auditor/settings/branches`.
2. Add a branch protection rule for `main` (or create a ruleset under **Settings → Rules → Rulesets**).
3. Enable:
   - **Require a pull request before merging**
   - **Require approvals** (1, or 0 for solo — see tradeoff)
   - **Dismiss stale pull request approvals when new commits are pushed**
   - **Require conversation resolution before merging**
4. Disable **Allow force pushes** and **Allow deletions**.
5. Leave **Require status checks** empty until CI is required as a merge gate.
6. Save changes.

## `gh api` commands

Inspect classic protection (404 = not configured):

```bash
export GH_REPO=weijia-89/wcag-auditor
OWNER="${GH_REPO%%/*}"
REPO="${GH_REPO##*/}"

gh api "repos/${OWNER}/${REPO}/branches/main/protection" 2>&1 || true
```

Dry-run payload (same as script):

```bash
DRY_RUN=1 GH_REPO=weijia-89/wcag-auditor ./scripts/apply_branch_protection.sh
```

Apply classic protection (requires repo + admin + `APPLY=1`):

```bash
APPLY=1 DRY_RUN=0 GH_REPO=weijia-89/wcag-auditor ./scripts/apply_branch_protection.sh
```

Equivalent one-shot PUT (requires `APPLY=1` gate if using the script):

```bash
export GH_REPO=weijia-89/wcag-auditor
OWNER="${GH_REPO%%/*}"
REPO="${GH_REPO##*/}"

gh api -X PUT "repos/${OWNER}/${REPO}/branches/main/protection" --input - <<'EOF'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true
}
EOF
```

## Status checks (future)

CI workflow **CI** (`.github/workflows/ci.yml`, job id `test`) runs on push/PR to `main`. To require it before merge, extend the script payload or ruleset.

<!-- sdk-review F1: GitHub reports Actions checks as "workflow / job", not bare job id — wrong context blocks merges indefinitely. -->

**Do not guess the context string.** GitHub Actions usually exposes the check as **`CI / test`** (workflow `name:` + job id), not `"test"` alone. Before enabling `required_status_checks`, copy the exact label from a **green** PR:

- GitHub UI: PR → **Checks** tab → use the full check name shown there.
- CLI: `gh pr checks <number> --repo "$GH_REPO"` (or open a PR and run without `<number>` on the current branch).

Example payload after you have verified the name on a real PR:

```json
"required_status_checks": {
  "strict": true,
  "contexts": ["CI / test"]
}
```

Replace `"CI / test"` with whatever your PR actually shows if GitHub renames the workflow or job. Until then, `required_status_checks` stays `null` so merges are not blocked on missing or mismatched check names.

## Git workflow after protection

- Work on feature branches; open PRs into `main`.
- **Do not** `git push --force` to `main` (blocked by protection; also disallowed by project policy).
- To undo a bad merge on `main`, use **revert commits**, not force-push.

## Related

- `README.md` — repo overview and usage
- `CHANGELOG.md` — release history
- `.github/workflows/ci.yml` — lint + unit tests on push/PR
- `scripts/apply_branch_protection.sh` — classic REST automation with `DRY_RUN=1` default
