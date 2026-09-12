#!/usr/bin/env bash
#
# Manual smoke test for the GNOME Shell extension's D-Bus access control.
# Run it inside a GNOME Wayland session with the extension enabled.
# Exit code 0 means every automated check passed.

set -uo pipefail

EXT_NAME="org.gnome.Shell.Extensions.clipman"
EXT_PATH="/org/gnome/Shell/Extensions/clipman"
DAEMON_NAME="com.clipman.Daemon"
pass=0
fail=0

ok() { printf '  PASS  %s\n' "$1"; pass=$((pass + 1)); }
ko() { printf '  FAIL  %s\n' "$1"; fail=$((fail + 1)); }

# Call a method from this shell. This shell does not own the daemon name,
# so every call must be refused with AccessDenied.
expect_denied() {
    local method="$1"; shift
    local out
    out=$(gdbus call --session --dest "$EXT_NAME" --object-path "$EXT_PATH" \
        --method "$EXT_NAME.$method" "$@" 2>&1)
    if printf '%s' "$out" | grep -q "AccessDenied"; then
        ok "$method refused for a foreign caller"
    else
        ko "$method was NOT refused: $out"
    fi
}

echo "== Extension present"
if gdbus introspect --session --dest "$EXT_NAME" --object-path "$EXT_PATH" 2>/dev/null \
        | grep -q "SetPaused"; then
    ok "interface exports SetPaused (contract version 8)"
else
    ko "SetPaused missing: is extension v8 installed and enabled?"
fi

echo "== Foreign callers are refused (direct name)"
expect_denied SimulatePaste "'ctrl-v'"
expect_denied MoveWindowToCursor "'Clipman'"
expect_denied RestorePreviousFocus
expect_denied SetPaused true

echo "== Foreign callers are refused (via org.gnome.Shell)"
out=$(gdbus call --session --dest org.gnome.Shell --object-path "$EXT_PATH" \
    --method "$EXT_NAME.SimulatePaste" "'ctrl-v'" 2>&1)
if printf '%s' "$out" | grep -q "AccessDenied"; then
    ok "SimulatePaste refused through the Shell's own name"
else
    ko "SimulatePaste through org.gnome.Shell was NOT refused: $out"
fi

echo "== Bad mode does not crash the extension"
out=$(gdbus call --session --dest "$EXT_NAME" --object-path "$EXT_PATH" \
    --method "$EXT_NAME.SimulatePaste" "'__proto__'" 2>&1)
if printf '%s' "$out" | grep -q "AccessDenied"; then
    ok "'__proto__' mode refused before it can reach the recipe table"
else
    ko "unexpected reply for '__proto__': $out"
fi

echo "== Daemon"
if gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner "$DAEMON_NAME" 2>/dev/null | grep -q true; then
    ok "daemon owns $DAEMON_NAME"
else
    ko "daemon is not running; start it and re-run for the manual steps"
fi

cat <<'EOF'

== Manual steps (need a human)
  1. Press Super+V, pick a clip, and confirm it pastes into the focused app.
  2. Turn incognito on in the popup, copy some text, and confirm no new
     entry appears in the history. Turn incognito off; copies work again.
  3. Run: gnome-extensions disable clipman@clipman.com
     Open the popup with `clipman toggle` and confirm it now shows in
     Alt+Tab (GNOME 49+ only). Re-enable the extension afterwards.
  4. Check the journal for "clipman: denied" lines from this script:
     journalctl --user -b -g "clipman: denied" | tail
EOF

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
