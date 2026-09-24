#!/usr/bin/env bash
#
# Run a command inside a throwaway headless GNOME Shell, with its own
# session bus, Wayland display, runtime folder and home. Nothing reaches
# the user's session, so this is safe on a developer machine, and it is
# what the CI end-to-end job runs.
#
# Usage: headless-shell.sh <workdir> <command> [args...]
#
# <workdir>/home is HOME. Settings go to dconf, as in a real session; its
# database lives in that home, and the dconf service runs on the private
# bus. Running again with the same workdir is a new login: the home and
# the settings stay, the Shell starts fresh. (The keyfile backend is not
# used: each process rewrites the whole file from its own copy, so the
# Shell could silently drop another process's change.)
#
# The command runs with WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS, HOME
# and the XDG folders pointing at this session. A test-only extension
# (tests/e2e/probe@clipman.test) turns on the Shell's unsafe mode, so
# the command can use org.gnome.Shell.Eval.

set -euo pipefail

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <workdir> <command> [args...]" >&2
    exit 2
fi
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$1"
work="$(cd "$1" && pwd)"
shift

home="$work/home"
extensions="$home/.local/share/gnome-shell/extensions"
mkdir -p "$extensions" "$work/bin"
rm -rf "$extensions/probe@clipman.test"
cp -r "$here/probe@clipman.test" "$extensions/"

# The Shell starts ibus-daemon for input methods. A stand-in keeps it from
# starting the real one on this bus.
printf '#!/bin/sh\nexec sleep 86400\n' > "$work/bin/ibus-daemon"
chmod 700 "$work/bin/ibus-daemon"

# The Wayland socket path must stay under 108 bytes, so the runtime
# folder cannot live in a long workdir path.
runtime="$(mktemp -d /tmp/clipman-e2e.XXXXXX)"
trap 'rm -rf "$runtime"' EXIT

unset DISPLAY WAYLAND_DISPLAY DBUS_SESSION_BUS_ADDRESS
export HOME="$home" \
    XDG_CONFIG_HOME="$home/.config" \
    XDG_DATA_HOME="$home/.local/share" \
    XDG_CACHE_HOME="$home/.cache" \
    XDG_STATE_HOME="$home/.local/state" \
    XDG_RUNTIME_DIR="$runtime" \
    GSETTINGS_BACKEND=dconf \
    NO_AT_BRIDGE=1 \
    GTK_A11Y=none \
    PATH="$work/bin:$PATH" \
    CLIPMAN_E2E_SESSION="$work"

dbus-run-session -- bash "$here/_session.sh" "$work" "$@"
