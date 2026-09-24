#!/usr/bin/env bash
#
# The inside of headless-shell.sh, run on its private session bus: start
# the Shell, wait until it and the probe extension are ready, run the
# command, then stop everything this session started.
#
# Usage: _session.sh <workdir> <command> [args...]

# No pipefail: `producer | grep -q` would then fail whenever grep stops
# reading early. Each check below tests its own result.
set -u

work="$1"
shift

has_owner() {
    gdbus call --session --dest org.freedesktop.DBus \
        --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner "$1" 2>/dev/null | grep -q true
}

eval_ready() {
    gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
        --method org.gnome.Shell.Eval 1 2>/dev/null | grep -q "(true"
}

# Stop the Shell, then every process that carries this session's marker
# (the services the bus started), except this script and its parents.
teardown() {
    local keep=" $$ " pid parent
    pid=$$
    while [ "$pid" -gt 1 ] 2>/dev/null; do
        parent=$(awk '{print $4}' "/proc/$pid/stat" 2>/dev/null) || break
        keep="$keep$parent "
        pid=$parent
    done
    [ -n "${shell_pid:-}" ] && kill "$shell_pid" 2>/dev/null
    sleep 1
    for pid in $(pgrep -u "$(id -u)"); do
        case "$keep" in *" $pid "*) continue ;; esac
        if { tr '\0' '\n' < "/proc/$pid/environ"; } 2>/dev/null \
                | grep -qxF "CLIPMAN_E2E_SESSION=$work"; then
            kill "$pid" 2>/dev/null
        fi
    done
}
trap teardown EXIT

display="wayland-e2e-$$"
args=(--headless --virtual-monitor 1280x800 --wayland-display "$display")
# Without Xwayland when the Shell can say so (not every version has it).
shell_help=$(gnome-shell --help 2>&1 || true)
case "$shell_help" in
    *--no-x11*) args+=(--no-x11) ;;
esac
gnome-shell "${args[@]}" > "$work/shell.log" 2>&1 &
shell_pid=$!

for _ in $(seq 1 120); do
    has_owner org.gnome.Shell && break
    kill -0 "$shell_pid" 2>/dev/null || break
    sleep 0.5
done
if ! has_owner org.gnome.Shell; then
    echo "e2e: the headless Shell did not start; the end of its log:" >&2
    tail -n 30 "$work/shell.log" >&2
    exit 2
fi

# Services the bus starts from now on (the one behind gnome-extensions,
# for one) must see the Shell's display, as the session manager arranges
# in a real session.
gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.UpdateActivationEnvironment \
    "{'WAYLAND_DISPLAY': '$display'}" >/dev/null

gnome-extensions enable probe@clipman.test >/dev/null 2>&1 || true
for _ in $(seq 1 40); do
    eval_ready && break
    sleep 0.5
done
if ! eval_ready; then
    echo "e2e: the probe extension did not turn on unsafe mode" >&2
    exit 2
fi

# A real session has a keyboard. Without one nothing gets keyboard focus,
# and GNOME 46 lets only the focused app set the clipboard. The tests can
# also type with it (global._e2eKeyboard). The backend moved to
# global.stage.context in GNOME 48.
keyboard=$(gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
    --method org.gnome.Shell.Eval "(() => {
        const Clutter = imports.gi.Clutter;
        const backend = global.stage.context
            ? global.stage.context.get_backend() : Clutter.get_default_backend();
        global._e2eKeyboard = backend.get_default_seat().create_virtual_device(
            Clutter.InputDeviceType.KEYBOARD_DEVICE);
        return 'keyboard';
    })()" 2>&1)
case "$keyboard" in
    *"(true, '\"keyboard\"')"*) ;;
    *) echo "e2e: could not add a virtual keyboard: $keyboard" >&2; exit 2 ;;
esac

# Some versions open the Activities overview at login, and a window opened
# behind it gets no focus. Close it, as a user would.
overview_open() {
    gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
        --method org.gnome.Shell.Eval "Main.overview.visible" 2>/dev/null \
        | grep -q "(true, 'true')"
}
if overview_open; then
    echo "e2e: closing the overview the Shell opened at login"
    gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
        --method org.gnome.Shell.Eval "Main.overview.hide()" >/dev/null 2>&1
    for _ in $(seq 1 20); do
        overview_open || break
        sleep 0.25
    done
fi

export WAYLAND_DISPLAY="$display"
"$@"
