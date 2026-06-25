#!/usr/bin/env bash
# Shared helpers for Clipman's local git hooks.
#
# These hooks are LOCAL ONLY. They are not part of CI and do not block other
# contributors' pull requests. They exist so the repo owner can catch two
# specific classes of mistake before they leave the machine:
#
#   1. Wrong GitHub account active when committing/pushing.
#   2. AI-tool footprints (Claude / Anthropic / generic LLM attributions)
#      ending up in commit messages or staged content.
#
# Hooks are opt-in: run scripts/install-hooks.sh to enable. External
# contributors are unaffected (denylist is two specific usernames; pattern
# scanner is universal but tuned to avoid common false positives like
# "Claude Monet" or anthropic.com appearing as a URL in citations).
#
# Known limitations (see docs/hooks.md):
#   - Unicode-obfuscated footprints (ZWSP, homoglyphs, NBSP) are NOT caught
#     by the ASCII regex set. The threat model is user-error, not a
#     deliberate adversary smuggling text past their own hook.
#   - `gh pr merge` and GitHub web/Desktop merges never invoke pre-push.

set -uo pipefail

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

if [ -t 2 ]; then
    _RED=$'\033[31m'; _YEL=$'\033[33m'; _GRN=$'\033[32m'
    _DIM=$'\033[2m';  _BLD=$'\033[1m';  _RST=$'\033[0m'
else
    _RED=""; _YEL=""; _GRN=""; _DIM=""; _BLD=""; _RST=""
fi

hook_error()   { printf '%s[hooks] ERROR%s %s\n' "$_RED$_BLD" "$_RST" "$*" >&2; }
hook_warn()    { printf '%s[hooks] WARN%s  %s\n' "$_YEL"     "$_RST" "$*" >&2; }
hook_ok()      { printf '%s[hooks] OK%s    %s\n' "$_GRN"     "$_RST" "$*" >&2; }
hook_detail()  { printf '%s          %s%s\n'     "$_DIM"     "$*"    "$_RST" >&2; }
hook_section() { printf '\n%s[hooks] %s%s\n' "$_BLD" "$*" "$_RST" >&2; }

# ---------------------------------------------------------------------------
# Path allowlist: files whose content legitimately references the patterns
# (these docs/scripts BY DESIGN contain example footprints). The staged-diff
# scanner skips these paths.
# ---------------------------------------------------------------------------

HOOKS_PATH_ALLOWLIST=(
    "docs/hooks.md"
    ".githooks/_lib.sh"
    ".githooks/_test.sh"
    ".githooks/_test_parse.py"
    ".githooks/_test_corpus.json"
    ".githooks/commit-msg"
    ".githooks/pre-commit"
    ".githooks/pre-push"
    "scripts/install-hooks.sh"
)

is_path_allowlisted() {
    local p="$1"
    local entry
    for entry in "${HOOKS_PATH_ALLOWLIST[@]}"; do
        [ "$p" = "$entry" ] && return 0
    done
    return 1
}

# ---------------------------------------------------------------------------
# Identity allowlist: the only account(s) allowed to commit/push from this
# clone after the local hooks are installed.
# ---------------------------------------------------------------------------
#
# Default whitelist holds only the repo owner's personal account. Override
# via env: CLIPMAN_HOOKS_ALLOW="login1 login2"  (space-separated usernames).
# Empty/whitespace values restore the safe default rather than turning the
# check off — there is no "off" without setting CLIPMAN_HOOKS_BYPASS=1 (one
# of the matched patterns must be present).
#
# Match is case-insensitive substring against:
#   - git user.name / user.email
#   - GIT_AUTHOR_NAME/_EMAIL, GIT_COMMITTER_NAME/_EMAIL env vars
#   - GIT_AUTHOR_IDENT, GIT_COMMITTER_IDENT (the post-override truth)
#   - the gh-CLI active login (best-effort, not blocking when gh missing)
#   - commit-trailer values on per-commit scans

HOOKS_ALLOW_DEFAULT=("MohammedEl-sayedAhmed")

