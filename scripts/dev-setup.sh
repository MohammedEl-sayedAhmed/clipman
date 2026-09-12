#!/usr/bin/env bash
#
# Idempotent dev bootstrap: system packages, .venv (--system-site-packages)
# with the dev extras, git hooks, identity check.
# Env: CLIPMAN_PYTHON (default python3); CLIPMAN_NO_NETWORK=1 skips PyPI.

set -euo pipefail

ROOT="$(cd "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() {
    printf 'setup: %s\n' "$*" >&2
}

step() {
    printf '\n== %s\n' "$*" >&2
}

notices=()

# 1. System packages
step "System packages (scripts/deps.sh --dev --install)"
deps_rc=0
scripts/deps.sh --dev --install || deps_rc=$?
case "$deps_rc" in
    0) ;;
    3)
        log "system packages could not be installed without a password; the command"
        log "to run is printed above. Continuing with the remaining steps."
        notices+=("System packages: run the sudo command printed by scripts/deps.sh, then re-run this script.")
        ;;
    *)
        log "warning: scripts/deps.sh exited with $deps_rc; continuing (the venv step may fail)"
        notices+=("System packages: scripts/deps.sh --dev --install failed (exit $deps_rc); re-run it after fixing the cause.")
        ;;
esac

# 2. Virtualenv
step "Virtualenv (.venv, --system-site-packages)"
PYTHON="${CLIPMAN_PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    log "error: interpreter '$PYTHON' not found"
    exit 1
fi
# Distro bindings older than 3.46, or a non-distro interpreter, make pip
# build PyGObject from source.
if ! "$PYTHON" -c 'import gi, sys; sys.exit(tuple(gi.version_info) < (3, 46))' 2>/dev/null; then
    log "warning: $PYTHON has no PyGObject >= 3.46 (Ubuntu 24.04+ / Fedora 40+ is the baseline);"
    log "         pip will build it from source, which needs a C compiler and GLib 2.80"
fi

if [ -x .venv/bin/python ]; then
    log ".venv already exists ($(.venv/bin/python --version 2>&1))"
else
    if [ -e .venv ]; then
        log "removing incomplete .venv from an earlier run"
        rm -rf .venv
    fi
    if "$PYTHON" -c 'import ensurepip' >/dev/null 2>&1; then
        log "creating .venv with $PYTHON"
        "$PYTHON" -m venv --system-site-packages .venv
    else
        if [ "${CLIPMAN_NO_NETWORK:-0}" = "1" ]; then
            log "error: $PYTHON has no ensurepip module and CLIPMAN_NO_NETWORK=1 forbids"
            log "       bootstrapping pip from the network. Install the distro's venv"
            log "       support (apt: python3-venv) and re-run."
            exit 1
        fi
        log "notice: $PYTHON has no ensurepip module (python3-venv not installed);"
        log "        creating .venv --without-pip and bootstrapping pip from"
        log "        https://bootstrap.pypa.io/get-pip.py"
        "$PYTHON" -m venv --system-site-packages --without-pip .venv
    fi
fi

if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    if [ "${CLIPMAN_NO_NETWORK:-0}" = "1" ]; then
        log "error: .venv has no pip and CLIPMAN_NO_NETWORK=1 forbids bootstrapping it."
        log "       Install python3-venv (apt) and recreate .venv, or unset CLIPMAN_NO_NETWORK."
        exit 1
    fi
    log "bootstrapping pip into .venv"
    if ! command -v curl >/dev/null 2>&1; then
        log "error: curl is required to bootstrap pip (or install python3-venv and recreate .venv)"
        exit 1
    fi
    curl -sSL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python -
fi

if [ "${CLIPMAN_NO_NETWORK:-0}" = "1" ]; then
    log "CLIPMAN_NO_NETWORK=1: skipping 'pip install -e .[dev]'"
    notices+=("Python extras: run '.venv/bin/python -m pip install -e \".[dev]\"' once you are online.")
else
    log "installing the project with its dev extras into .venv"
    .venv/bin/python -m pip install -e ".[dev]"
fi

# 3. Git hooks
step "Git hooks"
hooks_path=$(git config --get core.hooksPath 2>/dev/null || true)
if [ -z "$hooks_path" ]; then
    log "core.hooksPath unset; installing the repo's hooks"
    scripts/install-hooks.sh --replace
elif [ "$hooks_path" = ".githooks" ]; then
    log "hooks already installed (core.hooksPath=.githooks)"
else
    log "core.hooksPath is '$hooks_path' — left untouched"
    notices+=("Git hooks: core.hooksPath already points at '$hooks_path' (another hook manager). \
This script does not replace it. If your hook manager can chain to a previous hooks directory, \
point it at the repo's hooks with: git config guard.prevHooksPath \"$PWD/.githooks\" \
(the convention for managers that honor a prevHooksPath). Otherwise, to hand the clone over \
to the repo's hooks instead, run: scripts/install-hooks.sh --replace")
fi

# 4. Git identity
step "Git identity"
if [ -z "$(git config user.email 2>/dev/null || true)" ]; then
    log "git user.email is not set for this clone; configure it before committing:"
    printf '  git config user.name  "Your Name"\n  git config user.email "you@example.com"\n' >&2
    notices+=("Git identity: set user.name / user.email (commands printed above).")
else
    log "git identity: $(git config user.name 2>/dev/null || true) <$(git config user.email)>"
fi

# Summary
step "Done"
if [ "${#notices[@]}" -gt 0 ]; then
    printf 'Follow-ups:\n' >&2
    for n in "${notices[@]}"; do
        printf '  - %s\n' "$n" >&2
    done
    printf '\n' >&2
fi
cat >&2 <<'EOF'
Next:
  scripts/dev.sh test          # full suite under xvfb (make test)
  scripts/dev.sh lint          # ruff + shellcheck        (make lint)
  scripts/dev.sh check         # both                     (make check)
  scripts/dev.sh screenshot --out /tmp/clipman.png
EOF
