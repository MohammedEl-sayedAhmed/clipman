#!/usr/bin/env bash
#
# End to end in a headless GNOME Shell, the way a user meets Clipman:
#
#   login 1  run install.sh while the Shell is running (#1: the extension
#            was never enabled); until the next login nothing can record
#            copies, and the daemon says so instead of starting
#            wl-paste --watch, which GNOME cannot run
#   login 2  the extension is on, the daemon starts, a copy is recorded,
#            scripts/extension-smoke.sh passes, a huge copy and an app
#            that never sends its data cost the Shell little, the open
#            popup does not spin a CPU core (#307), and uninstall.sh
#            stops a daemon started by hand and keeps the data without a
#            terminal (#328)
#
# Usage: tests/e2e/install_flow.sh [workdir]
# Needs gnome-shell, python3 with GTK 4 and libadwaita, dbus and
# wl-clipboard. Nothing reaches the user's own session: see
# headless-shell.sh.

# No pipefail: `producer | grep -q` would then fail whenever grep stops
# reading early. Each check tests its own result.
set -u

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
uuid="clipman@clipman.com"

failures=0
pass() { printf '  PASS  %s\n' "$1"; }
fail() {
    printf '  FAIL  %s\n' "$1"
    [ -n "${2:-}" ] && [ -f "$2" ] && sed 's/^/        | /' "$2" | tail -n 25
    failures=$((failures + 1))
}

has_owner() {
    gdbus call --session --dest org.freedesktop.DBus \
        --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner "$1" 2>/dev/null | grep -q true
}

# wait_for <seconds> <command...>: poll until the command succeeds.
wait_for() {
    local tries=$(($1 * 4))
    shift
    while [ "$tries" -gt 0 ]; do
        "$@" && return 0
        sleep 0.25
        tries=$((tries - 1))
    done
    return 1
}

history_has() {
    python3 - "$HOME/.local/share/clipman/clipman.db" "$1" <<'PY'
import sqlite3, sys
db, text = sys.argv[1:]
try:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    found = conn.execute("SELECT 1 FROM entries WHERE content_text = ?", (text,)).fetchone()
except sqlite3.Error:
    found = None
sys.exit(0 if found else 1)
PY
}

# The length of the newest text in the history.
newest_length() {
    python3 - "$HOME/.local/share/clipman/clipman.db" <<'PY'
import sqlite3, sys
try:
    conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    row = conn.execute("SELECT length(content_text) FROM entries "
                       "WHERE content_type = 'text' ORDER BY id DESC LIMIT 1").fetchone()
except sqlite3.Error:
    row = None
print(row[0] if row else 0)
PY
}

# CPU clock ticks the process used over two seconds.
cpu_ticks() {
    local before after
    before=$(awk '{print $14 + $15}' "/proc/$1/stat")
    sleep 2
    after=$(awk '{print $14 + $15}' "/proc/$1/stat")
    echo $((after - before))
}

shell_pid() {
    gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.GetConnectionUnixProcessID org.gnome.Shell \
        | tr -dc '0-9 ' | awk '{print $NF}'
}

# The most memory the process has used so far, in MB.
peak_mb() {
    awk '/^VmHWM:/ {print int($2 / 1024)}' "/proc/$1/status"
}

pipe_count() {
    find "/proc/$1/fd" -lname 'pipe:*' 2>/dev/null | wc -l
}

shell_eval() {
    gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
        --method org.gnome.Shell.Eval "$1" 2>&1
}

# True while the Shell shows a window titled "Clipman" (the popup).
popup_shown() {
    gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
        --method org.gnome.Shell.Eval \
        "global.get_window_actors().some(a => a.meta_window.get_title() === 'Clipman' && a.visible)" \
        2>/dev/null | grep -q "(true, 'true')"
}

popup_hidden() { ! popup_shown; }

daemon_call() {
    gdbus call --session --dest com.clipman.Daemon --object-path /com/clipman/Daemon \
        --method "com.clipman.Daemon.$1" >/dev/null 2>&1
}

login1() {
    echo "== Login 1: install while the Shell is running"
    if PATH="$STUBS:$PATH" bash "$repo/install.sh" > "$WORK/install.out" 2>&1; then
        pass "install.sh finished"
    else
        fail "install.sh failed" "$WORK/install.out"
    fi
    local enabled
    enabled=$(gsettings get org.gnome.shell enabled-extensions)
    case "$enabled" in
        *"'$uuid'"*) pass "the extension is enabled for the next login" ;;
        *) fail "enabled-extensions is $enabled" ;;
    esac
    without_extension
}