_resolve_allowlist() {
    local raw="${CLIPMAN_HOOKS_ALLOW-}"
    # Trim whitespace
    raw="${raw#"${raw%%[![:space:]]*}"}"
    raw="${raw%"${raw##*[![:space:]]}"}"
    if [ -z "$raw" ]; then
        HOOKS_ALLOW=("${HOOKS_ALLOW_DEFAULT[@]}")
    else
        # shellcheck disable=SC2034
        read -r -a HOOKS_ALLOW <<<"$raw"
    fi
}
_resolve_allowlist

# Returns 0 if $1 contains ANY allowed account (case-insensitive substring).
# Tokens shorter than 4 chars are skipped to avoid false-positives on
# common short fragments inside real names.
contains_allowed_identity() {
    local needle="${1,,}"
    local allow
    for allow in "${HOOKS_ALLOW[@]}"; do
        [ -z "$allow" ] && continue
        [ "${#allow}" -lt 4 ] && continue
        if [[ "$needle" == *"${allow,,}"* ]]; then
            return 0
        fi
    done
    return 1
}

allowed_list_for_message() {
    local IFS=", "
    printf '%s' "${HOOKS_ALLOW[*]}"
}

# ---------------------------------------------------------------------------
# Trailer-identity allowlist
# ---------------------------------------------------------------------------
#
# Background: ``contains_allowed_identity`` (above) is used to validate the
# author/committer of an outgoing commit. It's also tempting to apply it
# to ``Co-Authored-By:`` / ``Signed-off-by:`` / ``Reviewed-by:`` trailers,
# but those routinely carry external contributor names + emails when this
# repo accepts patches from the wider world. Plain-allowlist would reject
# legitimate external co-authors.
#
# This function takes a more nuanced position: it returns 0 if the trailer
# email is from a class of identities we KNOW are safe to surface — the
# repo owner's allowlisted handles, GitHub's privacy-alias noreplies
# (which are bound to a real GitHub account, so any leak there is
# already that account's choice to expose), and the canonical bot
# noreplies (dependabot, github-actions, etc).
#
# Anything else — including human emails on personal/work domains — is
# rejected. This forces commit messages to use the privacy-alias form
# of an email rather than the raw domain, which is what GitHub itself
# recommends in its "Setting your commit email address" docs.
#
# Designed as a positive policy: there are no per-domain deny patterns
# baked into this file, so the source doesn't track any specific
# identity that we'd rather not appear in the repo.
is_safe_trailer_email() {
    local email="${1,,}"
    [ -z "$email" ] && return 1

    # GitHub privacy-alias noreply addresses (any user, any bot).
    # Pattern: <numericid>+<login>@users.noreply.github.com  OR  <login>@users.noreply.github.com
    if [[ "$email" =~ ^([0-9]+\+)?[a-z0-9._-]+(\[bot\])?@users\.noreply\.github\.com$ ]]; then
        return 0
    fi

    # GitHub's web-flow merge identity (used on web-merged squashes).
    if [[ "$email" == "noreply@github.com" ]]; then
        return 0
    fi

    # Allowlisted handles, matched against the local-part of the address
    # (the bit before '@'). Same case-insensitive substring rule as
    # contains_allowed_identity.
    local local_part="${email%@*}"
    local allow
    for allow in "${HOOKS_ALLOW[@]}"; do
        [ -z "$allow" ] && continue
        [ "${#allow}" -lt 4 ] && continue
        if [[ "$local_part" == *"${allow,,}"* ]]; then
            return 0
        fi
    done

    return 1
}

# Walk a commit message file's trailers and validate every identity-
# carrying trailer (Co-Authored-By, Signed-off-by, Reviewed-by, Tested-
# by, Helped-by, etc.) against is_safe_trailer_email. Echoes one error
# line per offending trailer; returns 0 if all clean, 1 otherwise.
scan_trailer_identities() {
    local msg_path="$1"
    [ -f "$msg_path" ] || return 0

    local bad=0
    while IFS=$'\t' read -r key value; do
        # Only key types that may carry person identity. Skip purely
        # informational ones like "Closes:", "Refs:", "Fixes:".
        case "${key,,}" in
            co-authored-by|signed-off-by|reviewed-by|tested-by|helped-by|reported-by|acked-by|cc)
                ;;
            *)
                continue
                ;;
        esac
        # Extract <email> from "Name <email>" trailer values.
        local email=""
        if [[ "$value" =~ \<([^>]+)\> ]]; then
            email="${BASH_REMATCH[1]}"
        else
            email="$value"
        fi
        if ! is_safe_trailer_email "$email"; then
            hook_error "trailer identity not allowed: ${key}: ${value}"
            hook_detail "  This repo only allows trailers carrying:"
            hook_detail "    - owner allowlist ($(allowed_list_for_message))"
            hook_detail "    - GitHub privacy-alias noreplies (id+login@users.noreply.github.com)"
            hook_detail "    - GitHub's web-flow merge identity (noreply@github.com)"
            hook_detail "  Use the GitHub privacy-alias form of the email instead."
            bad=1
        fi
    done < <(parse_message_trailers "$msg_path")

    return "$bad"
}

