#!/usr/bin/env bash
# install-hooks.sh — opt-in installer for the repo's local git hooks (identity allowlist + footprint scanner); safe to re-run.
# CI never needs them. --replace takes over a foreign core.hooksPath without prompting.
# The identity checks run only in the maintainer's clone: the mode follows the
# clone's git identity unless --maintainer or --contributor says otherwise.
# With no identity set yet, the mode is left to the hooks (origin decides).

set -euo pipefail

usage="usage: $0 [--replace] [--maintainer|--contributor]"
replace=0
mode=""
for arg in "$@"; do
    case "$arg" in
        --replace) replace=1 ;;
        --maintainer) mode=maintainer ;;
        --contributor) mode=contributor ;;
        -h|--help)
            printf '%s\n' "$usage"
            exit 0
            ;;
        *)
            printf 'error: unknown argument "%s" (%s)\n' "$arg" "$usage" >&2
            exit 2
            ;;
    esac
done

cd "$(dirname -- "$0")/.."

if [ ! -d .githooks ]; then
    printf 'error: .githooks/ not found (run from repo root or via "scripts/install-hooks.sh")\n' >&2
    exit 1
fi

# Warn if another hooks framework already owns core.hooksPath (Husky,
# lefthook, pre-commit, monorepo wrappers) — silently overwriting that
# would be confusing.
existing=$(git config --get core.hooksPath 2>/dev/null || true)
if [ -n "$existing" ] && [ "$existing" != ".githooks" ]; then
    printf 'warning: core.hooksPath is currently set to "%s"\n' "$existing" >&2
    printf '         Installing Clipman hooks will REPLACE that setting.\n' >&2
    if [ "$replace" -eq 1 ]; then
        printf '         --replace given; proceeding.\n' >&2
    elif [ -t 0 ]; then
        printf '         Press ENTER to continue, Ctrl-C to abort.\n' >&2
        read -r _
    else
        printf '         Not a terminal, so nothing was changed. Re-run with --replace\n' >&2
        printf '         to take over core.hooksPath, or chain your hook manager to\n' >&2
        printf '         "%s/.githooks" instead.\n' "$PWD" >&2
        exit 1
    fi
fi

# Make all hook files executable
chmod +x .githooks/* 2>/dev/null || true

# Point this clone's git at .githooks/ instead of .git/hooks/
git config core.hooksPath .githooks

# Sanity check: hooks executable
if [ ! -x .githooks/pre-commit ] || [ ! -x .githooks/commit-msg ] || [ ! -x .githooks/pre-push ]; then
    printf 'error: hooks not executable after chmod\n' >&2
    exit 1
fi

# Record the mode so the hooks don't have to guess. The account checks are
# for the maintainer's clone only; everyone keeps the footprint checks.
if [ -z "$mode" ]; then
    ident="$(git config user.name 2>/dev/null || true)$(git config user.email 2>/dev/null || true)"
    # shellcheck disable=SC2016  # $1 expands in the child shell
    if [ -z "$ident" ]; then
        mode=auto
    elif bash -c '. .githooks/_lib.sh && contains_allowed_identity "$1"' _ "$ident"; then
        mode=maintainer
    else
        mode=contributor
    fi
fi
case "$mode" in
    maintainer)
        git config clipman.hooks.maintainer true
        mode_line="maintainer: the account checks are on"
        ;;
    contributor)
        git config clipman.hooks.maintainer false
        mode_line="contributor: the account checks are off (they are for the maintainer's clone)"
        ;;
    *)
        git config --unset clipman.hooks.maintainer 2>/dev/null || true
        mode_line="not set: no git identity yet, so origin decides; set your identity and re-run to pin it"
        ;;
esac

printf '✓ Clipman local hooks installed. Mode: %s.\n' "$mode_line"
cat <<'EOF'

What this enabled:
  • commit-msg : aborts commits whose message contains an AI/Claude footprint,
                 or a trailer (Co-Authored-By:, Signed-off-by:, etc.) from an
                 AI-assistant domain or borrowing the maintainer's handle
  • pre-commit : aborts if the staged diff *adds* an AI footprint to a tracked
                 file (skips paths in HOOKS_PATH_ALLOWLIST, e.g. docs/hooks.md);
                 in maintainer mode, also if your git identity is not on the
                 allowlist
  • pre-push   : per-commit final check before commits leave the machine,
                 including a scan of diff additions; in maintainer mode it also
                 checks the push URL, the gh account and each commit's author

Allowed account names (override via CLIPMAN_HOOKS_ALLOW="..."):
  MohammedEl-sayedAhmed

Change the mode:
  git config clipman.hooks.maintainer true|false

Uninstall:
  git config --unset core.hooksPath

Bypass once (NOT recommended):
  git commit --no-verify
  git push   --no-verify

Verify:
  .githooks/_test.sh
EOF
