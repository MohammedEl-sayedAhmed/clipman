#!/usr/bin/env bash
# _test.sh — run the hooks corpus and unit tests against the real hooks.
#
# The corpus (.githooks/_test_corpus.json) has three categories:
#   - should_block    : real footprints (canonical trailer, variants, emoji,
#                       HTML entity escapes, ...) and wrong-account states
#   - should_pass     : borderline content that LOOKS like a footprint but
#                       is legitimate (Claude Monet, anthropic.com URL in
#                       docs, ...)
#   - contributor_safe: commits and clones of outside contributors (their
#                       own identities, normal Signed-off-by trailers, ...)
#
# A case whose input is a commit message runs through the real commit-msg
# hook. A case whose input is a JSON object describes a clone instead; it
# runs through the real pre-commit and pre-push hooks in a throwaway repo
# (see _test_scenario.py). The identity allowlist and the push-URL owner
# match are unit-tested at the bottom of this script.

set -uo pipefail

cd "$(dirname "$0")" || exit 2

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
    parser=(jq -r 'to_entries[] | [(.key|tostring), .value.category, .value.expected_outcome, (.value.expected_check // ""), .value.reason, .value.input] | @tsv' "$CORPUS")
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

while IFS=$'\t' read -r idx category outcome check reason input; do
    input=$(decode_input "$input")
    if [[ "$input" =~ ^[[:space:]]*\{.*\}[[:space:]]*$ ]]; then
        # A JSON object describes a clone, not a message: run the real
        # pre-commit and pre-push hooks against it in a throwaway repo.
        # BLOCK(<hook>) means the other hook refused it than the one the
        # case expects.
        if ! command -v python3 >/dev/null 2>&1; then
            actual="SKIPPED (python3 missing)"
        elif ! actual=$(python3 ./_test_scenario.py "$PWD" "$input" "$check" 2>&1); then
            actual="ERROR: ${actual//$'\n'/ }"
        fi
    else
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
    fi

    if [ "$actual" = "$outcome" ]; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        short="${input:0:100}"
        fail_lines+=("#$idx [$category] expected=$outcome got=$actual | ${short//$'\n'/ \\n }")
        fail_lines+=("    reason: $reason")
    fi
done < <("${parser[@]}")

# ----- Pull-request check (scripts/check-footprints.sh) --------------------
#
# The CI side of the footprint rule must block exactly what commit-msg
# blocks, plus footprints in added lines, the title and the description.
# _test_ci_scan.py prints mismatches, then "ci-scan <passed> <failed>".

if command -v python3 >/dev/null 2>&1; then
    ci_out=$(python3 ./_test_ci_scan.py "$PWD/.." 2>&1)
    ci_summary=$(printf '%s\n' "$ci_out" | tail -n 1)
    if [[ "$ci_summary" =~ ^ci-scan\ ([0-9]+)\ ([0-9]+)$ ]]; then
        pass=$((pass + BASH_REMATCH[1]))
        fail=$((fail + BASH_REMATCH[2]))
        while IFS= read -r line; do
            [ -n "$line" ] && fail_lines+=("$line")
        done < <(printf '%s\n' "$ci_out" | sed '$d')
    else
        fail=$((fail + 1))
        fail_lines+=("ci-scan did not run: ${ci_out//$'\n'/ }")
    fi
else
    fail=$((fail + 1))
    fail_lines+=("ci-scan skipped: python3 missing")
fi

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

# ----- Push-URL owner tests -----------------------------------------------

# The owner segment must match the allowlist exactly. A repo named after the
# owner under somebody else's account must not pass on a substring.
url_tests=(
    "git@github.com:MohammedEl-sayedAhmed/clipman.git|1"
    "https://github.com/MohammedEl-sayedAhmed/clipman.git|1"
    "ssh://git@github.com/MohammedEl-sayedAhmed/clipman.git|1"
    "git@github.com:attacker/MohammedEl-sayedAhmed-mirror.git|0"
    "https://github.com/attacker/MohammedEl-sayedAhmed.git|0"
    "https://user@github.com/OtherOrg/clipman.git|0"
    "https://github.com/MohammedEl-sayedAhmed-mirror/clipman.git|0"
)

for entry in "${url_tests[@]}"; do
    input="${entry%|*}"
    expect="${entry##*|}"
    if owner=$(push_url_owner "$input") && is_allowed_owner "$owner"; then
        actual=1
    else
        actual=0
    fi
    if [ "$actual" = "$expect" ]; then
        pass=$((pass+1))
    else
        fail=$((fail+1))
        fail_lines+=("push url [$input] expected=$expect got=$actual")
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
