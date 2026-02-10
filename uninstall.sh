#!/bin/bash
set -e

AUTOSTART_DIR="$HOME/.config/autostart"
DATA_DIR="$HOME/.local/share/clipman"

echo "=== Uninstalling Clipman ==="

# Step 1: Remove autostart entry
echo "[1/3] Removing autostart entry..."
rm -f "$AUTOSTART_DIR/com.clipman.Clipman.desktop"

# Step 2: Remove keybinding
echo "[2/3] Removing keyboard shortcut..."
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
    echo "  Keybinding removed."
else
    echo "  No keybinding found."
fi

# Step 3: Remove data (ask first)
echo ""
read -p "Remove clipboard history data ($DATA_DIR)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$DATA_DIR"
    echo "  Data removed."
else
    echo "  Data kept."
fi

# Kill running daemon
pkill -f "clipman.py" 2>/dev/null || true

echo ""
echo "=== Uninstall Complete ==="
