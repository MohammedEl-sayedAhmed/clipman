#!/bin/bash
set -e

AUTOSTART_DIR="$HOME/.config/autostart"
DATA_DIR="$HOME/.local/share/clipman"
EXTENSION_UUID="clipman@clipman.com"
EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/$EXTENSION_UUID"
SYSTEMD_DIR="$HOME/.config/systemd/user"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "=== Uninstalling Clipman ==="

# Step 1: Stop and remove systemd service
echo "[1/6] Stopping systemd service..."
systemctl --user stop clipman.service 2>/dev/null || true
systemctl --user disable clipman.service 2>/dev/null || true
rm -f "$SYSTEMD_DIR/clipman.service"
systemctl --user daemon-reload 2>/dev/null || true
echo "  Service removed."

# Step 2: Remove GNOME Shell extension
echo "[2/6] Removing GNOME Shell clipboard extension..."
gnome-extensions disable "$EXTENSION_UUID" 2>/dev/null || true
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
    # Restore Super+V to GNOME's message tray
    gsettings reset org.gnome.shell.keybindings toggle-message-tray 2>/dev/null || true
    echo "  Keybinding removed. Super+V restored to GNOME message tray."
else
    echo "  No keybinding found."
fi

# Step 5: Remove app icon
echo "[5/6] Removing application icon..."
rm -f "$ICON_DIR/com.clipman.Clipman.svg"

# Step 6: Remove data (ask first)
echo "[6/6] Data cleanup..."
echo ""
read -p "Remove clipboard history data ($DATA_DIR)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_DIR"
    echo "  Data removed."
else
    echo "  Data kept."
fi

echo ""
echo "=== Uninstall Complete ==="
echo ""
echo "You may need to log out and back in for extension removal to take effect."
