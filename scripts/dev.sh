#!/usr/bin/env bash
# dev.sh — clipman's task runner (pure bash, no make required).
#
#   scripts/dev.sh setup                one-command bootstrap (dev-setup.sh)
#   scripts/dev.sh deps [args]          system package manifest (deps.sh)
#   scripts/dev.sh test [args]          the suite, exactly as CI runs it
#   scripts/dev.sh lint                 ruff + shellcheck
#   scripts/dev.sh ruff                 ruff check clipman tests
#   scripts/dev.sh shellcheck           shellcheck on the repo's shell scripts
#   scripts/dev.sh screenshot [args]    headless render (scripts/screenshot.py)
#   scripts/dev.sh hooks-test           the git-hook footprint-scanner corpus
#   scripts/dev.sh check                lint, then test
#   scripts/dev.sh help
#
# Python resolution: $CLIPMAN_PYTHON, else .venv/bin/python when present,
# else python3 on PATH. The Makefile is a thin wrapper around this file.

set -euo pipefail

ROOT="$(cd "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() {
    printf 'dev: %s\n' "$*" >&2
}

die() {
    log "error: $*"
    exit 1
}

resolve_python() {
    if [ -n "${CLIPMAN_PYTHON:-}" ]; then
        echo "$CLIPMAN_PYTHON"
    elif [ -x .venv/bin/python ]; then
        echo "$ROOT/.venv/bin/python"
    else
        echo python3
    fi
}

resolve_ruff() {
    if [ -x .venv/bin/ruff ]; then
        echo "$ROOT/.venv/bin/ruff"
    elif command -v ruff >/dev/null 2>&1; then
        command -v ruff
    else
        return 1
    fi
}

# Prefix a command with `xvfb-run -a` when available; otherwise warn once
# and run it against whatever display the environment provides.
with_display() {
    if command -v xvfb-run >/dev/null 2>&1; then
        xvfb-run -a "$@"
    else
        log "warning: xvfb-run not found; running without a virtual display" \
            "(install the 'test' set: scripts/deps.sh --test --install)"
        "$@"
    fi
}

cmd_setup() {
    exec "$ROOT/scripts/dev-setup.sh" "$@"
}

cmd_deps() {
    exec "$ROOT/scripts/deps.sh" "$@"
}

cmd_test() {
    local py
    py=$(resolve_python)
    export CLIPMAN_REQUIRE_GTK4="${CLIPMAN_REQUIRE_GTK4:-1}"
    if "$py" -c 'import pytest' >/dev/null 2>&1; then
        log "runner: pytest ($py)"
        with_display "$py" -m pytest -q "$@"
    else
        log "runner: unittest ($py; pytest not importable — scripts/dev.sh setup installs it)"
        with_display "$py" -m unittest discover -s tests "$@"
    fi
}

cmd_ruff() {
    local ruff
    if ! ruff=$(resolve_ruff); then
        die "ruff not found (.venv/bin/ruff or on PATH); run: scripts/dev.sh setup"
    fi
    log "ruff: $ruff"
    "$ruff" check clipman tests
}

cmd_shellcheck() {
    if ! command -v shellcheck >/dev/null 2>&1; then
        die "shellcheck not found; run: scripts/deps.sh --lint --install (or scripts/dev.sh setup)"
    fi
    shellcheck --severity=warning install.sh uninstall.sh launcher.sh scripts/*.sh
}

cmd_lint() {
    local rc=0
    cmd_ruff || rc=1
    cmd_shellcheck || rc=1
    if [ "$rc" -ne 0 ]; then
        die "lint failed"
    fi
    log "lint ok"
}

cmd_screenshot() {
    local py
    py=$(resolve_python)
    with_display "$py" scripts/screenshot.py "$@"
}

cmd_hooks_test() {
    bash .githooks/_test.sh
}

cmd_check() {
    cmd_lint
    cmd_test "$@"
}

cmd_help() {
    sed -n '2,/^$/p' "$ROOT/scripts/dev.sh" | sed 's/^# \{0,1\}//'
}

main() {
    local sub="${1:-help}"
    shift || true
    case "$sub" in
        setup)      cmd_setup "$@" ;;
        deps)       cmd_deps "$@" ;;
        test)       cmd_test "$@" ;;
        lint)       cmd_lint ;;
        ruff)       cmd_ruff ;;
        shellcheck) cmd_shellcheck ;;
        screenshot) cmd_screenshot "$@" ;;
        hooks-test) cmd_hooks_test ;;
        check)      cmd_check "$@" ;;
        help|-h|--help) cmd_help ;;
        *)
            log "unknown subcommand '$sub'"
            cmd_help >&2
            exit 2
            ;;
    esac
}

main "$@"
