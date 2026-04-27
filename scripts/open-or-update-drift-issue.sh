#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 PR_NUMBER [DIFF_FILE]" >&2
  exit 2
fi

PR_NUMBER="$1"
DIFF_FILE="${2:-/tmp/readme-parity.out}"

if [[ -z "${GITHUB_TOKEN:-${GH_TOKEN:-}}" ]]; then
  echo "GITHUB_TOKEN/GH_TOKEN is not set; skipping drift issue update." >&2
  exit 0
fi

export GH_TOKEN="${GITHUB_TOKEN:-$GH_TOKEN}"

if [[ ! -f "$DIFF_FILE" ]]; then
  echo "diff file not found: $DIFF_FILE" >&2
  exit 2
fi

gh label create readme-translation-drift \
  --color d29922 \
  --description "Tracks README translation drift during the seven-day grace window" >/dev/null 2>&1 || true
gh label create readme-translation-backfill \
  --color 0969da \
  --description "Tracks required README translation backfill after an exemption" >/dev/null 2>&1 || true
gh label create docs-translation-exempt \
  --color d73a4a \
  --description "Exempts the PR from the README parity check; requires 30-day backfill follow-up issue per FR-602" >/dev/null 2>&1 || true

deadline="$(date -u -d '+7 days' '+%Y-%m-%dT%H:%M:%SZ')"
body_file="$(mktemp)"
backfill_body_file=""
trap 'rm -f "$body_file" "${backfill_body_file:-}"' EXIT

{
  echo "README translation drift was detected for PR #${PR_NUMBER}."
  echo
  echo "Grace deadline: ${deadline}"
  echo
  echo "Diff:"
  echo '```text'
  cat "$DIFF_FILE"
  echo '```'
  echo
  echo "Source PR: #${PR_NUMBER}"
} > "$body_file"

existing_issue="$(gh issue list \
  --label readme-translation-drift \
  --state open \
  --json number \
  --jq '.[0].number // empty')"

if [[ -n "$existing_issue" ]]; then
  gh issue edit "$existing_issue" \
    --title "README translation drift: PR #${PR_NUMBER}" \
    --body-file "$body_file" \
    --add-label readme-translation-drift >/dev/null
  echo "Updated README translation drift issue #${existing_issue}."
else
  created_url="$(gh issue create \
    --title "README translation drift: PR #${PR_NUMBER}" \
    --body-file "$body_file" \
    --label readme-translation-drift)"
  echo "Created README translation drift issue: ${created_url}"
fi

if gh pr view "$PR_NUMBER" --json labels --jq '.labels[].name' | grep -qx 'docs-translation-exempt'; then
  backfill_deadline="$(date -u -d '+30 days' '+%Y-%m-%dT%H:%M:%SZ')"
  backfill_body_file="$(mktemp)"
  {
    echo "PR #${PR_NUMBER} used the docs-translation-exempt label."
    echo
    echo "Translations must be backfilled by: ${backfill_deadline}"
    echo
    echo "Original parity output:"
    echo '```text'
    cat "$DIFF_FILE"
    echo '```'
  } > "$backfill_body_file"

  existing_backfill="$(gh issue list \
    --label readme-translation-backfill \
    --state open \
    --search "README translation backfill PR #${PR_NUMBER} in:title" \
    --json number \
    --jq '.[0].number // empty')"

  if [[ -n "$existing_backfill" ]]; then
    gh issue edit "$existing_backfill" \
      --title "README translation backfill (30-day SLA): PR #${PR_NUMBER}" \
      --body-file "$backfill_body_file" \
      --add-label readme-translation-backfill >/dev/null
    echo "Updated README translation backfill issue #${existing_backfill}."
  else
    created_backfill_url="$(gh issue create \
      --title "README translation backfill (30-day SLA): PR #${PR_NUMBER}" \
      --body-file "$backfill_body_file" \
      --label readme-translation-backfill)"
    echo "Created README translation backfill issue: ${created_backfill_url}"
  fi
fi
