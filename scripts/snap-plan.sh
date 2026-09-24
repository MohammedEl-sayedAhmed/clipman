#!/usr/bin/env bash
#
# Plan the snap-refresh matrix: which ref each build uses and which store
# channels it publishes to. .github/workflows/snap-refresh.yml runs this,
# and tests/test_snap_plan.py runs it with stand-ins for gh and curl.
#
# Environment:
#   EVENT              schedule, workflow_dispatch, push or pull_request
#   CHANNEL            the dispatch input: edge, beta, candidate or stable
#   GITHUB_REPOSITORY  owner/name, for the latest release lookup
#   GITHUB_OUTPUT      file that receives matrix=<json>
#   GH_TOKEN           read by gh
# Needs gh, curl and jq.

set -euo pipefail

# Print the latest release tag. Never fall back to main: an empty ref
# would publish main to stable.
latest_tag() {
    local tag
    tag=$(gh api "repos/${GITHUB_REPOSITORY}/releases/latest" -q .tag_name) || tag=""
    case "$tag" in
        v[0-9]*.[0-9]*.[0-9]*) printf '%s\n' "$tag" ;;
        *) echo "::error::could not resolve the latest release tag (got '${tag}')" >&2; return 1 ;;
    esac
}

# True when the store's stable channel already holds a version newer than
# $1. That happens when a release got as far as the store but not the
# GitHub Release: rebuilding the older tag would roll stable users back.
store_is_ahead() {
    local store
    store=$(curl -fsS -H 'Snap-Device-Series: 16' \
        'https://api.snapcraft.io/v2/snaps/info/clipman?fields=version' \
        | jq -r '.["channel-map"][]
                  | select(.channel.name == "stable" and .channel.architecture == "amd64")
                  | .version' | head -n 1) || store=""
    [ -n "$store" ] && [ "$store" != "${1#v}" ] &&
        [ "$(printf '%s\n%s\n' "$store" "${1#v}" | sort -V | tail -n 1)" = "$store" ]
}

case "${EVENT:?EVENT is not set}" in
    schedule)
        tag="$(latest_tag)" || exit 1
        if store_is_ahead "$tag"; then
            echo "::warning::the store's stable is newer than the latest GitHub Release ($tag): a release is half-finished. Rebuilding edge only, so stable is not rolled back."
            matrix='[{"ref": "main", "channels": "edge", "slug": "edge"}]'
        else
            matrix=$(jq -nc --arg tag "$tag" '[
                {ref: "main", channels: "edge",                    slug: "edge"},
                {ref: $tag,   channels: "beta,candidate,stable",   slug: "stable"}
            ]')
        fi
        ;;
    workflow_dispatch)
        channel="${CHANNEL:?CHANNEL is not set}"
        if [ "$channel" = "edge" ]; then
            ref="main"
        else
            ref="$(latest_tag)" || exit 1
            if store_is_ahead "$ref"; then
                echo "::error::the store's stable is newer than the latest GitHub Release ($ref): finish that release first, or this would roll $channel back."
                exit 1
            fi
        fi
        matrix=$(jq -nc --arg ref "$ref" --arg ch "$channel" \
            '[{ref: $ref, channels: $ch, slug: $ch}]')
        ;;
    *)
        # push / pull_request: build-only smoke of the triggering ref.
        matrix='[{"ref": "", "channels": "", "slug": "ci"}]'
        ;;
esac
echo "matrix=$matrix" >> "$GITHUB_OUTPUT"
echo "Planned: $matrix"
