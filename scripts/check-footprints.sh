#!/usr/bin/env bash
# check-footprints.sh — the pull-request side of the no-AI-attribution rule.
#
# Scans every commit in <base>..<head> (trailers, message, added lines) with
# the same checks the local git hooks use (.githooks/_lib.sh), plus the pull
# request's title and description when PR_TITLE / PR_BODY are set. Run by
# .github/workflows/footprints.yml on every pull request, so the rule holds
# for every contributor whether or not they installed the hooks.
#
# The description of a pull request opened by a bot (PR_AUTHOR_TYPE=Bot) is
# skipped: Dependabot quotes upstream release notes, which are not ours.
#
# Usage: scripts/check-footprints.sh <base-sha> <head-sha>

set -uo pipefail

cd "$(dirname -- "$0")/.." || exit 2

# shellcheck source=.githooks/_lib.sh
. .githooks/_lib.sh

usage="usage: $0 <base-sha> <head-sha>"
base="${1:?$usage}"
head="${2:?$usage}"

if ! commits=$(git rev-list --no-merges "$base..$head"); then
    hook_error "cannot list the commits in $base..$head"
    exit 2
fi

failed=0
count=0
while IFS= read -r sha; do
    [ -z "$sha" ] && continue
    count=$((count + 1))
    if ! scan_commit_content "$sha"; then
        failed=1
    fi
done <<<"$commits"

if [ -n "${PR_TITLE:-}" ] && ! printf '%s\n' "$PR_TITLE" | scan_footprints; then
    hook_error "the pull request title contains a footprint"
    failed=1
fi

if [ -n "${PR_BODY:-}" ] && [ "${PR_AUTHOR_TYPE:-}" != "Bot" ] \
        && ! printf '%s\n' "$PR_BODY" | scan_footprints; then
    hook_error "the pull request description contains a footprint"
    failed=1
fi

if [ "$failed" -ne 0 ]; then
    hook_section "AI-tool attribution found"
    hook_detail "This project keeps AI-tool attribution out of its history and its"
    hook_detail "pull requests: co-author trailers for AI assistants, 'Generated with'"
    hook_detail "notes, robot emoji. Using AI tools is fine; just remove the lines"
    hook_detail "above. Edit the pull request title or description, or reword the"
    hook_detail "commits (git rebase -i) and push again with --force-with-lease."
    exit 1
fi

hook_ok "no AI-tool footprints in $count commit(s), the title or the description"
exit 0
