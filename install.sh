#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIPMAN_PY="$SCRIPT_DIR/clipman.py"
AUTOSTART_DIR="$HOME/.config/autostart"
DATA_DIR="$HOME/.local/share/clipman"
EXTENSION_UUID="clipman@clipman.com"
EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/$EXTENSION_UUID"

echo "=== Installing Clipman ==="

# Step 1: Install system dependencies
echo "[1/5] Installing dependencies..."
sudo apt install -y wl-clipboard python3-gi python3-dbus gir1.2-gtk-3.0

# Step 2: Create data directories
echo "[2/5] Creating data directories..."
mkdir -p "$DATA_DIR/images"
mkdir -p "$AUTOSTART_DIR"

# Step 3: Install GNOME Shell extension for native clipboard monitoring
echo "[3/5] Installing GNOME Shell clipboard extension..."
mkdir -p "$EXTENSION_DIR"
cp "$SCRIPT_DIR/extension/metadata.json" "$EXTENSION_DIR/"
cp "$SCRIPT_DIR/extension/extension.js" "$EXTENSION_DIR/"
gnome-extensions enable "$EXTENSION_UUID" 2>/dev/null || true
echo "  Extension installed. You may need to log out and back in to activate it."

# Step 4: Generate and install autostart desktop file
echo "[4/5] Setting up autostart..."
sed "s|CLIPMAN_PATH_PLACEHOLDER|$SCRIPT_DIR|g" "$SCRIPT_DIR/data/com.clipman.Clipman.desktop" > "$AUTOSTART_DIR/com.clipman.Clipman.desktop"

# Step 5: Register Super+V keybinding
echo "[5/5] Registering Super+V keyboard shortcut..."

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

# Remove Super+V from GNOME's built-in message tray toggle (conflicts with our binding)
CURRENT_MSG_TRAY=$(gsettings get org.gnome.shell.keybindings toggle-message-tray 2>/dev/null || echo "[]")
if echo "$CURRENT_MSG_TRAY" | grep -q "'<Super>v'"; then
    gsettings set org.gnome.shell.keybindings toggle-message-tray "['<Super>m']"
    echo "  Removed Super+V from GNOME message tray (Super+M still works)."
fi

# Set the keybinding properties
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${CLIPMAN_KEY_PATH}" name "Clipman Toggle"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${CLIPMAN_KEY_PATH}" command "$SCRIPT_DIR/launcher.sh toggle"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${CLIPMAN_KEY_PATH}" binding "<Super>v"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "IMPORTANT: Log out and back in to activate the clipboard extension."
echo ""
echo "Usage:"
echo "  Start daemon:  python3 $CLIPMAN_PY"
echo "  Toggle popup:  Super+V (or: python3 $CLIPMAN_PY toggle)"
echo ""
echo "The daemon will autostart on your next login."
echo "To start it now, run: python3 $CLIPMAN_PY &"
