#!/bin/bash
set -e

AUTOSTART_DIR="$HOME/.config/autostart"
DATA_DIR="$HOME/.local/share/clipman"
EXTENSION_UUID="clipman@clipman.com"
EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/$EXTENSION_UUID"

echo "=== Uninstalling Clipman ==="

# Step 1: Remove GNOME Shell extension
echo "[1/4] Removing GNOME Shell clipboard extension..."
gnome-extensions disable "$EXTENSION_UUID" 2>/dev/null || true
rm -rf "$EXTENSION_DIR"
echo "  Extension removed."

# Step 2: Remove autostart entry
echo "[2/4] Removing autostart entry..."
rm -f "$AUTOSTART_DIR/com.clipman.Clipman.desktop"

# Step 3: Remove keybinding
echo "[3/4] Removing keyboard shortcut..."
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

# Step 4: Remove data (ask first)
echo ""
read -p "Remove clipboard history data ($DATA_DIR)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_DIR"
    echo "  Data removed."
else
    echo "  Data kept."
fi

# Kill running daemon (match exact command pattern to avoid killing unrelated processes)
pkill -f "python3.*clipman\.py$" 2>/dev/null || true

echo ""
echo "=== Uninstall Complete ==="