# ---------------------------------------------------------------------------
# Footprint scanner
# ---------------------------------------------------------------------------
#
# Tight ERE pattern set. Each line:  TAG | regex (case-insensitive)
#
# Designed to catch Claude Code's actual emitted footprints + common verb
# variants, without false-positives on "Claude Monet", anthropic.com URLs
# in docs, or Copilot/GPT mentions in unrelated contexts.

HOOKS_FOOTPRINT_PATTERNS=(
    # Canonical co-author trailers
    'co-author-claude       | co.?authored.?by[[:space:]:].*claude'
    'co-author-anthropic    | co.?authored.?by[[:space:]:].*anthropic'

    # Email addresses (requires <...> bracket OR explicit mail context to
    # avoid matching anthropic.com URLs in docs)
    'noreply-anthropic      | noreply@anthropic\.com'
    'email-anthropic-brkt   | <[[:space:]]*[^>]*@anthropic\.com[[:space:]]*>'
    'email-anthropic-plain  | [[:space:]][a-z0-9._%+-]+@anthropic\.com\b'

    # Attribution verbs — broad list (BYPASS-06)
    'created-by-claude      | (created|written|authored|produced|made|built|implemented|developed|coded|drafted|crafted|forged|wrote|generated)[[:space:]]+(with|by|using|via)[[:space:]]+(\[)?claude'
    'created-by-anthropic   | (created|written|authored|produced|made|built|implemented|developed|coded|drafted|crafted|forged|wrote|generated)[[:space:]]+(with|by|using|via)[[:space:]]+(\[)?anthropic'

    # Other AI-attribution phrasings
    'powered-by-claude      | powered[[:space:]]+by[[:space:]]+(claude|anthropic)'
    'with-help-of-claude    | with[[:space:]]+(the[[:space:]]+)?(help|assistance)[[:space:]]+of[[:space:]]+(claude|anthropic)'

    # Trailer-style AI attribution (tight: only claude/anthropic, dropped
    # copilot/gpt due to FP-01 — those can be real human names or non-AI tools)
    'assisted-by-ai         | ^[[:space:]]*assisted.?by[[:space:]:].*(claude|anthropic)'
    'reviewed-by-ai         | ^[[:space:]]*reviewed.?by[[:space:]:].*(claude|anthropic)'
    'signoff-claude         | ^[[:space:]]*signed.?off.?by[[:space:]:].*<[^>]*@anthropic\.com>'

    # URLs — broad coverage (BYPASS-07)
    'url-claude-ai          | claude\.ai/(code|chat|new|agent|share|workspace|p)'
    'url-claude-com-product | claude\.com/(claude.?code|product|code|chat)'

    # Robot emoji + sneakier representations
    'robot-emoji-literal    | 🤖'
    'robot-emoji-htmlent    | &#(129302|x1F916|x1f916);'
    'robot-emoji-shortcode  | :robot_face:'
)