# The Shell loads a new extension only at login, so the daemon runs
# without it here. A logging wl-paste shows whether it starts the watcher.
without_extension() {
    local real shim="$WORK/shim"
    real=$(command -v wl-paste) || { fail "wl-paste is not installed"; return; }
    mkdir -p "$shim"
    printf '#!/bin/sh\necho "$*" >> "%s/wl-paste.calls"\nexec "%s" "$@"\n' \
        "$WORK" "$real" > "$shim/wl-paste"
    chmod 700 "$shim/wl-paste"

    PATH="$shim:$PATH" GDK_BACKEND=wayland python3 "$repo/clipman.py" \
        > "$WORK/daemon1.log" 2>&1 &
    local daemon=$!
    if wait_for 20 has_owner com.clipman.Daemon; then
        pass "the daemon started without the extension"
    else
        fail "the daemon did not start" "$WORK/daemon1.log"
        kill "$daemon" 2>/dev/null
        return
    fi
    # The daemon decides right after it owns its name; give it a moment.
    sleep 2
    if grep -q -- "--watch" "$WORK/wl-paste.calls" 2>/dev/null; then
        fail "the daemon ran wl-paste --watch, which cannot work on GNOME"
    else
        pass "the daemon did not run wl-paste --watch"
    fi
    if grep -q "extension is not running" "$WORK/daemon1.log"; then
        pass "the log says why copies are not recorded"
    else
        fail "the log does not say why copies are not recorded" "$WORK/daemon1.log"
    fi
    kill "$daemon" 2>/dev/null
    wait "$daemon" 2>/dev/null
}

