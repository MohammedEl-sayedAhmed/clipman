#!/usr/bin/env bash
# _test.sh — run the corpus against the footprint scanner.
#
# The corpus (.githooks/_test_corpus.json) was produced by the research
# workflow and covers:
#   - 15 should_block: real footprints (canonical trailer, variants, emoji,
#     HTML entity escapes, etc.)
#   - 10 should_pass : borderline content that LOOKS like a footprint but
#     is legitimate (Claude Monet, anthropic.com URL in docs, etc.)
#   -  5 contributor_safe: commits from other open-source contributors
#     (their own emails, normal Signed-off-by, Reviewed-by trailers, etc.)
#
# This script only exercises the FOOTPRINT scanner via scan_footprints.
# Identity allowlist checks are deterministic substring matches and are
# unit-tested separately at the bottom of this script.

set -uo pipefail

cd "$(dirname "$0")"

# shellcheck source=.githooks/_lib.sh
. ./_lib.sh

CORPUS="${1:-_test_corpus.json}"
if ! [ -r "$CORPUS" ]; then
    printf 'usage: %s [path/to/_test_corpus.json]\n' "$0" >&2
    exit 2
fi

pass=0
fail=0
fail_lines=()

# Iterate over the JSON corpus. We need a JSON parser; prefer jq, fall back
# to python3 (always present alongside our app), so the harness works on a
# bare clone without root.
if command -v jq >/dev/null 2>&1; then
    parser=(jq -r 'to_entries[] | [(.key|tostring), .value.category, .value.expected_outcome, .value.reason, .value.input] | @tsv' "$CORPUS")
elif command -v python3 >/dev/null 2>&1; then
    parser=(python3 ./_test_parse.py "$CORPUS")
else
    printf 'this script requires jq or python3\n' >&2
    exit 2
fi

decode_input() {
    # Reverse the \n -> \\n escape we applied in the python parser. No-op for
    # the jq parser since @tsv strips newlines but we still escape for it.
    printf '%b' "$1"
}

while IFS=$'\t' read -r idx category outcome reason input; do
    input=$(decode_input "$input")
    # JSON-shaped inputs represent git-state, not commit messages — they
    # exercise identity logic, which is covered by the contains_allowed_identity
    # unit tests below. Skip from the message scanner.
    if [[ "$input" =~ ^[[:space:]]*\{.*\}[[:space:]]*$ ]]; then
        continue
    fi

    # Invoke the ACTUAL commit-msg hook so this harness validates real
    # behaviour, not a reimplementation. (DESIGN-01 fix.)
    tmpfile=$(mktemp)
    # Real git commit messages end with a trailing newline — mirror that
    # so hooks reading the message line-by-line don't miss the final line.
    printf '%s\n' "$input" > "$tmpfile"
    if ./commit-msg "$tmpfile" >/dev/null 2>&1; then
        actual=PASS
    else
        actual=BLOCK
    fi
    rm -f "$tmpfile"

    if [ "$actual" = "$outcome" ]; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        short="${input:0:100}"
        fail_lines+=("#$idx [$category] expected=$outcome got=$actual | ${short//$'\n'/ \\n }")
        fail_lines+=("    reason: $reason")
    fi
done < <("${parser[@]}")

# ----- Identity allowlist unit tests --------------------------------------

ident_tests=(
    # input | expect_match(1=allowed,0=blocked)
    "MohammedEl-sayedAhmed|1"
    "57391064+MohammedEl-sayedAhmed@users.noreply.github.com|1"
    "outside-account|0"
    "alice@example.com|0"
    "Mohammed Other (other@example.com)|0"
    "dependabot[bot]|0"
    "Random Stranger <stranger@example.com>|0"
)

for entry in "${ident_tests[@]}"; do
    input="${entry%|*}"
    expect="${entry##*|}"
    if contains_allowed_identity "$input"; then
        actual=1
    else
        actual=0
    fi
    if [ "$actual" = "$expect" ]; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        fail_lines+=("identity [$input] expected=$expect got=$actual")
    fi
done

# ----- Report -------------------------------------------------------------

echo
if [ "$fail" -eq 0 ]; then
    printf '%sALL TESTS PASS%s — %d/%d\n' "$_GRN$_BLD" "$_RST" "$pass" "$((pass+fail))"
    exit 0
else
    printf '%sFAILURES: %d/%d%s\n' "$_RED$_BLD" "$fail" "$((pass+fail))" "$_RST"
    for line in "${fail_lines[@]}"; do printf '  %s\n' "$line"; done
    exit 1
fi