# Strip ZWSP/ZWNJ/ZWJ/BOM/word-joiner/soft-hyphen before scanning. This
# closes the easiest Unicode bypasses without a full NFKD pass (which
# would require Python in every hook). Implementable as a single sed for
# UTF-8 byte sequences.
_strip_invisibles() {
    # \xE2\x80\x8B  U+200B ZWSP
    # \xE2\x80\x8C  U+200C ZWNJ
    # \xE2\x80\x8D  U+200D ZWJ
    # \xEF\xBB\xBF  U+FEFF BOM
    # \xE2\x81\xA0  U+2060 WORD JOINER
    # \xC2\xAD      U+00AD SOFT HYPHEN
    # \xC2\xA0      U+00A0 NBSP  → collapse to plain space
    sed -e $'s/\xE2\x80\x8B//g; s/\xE2\x80\x8C//g; s/\xE2\x80\x8D//g' \
        -e $'s/\xEF\xBB\xBF//g; s/\xE2\x81\xA0//g; s/\xC2\xAD//g' \
        -e $'s/\xC2\xA0/ /g'
}

# Scan stdin (or a file given as $1) for footprint patterns.
# Returns 0 if clean, 1 if any pattern matched.
scan_footprints() {
    local input
    if [ "$#" -ge 1 ] && [ -n "${1:-}" ]; then
        if ! [ -r "$1" ]; then return 0; fi
        input=$(cat -- "$1")
    else
        input=$(cat)
    fi
    [ -z "$input" ] && return 0

    # Strip invisible characters before pattern matching
    input=$(printf '%s' "$input" | _strip_invisibles)

    local hit=0
    local entry tag pattern matches
    for entry in "${HOOKS_FOOTPRINT_PATTERNS[@]}"; do
        tag="${entry%%|*}"
        tag="${tag// /}"
        pattern="${entry#*|}"
        pattern="${pattern# }"
        if matches=$(printf '%s' "$input" | grep -niE -- "$pattern" 2>/dev/null); then
            if [ -n "$matches" ]; then
                if [ "$hit" -eq 0 ]; then
                    hook_error "AI/Claude footprint detected:"
                fi
                hit=1
                printf '  %s[%s]%s\n' "$_DIM" "$tag" "$_RST" >&2
                while IFS= read -r line; do
                    printf '    %s%s%s\n' "$_DIM" "$line" "$_RST" >&2
                done <<<"$matches"
            fi
        fi
    done

    return "$hit"
}

# Parse trailers from a commit-message file via git's own RFC-2822 logic.
# Outputs one TAB-separated key\tvalue per line. Handles folded trailers
# and leading whitespace (BYPASS-08, BYPASS-09).
parse_message_trailers() {
    local msg_path="$1"
    [ -r "$msg_path" ] || return 0
    git interpret-trailers --parse --no-divider < "$msg_path" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Identity sources
# ---------------------------------------------------------------------------

collect_local_identities() {
    {
        git config user.name 2>/dev/null
        git config user.email 2>/dev/null
        printf '%s\n' "${GIT_AUTHOR_NAME:-}" \
                     "${GIT_AUTHOR_EMAIL:-}" \
                     "${GIT_COMMITTER_NAME:-}" \
                     "${GIT_COMMITTER_EMAIL:-}" \
                     "${EMAIL:-}"
        git var GIT_AUTHOR_IDENT 2>/dev/null
        git var GIT_COMMITTER_IDENT 2>/dev/null
    } | sed '/^$/d'
}

collect_push_urls() {
    {
        git remote get-url --push origin 2>/dev/null
        git config --get remote.origin.url 2>/dev/null
        git config --get remote.origin.pushurl 2>/dev/null
        git config --get-regexp '^url\..*\.(insteadof|pushinsteadof)$' 2>/dev/null \
            | awk '{print $2}'
    } | sed '/^$/d'
}

gh_active_login() {
    command -v gh >/dev/null 2>&1 || return 0
    gh api user -q .login 2>/dev/null || true
}
