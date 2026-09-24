#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER="$SCRIPT_DIR/scripts/install_helper.py"
AUTOSTART_DIR="$HOME/.config/autostart"
DATA_DIR="$HOME/.local/share/clipman"
EXTENSION_UUID="clipman@clipman.com"
EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/$EXTENSION_UUID"
SYSTEMD_DIR="$HOME/.config/systemd/user"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APPS_DIR="$HOME/.local/share/applications"

echo "=== Uninstalling Clipman ==="

# Step 1: Stop and remove systemd service
echo "[1/6] Stopping systemd service..."
systemctl --user stop clipman.service 2>/dev/null || true
systemctl --user disable clipman.service 2>/dev/null || true
rm -f "$SYSTEMD_DIR/clipman.service"
systemctl --user daemon-reload 2>/dev/null || true
echo "  Service removed."
# A daemon started by hand (python3 clipman.py &) outlives the service. It
# kept the bus name and wrote into the files removed below. Ask it to quit.
if gdbus call --session --timeout 5 --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon --method com.clipman.Daemon.Quit >/dev/null 2>&1; then
    echo "  Running daemon stopped."
fi

# Step 2: Remove GNOME Shell extension
echo "[2/6] Removing GNOME Shell clipboard extension..."
# The Shell refuses to disable an extension it has not loaded, for example
# one installed since the last login. Take it out of the setting instead.
if ! gnome-extensions disable "$EXTENSION_UUID" 2>/dev/null; then
    list=$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null) &&
        list=$(python3 "$HELPER" strv-remove "$list" "$EXTENSION_UUID" 2>/dev/null) &&
        gsettings set org.gnome.shell enabled-extensions "$list" 2>/dev/null || true
fi
rm -rf "$EXTENSION_DIR"
echo "  Extension removed."

# Step 3: Remove autostart entry
echo "[3/6] Removing autostart entry..."
rm -f "$AUTOSTART_DIR/com.clipman.Clipman.desktop"

# Step 4: Remove keybinding
echo "[4/6] Removing keyboard shortcut..."
CUSTOM_KEYS_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
CLIPMAN_KEY_PATH="$CUSTOM_KEYS_PATH/clipman/"

EXISTING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "[]")

if echo "$EXISTING" | grep -q "clipman"; then
    NEW_LIST=$(echo "$EXISTING" | python3 -c "
import sys, ast
keys = ast.literal_eval(sys.stdin.read().strip())
keys = [k for k in keys if 'clipman' not in k]
print(keys)
")
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"
    # Reset the keybinding
    gsettings reset org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CLIPMAN_KEY_PATH name 2>/dev/null || true
    gsettings reset org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CLIPMAN_KEY_PATH command 2>/dev/null || true
    gsettings reset org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CLIPMAN_KEY_PATH binding 2>/dev/null || true
    # Give Super+V back to GNOME's message tray: the list install.sh saved
    # if there is one, otherwise GNOME's default.
    if [ -f "$DATA_DIR/toggle-message-tray.orig" ]; then
        gsettings set org.gnome.shell.keybindings toggle-message-tray \
            "$(cat "$DATA_DIR/toggle-message-tray.orig")" 2>/dev/null || true
        rm -f "$DATA_DIR/toggle-message-tray.orig"
    else
        gsettings reset org.gnome.shell.keybindings toggle-message-tray 2>/dev/null || true
    fi
    echo "  Keybinding removed. Super+V given back to GNOME's message tray."
else
    echo "  No keybinding found."
fi

# Step 5: Remove app icon and desktop entry
echo "[5/6] Removing application icon and desktop entry..."
rm -f "$ICON_DIR/com.clipman.Clipman.svg" "$APPS_DIR/com.clipman.Clipman.desktop"
update-desktop-database "$APPS_DIR" 2>/dev/null || true

# Step 6: Remove data (ask first)
echo "[6/6] Data cleanup..."
echo ""
# Without a terminal, read gets no answer and set -e used to stop the
# script here with exit 1. Keep the data then; it is the safe answer.
REPLY=""
if [ -t 0 ]; then
    read -p "Remove clipboard history data ($DATA_DIR)? [y/N] " -n 1 -r || true
    echo
fi
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_DIR"
    echo "  Data removed."
else
    echo "  Data kept in $DATA_DIR"
fi

echo ""
echo "=== Uninstall Complete ==="
echo ""
echo "You may need to log out and back in for extension removal to take effect."
