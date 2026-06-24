#!/usr/bin/env bash
# install-hooks.sh — opt-in installer for Clipman's local git hooks.
#
# Run once after cloning if you want the local guardrails (identity
# denylist + AI-footprint scanner). External contributors do NOT need
# to run this; the CI does not require it; nothing about your workflow
# breaks if you skip it.
#
# Re-running is safe (idempotent).

set -euo pipefail

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
    printf '         Press ENTER to continue, Ctrl-C to abort.\n' >&2
    read -r _
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

cat <<'EOF'
✓ Clipman local hooks installed.

What this enabled:
  • commit-msg : aborts commits whose message contains an AI/Claude footprint
                 OR a trailer (Co-Authored-By:, Signed-off-by:, etc.) citing
                 a denied account
  • pre-commit : aborts if your git identity is on the personal denylist,
                 or if the staged diff *adds* an AI footprint to a tracked
                 file (skips paths in HOOKS_PATH_ALLOWLIST, e.g. docs/hooks.md)
  • pre-push   : per-commit final check before commits leave the machine,
                 including a scan of diff additions (catches binaries +
                 commits made outside this hook chain)

Denied account names (override via CLIPMAN_HOOKS_DENY="..."):
  mammar97, salmaamr129

Uninstall:
  git config --unset core.hooksPath

Bypass once (NOT recommended):
  git commit --no-verify
  git push   --no-verify

Verify:
  .githooks/_test.sh
EOF
