#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIPMAN_PY="$SCRIPT_DIR/clipman.py"
AUTOSTART_DIR="$HOME/.config/autostart"
DATA_DIR="$HOME/.local/share/clipman"

echo "=== Installing Clipman ==="

# Step 1: Install system dependencies
echo "[1/4] Installing dependencies..."
sudo apt install -y wl-clipboard python3-gi python3-dbus gir1.2-gtk-3.0

# Step 2: Create data directories
echo "[2/4] Creating data directories..."
mkdir -p "$DATA_DIR/images"
mkdir -p "$AUTOSTART_DIR"

# Step 3: Generate and install autostart desktop file
echo "[3/4] Setting up autostart..."
sed "s|CLIPMAN_PATH_PLACEHOLDER|$SCRIPT_DIR|g" "$SCRIPT_DIR/data/com.clipman.Clipman.desktop" > "$AUTOSTART_DIR/com.clipman.Clipman.desktop"

# Step 4: Register Super+V keybinding
echo "[4/4] Registering Super+V keyboard shortcut..."

CUSTOM_KEYS_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
CLIPMAN_KEY_PATH="$CUSTOM_KEYS_PATH/clipman/"

# Get existing custom keybindings
EXISTING=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings 2>/dev/null || echo "[]")

# Check if clipman binding already exists
if echo "$EXISTING" | grep -q "clipman"; then
    echo "  Keybinding already registered."
else
    # Add clipman to the list
    if [ "$EXISTING" = "@as []" ] || [ "$EXISTING" = "[]" ]; then
        NEW_LIST="['$CLIPMAN_KEY_PATH']"
    else
        # Remove trailing ] and append
        NEW_LIST=$(echo "$EXISTING" | sed "s/]$/, '$CLIPMAN_KEY_PATH']/")
    fi
    gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"
fi

# Set the keybinding properties
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${CLIPMAN_KEY_PATH}" name "Clipman Toggle"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${CLIPMAN_KEY_PATH}" command "python3 $CLIPMAN_PY toggle"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${CLIPMAN_KEY_PATH}" binding "<Super>v"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Usage:"
echo "  Start daemon:  python3 $CLIPMAN_PY"
echo "  Toggle popup:  Super+V (or: python3 $CLIPMAN_PY toggle)"
echo ""
echo "The daemon will autostart on your next login."
echo "To start it now, run: python3 $CLIPMAN_PY &"
