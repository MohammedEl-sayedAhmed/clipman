#!/bin/bash
# Bluefin-DX / Fedora atomic installer for this clipman fork.
# Idempotent. No /usr writes, no rpm-ostree layering (deps ship in image).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== [1/5] Dependency check ==="
missing=()
for c in wl-copy wl-paste wtype ydotool ydotoold python3; do
    command -v "$c" >/dev/null 2>&1 || missing+=("$c")
done
python3 -c "import gi, dbus; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" \
    2>/dev/null || missing+=("python3-gi/dbus/GTK4/Adw")
if [ "${#missing[@]}" -ne 0 ]; then
    echo "Missing: ${missing[*]}"
    echo "Layer them:  rpm-ostree install wl-clipboard wtype ydotool python3-dbus && systemctl reboot"
    exit 1
fi
echo "  all deps present"

echo "=== [2/5] Patch extension shell-version (add 49,50 if absent) ==="
python3 - "$SCRIPT_DIR/extension/metadata.json" <<'PY'
import sys, json
p = sys.argv[1]; d = json.load(open(p))
for v in ("49", "50"):
    if v not in d["shell-version"]:
        d["shell-version"].append(v)
json.dump(d, open(p, "w"), indent=2)
print("  shell-version:", d["shell-version"])
PY

echo "=== [3/5] Run upstream install.sh with dnf dep-step neutralized ==="
# Must live inside SCRIPT_DIR: upstream install.sh derives its own paths from
# `dirname "$0"`, so running a /tmp copy would resolve $SCRIPT_DIR to /tmp and
# break every `$SCRIPT_DIR/extension/...` reference.
tmp_install="$SCRIPT_DIR/.install-bluefin-patched.tmp.sh"
trap 'rm -f "$tmp_install"' EXIT
sed -E 's@^[[:space:]]*sudo (dnf|apt) install.*@        echo "  [skip] deps pre-satisfied on atomic host"@' \
    "$SCRIPT_DIR/install.sh" > "$tmp_install"
# drop the apt continuation line (backslash-wrapped second line), if present
sed -i '/gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0/d' "$tmp_install"
bash "$tmp_install"
rm -f "$tmp_install"

echo "=== [4/5] One daemon owner: disable autostart dup (systemd keeps it) ==="
ad="$HOME/.config/autostart/com.clipman.Clipman.desktop"
[ -f "$ad" ] && mv "$ad" "$ad.disabled" && echo "  autostart disabled" || echo "  no autostart dup"

echo "=== [5/5] Auto-paste backend: input group + ydotoold ==="
if id -nG "$USER" | grep -qw input; then
    echo "  already in 'input' group"
else
    echo "  adding $USER to 'input' group (sudo)..."
    sudo usermod -aG input "$USER" && echo "  added — RELOGIN required"
fi
systemctl --user enable ydotoold.service && echo "  ydotoold.service enabled"

cat <<EOF

=== Done ===
LOG OUT and back in, then verify:
  id -nG | grep -qw input && echo input-OK
  systemctl --user is-active ydotoold.service clipman.service
Usage: focus a text field -> Super+V -> click a card -> pastes.
EOF