login2() {
    echo "== Login 2: the extension, the daemon, a copy, the popup, uninstall"
    if wait_for 20 has_owner org.gnome.Shell.Extensions.clipman; then
        pass "the extension is running ($(gnome-extensions info "$uuid" | grep -o 'State: [A-Z]*'))"
    else
        fail "the extension is not running after the new login"
        gnome-extensions info "$uuid" > "$WORK/ext-info.out" 2>&1
        fail "gnome-extensions info" "$WORK/ext-info.out"
        return
    fi

    # Start the daemon by hand, as install.sh suggests.
    GDK_BACKEND=wayland python3 "$repo/clipman.py" > "$WORK/daemon.log" 2>&1 &
    local daemon=$!
    if wait_for 20 has_owner com.clipman.Daemon; then
        pass "the daemon started"
    else
        fail "the daemon did not start" "$WORK/daemon.log"
        return
    fi

    python3 "$here/clipboard_client.py" "clipman e2e copy" > "$WORK/client.log" 2>&1 &
    local client=$!
    if wait_for 15 history_has "clipman e2e copy"; then
        pass "a copy reached the history"
    else
        fail "a copy did not reach the history" "$WORK/client.log"
        shell_eval "global.display.focus_window ? global.display.focus_window.get_title() : null" \
            | sed 's/^/        | focus window: /'
        shell_eval "Main.overview.visible" | sed 's/^/        | overview open: /'
    fi
    if grep -q "not recorded" "$WORK/daemon.log"; then
        fail "the log says copies are not recorded, with the extension on" "$WORK/daemon.log"
    else
        pass "no recording problem is logged"
    fi

    if bash "$repo/scripts/extension-smoke.sh" > "$WORK/smoke.out" 2>&1; then
        pass "scripts/extension-smoke.sh"
    else
        fail "scripts/extension-smoke.sh" "$WORK/smoke.out"
    fi

    # While that client runs, another one cannot take the clipboard.
    wait "$client"
    # Count the clipboard owners, so a copy that never took the clipboard
    # cannot pass the checks below.
    shell_eval "global._e2eOwners = 0; global.display.get_selection().connect('owner-changed',
        (_s, type) => { if (type === imports.gi.Meta.SelectionType.SELECTION_CLIPBOARD) global._e2eOwners++; });
        'counting'" > /dev/null

    # A long copy is read in many chunks, and must arrive whole.
    python3 "$here/clipboard_client.py" y 1048576 > "$WORK/long.log" 2>&1
    if [ "$(newest_length)" = 1048576 ]; then
        pass "a 1 MB copy reached the history whole"
    else
        fail "a 1 MB copy did not reach the history whole ($(newest_length) characters)" "$WORK/long.log"
    fi

    # The extension reads a copy only up to the daemon's 10 MB limit.
    # Before, the Shell read all of it: its peak grew by 273 MB for 50 MB.
    local shell peak after owners
    shell=$(shell_pid)
    peak=$(peak_mb "$shell")
    owners=$(shell_eval "global._e2eOwners" | tr -dc '0-9')
    python3 "$here/clipboard_client.py" z 52428800 > "$WORK/big.log" 2>&1
    after=$(peak_mb "$shell")
    if [ "$(shell_eval "global._e2eOwners" | tr -dc '0-9')" -le "$owners" ]; then
        fail "the 50 MB copy did not take the clipboard" "$WORK/big.log"
    elif [ $((after - peak)) -lt 100 ]; then
        pass "a 50 MB copy raised the Shell's peak memory by $((after - peak)) MB ($peak to $after)"
    else
        fail "a 50 MB copy raised the Shell's peak memory by $((after - peak)) MB ($peak to $after)" "$WORK/big.log"
    fi

    # An app that owns the clipboard but never sends the data: each read
    # must end, at the next copy or after 5 s, and close its pipe. Before,
    # every read stayed open until the app quit. GNOME's own clipboard
    # manager keeps one read open, with or without Clipman.
    local pipes stuck
    pipes=$(pipe_count "$shell")
    python3 "$here/stuck_clipboard_client.py" 20 > "$WORK/stuck.log" 2>&1 &
    stuck=$!
    if wait_for 20 grep -q "done:" "$WORK/stuck.log"; then
        sleep 7
        local left=$(( $(pipe_count "$shell") - pipes ))
        if [ "$left" -le 1 ]; then
            pass "reads from a stuck app end (extra pipes open: $left)"
        else
            fail "reads from a stuck app stay open (extra pipes open: $left)" "$WORK/stuck.log"
        fi
    else
        fail "the stuck clipboard app did not run" "$WORK/stuck.log"
    fi
    kill "$stuck" 2>/dev/null

    # Before #307, one open left a core at 100 % (about 200 ticks in 2 s).
    # Idle is far below that, though software rendering on a CI runner
    # costs some ticks while the popup is open: allow half a core.
    local ticks
    daemon_call Show
    if wait_for 10 popup_shown; then
        pass "Show opens the popup"
    else
        fail "Show did not open the popup" "$WORK/daemon.log"
    fi
    sleep 2
    ticks=$(cpu_ticks "$daemon")
    if [ "$ticks" -lt 100 ]; then
        pass "the open popup is idle ($ticks ticks in 2 s)"
    else
        fail "the open popup uses a CPU core ($ticks ticks in 2 s)"
    fi
    daemon_call Hide
    if wait_for 10 popup_hidden; then
        pass "Hide closes the popup"
    else
        fail "Hide did not close the popup"
    fi
    sleep 2
    ticks=$(cpu_ticks "$daemon")
    if [ "$ticks" -lt 100 ]; then
        pass "the hidden popup is idle ($ticks ticks in 2 s)"
    else
        fail "the hidden popup uses a CPU core ($ticks ticks in 2 s)"
    fi

    if PATH="$STUBS:$PATH" bash "$repo/uninstall.sh" < /dev/null > "$WORK/uninstall.out" 2>&1; then
        pass "uninstall.sh finished without a terminal"
    else
        fail "uninstall.sh failed without a terminal" "$WORK/uninstall.out"
    fi
    if wait_for 10 bash -c "! kill -0 $daemon 2>/dev/null"; then
        pass "uninstall.sh stopped the daemon started by hand"
    else
        fail "the daemon is still running after uninstall.sh"
        kill "$daemon" 2>/dev/null
    fi
    if [ -d "$HOME/.local/share/clipman" ]; then
        pass "the history was kept"
    else
        fail "the history was removed without asking"
    fi
}

case "${1:-}" in
    --login1) login1; exit $((failures > 0)) ;;
    --login2) login2; exit $((failures > 0)) ;;
esac

WORK="${1:-$(mktemp -d /tmp/clipman-e2e-work.XXXXXX)}"
mkdir -p "$WORK"
WORK="$(cd "$WORK" && pwd)"
STUBS="$WORK/stubs"
mkdir -p "$STUBS"
# install.sh and uninstall.sh reach the system: packages, the user's
# systemd manager, the desktop database. Stand-ins keep them inside the
# test. (The package check reports everything as installed.)
printf '#!/bin/sh\nprintf "install ok installed"\n' > "$STUBS/dpkg-query"
for tool in apt-get sudo systemctl update-desktop-database; do
    printf '#!/bin/sh\nexit 0\n' > "$STUBS/$tool"
done
chmod 700 "$STUBS"/*
export WORK STUBS

echo "e2e work folder: $WORK"
rc=0
bash "$here/headless-shell.sh" "$WORK" bash "$0" --login1 || rc=1
bash "$here/headless-shell.sh" "$WORK" bash "$0" --login2 || rc=1
if [ "$rc" -ne 0 ]; then
    echo "e2e: FAILED (logs in $WORK)"
fi
exit "$rc"
