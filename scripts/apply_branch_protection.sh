#!/usr/bin/env bash
# Apply GitHub branch protection on main. Default DRY_RUN=1.
# Requires GH_REPO=owner/name. Never stores tokens in this file.
# Live PUT requires APPLY=1 in environment (portfolio wave gate).
set -euo pipefail

GH_REPO="${GH_REPO:-weijia-89/wcag-auditor}"
DRY_RUN="${DRY_RUN:-1}"
BRANCH="${BRANCH:-main}"
OWNER="${GH_REPO%%/*}"
REPO="${GH_REPO##*/}"

if [[ "$OWNER" == "$REPO" || -z "$OWNER" || -z "$REPO" ]]; then
  echo "error: GH_REPO must be owner/repo, got: $GH_REPO" >&2
  exit 1
fi

PAYLOAD=$(cat <<EOFJSON
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
EOFJSON
)

echo "target: $GH_REPO branch=$BRANCH DRY_RUN=$DRY_RUN" >&2

# Dry-run unless DRY_RUN=0 exactly (truthy values like 01 must not reach live PUT).
if [[ "$DRY_RUN" != "0" ]]; then
  echo "DRY_RUN=1 — would PUT repos/$OWNER/$REPO/branches/$BRANCH/protection" >&2
  echo "$PAYLOAD" | python3 -m json.tool
  exit 0
fi

if [[ "${APPLY:-}" != "1" ]]; then
  echo "error: DRY_RUN=0 requires APPLY=1 in environment (portfolio wave gate)." >&2
  exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "error: gh not authenticated to github.com; run 'gh auth login' before DRY_RUN=0." >&2
  exit 1
fi

if ! gh repo view "$GH_REPO" --json nameWithOwner >/dev/null 2>&1; then
  echo "error: repo $GH_REPO not found or not visible; aborting (no PUT)." >&2
  exit 1
fi

echo "Applying protection to $GH_REPO ($BRANCH) …" >&2
gh api -X PUT "repos/${OWNER}/${REPO}/branches/${BRANCH}/protection" --input - <<<"$PAYLOAD"
echo "done — verify with: gh api repos/${OWNER}/${REPO}/branches/${BRANCH}/protection" >&2
