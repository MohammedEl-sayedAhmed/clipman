#!/bin/bash
# Launcher that strips snap environment pollution if present.
# This ensures clipman works whether started from GNOME, a regular
# terminal, or a snap-packaged terminal like VSCode.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -n "$SNAP" ]; then
    exec env -i \
        HOME="$HOME" \
        DISPLAY="${DISPLAY:-}" \
        WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
        XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
        PATH="/usr/bin:/usr/local/bin:/bin" \
        python3 "$SCRIPT_DIR/clipman.py" "$@"
else
    exec python3 "$SCRIPT_DIR/clipman.py" "$@"
fi
