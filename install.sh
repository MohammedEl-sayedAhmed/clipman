#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIPMAN_PY="$SCRIPT_DIR/clipman.py"
LAUNCHER="$SCRIPT_DIR/launcher.sh"
HELPER="$SCRIPT_DIR/scripts/install_helper.py"
AUTOSTART_DIR="$HOME/.config/autostart"
LEGACY_AUTOSTART="$AUTOSTART_DIR/com.clipman.Clipman.desktop"
DATA_DIR="$HOME/.local/share/clipman"
EXTENSION_UUID="clipman@clipman.com"
EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/$EXTENSION_UUID"

# True if gsettings has schema $1. Outside GNOME the schemas this script
# writes are missing, and set -e used to stop it before the service step.
has_schema() {
    gsettings list-schemas 2>/dev/null | grep -qxF "$1"
}

# A running Shell only enables the extensions it found at login. For a new
# one, `gnome-extensions enable` fails and leaves the setting unchanged, so
# the extension stayed off after the next login too. Write the setting the
# Shell reads at login instead. disabled-extensions wins over
# enabled-extensions, so take the extension out of it as well.
enable_at_next_login() {
    local list
    list=$(gsettings get org.gnome.shell enabled-extensions) &&
        list=$(python3 "$HELPER" strv-add "$list" "$EXTENSION_UUID") &&
        gsettings set org.gnome.shell enabled-extensions "$list" &&
        list=$(gsettings get org.gnome.shell disabled-extensions) &&
        list=$(python3 "$HELPER" strv-remove "$list" "$EXTENSION_UUID") &&
        gsettings set org.gnome.shell disabled-extensions "$list"
}

echo "=== Installing Clipman ==="

# Step 1: Install system dependencies (package lists live in scripts/deps.sh)
echo "[1/6] Installing dependencies..."
# shellcheck source=scripts/deps.sh
source "$SCRIPT_DIR/scripts/deps.sh"
# Assume yes as 'apt install -y' did; CLIPMAN_DEPS_YES=0 restores the prompt.
: "${CLIPMAN_DEPS_YES:=1}"
# Capture the status instead of letting set -e abort, so the exit-3 hint runs.
deps_rc=0
clipman_deps_install runtime || deps_rc=$?
if [ "$deps_rc" -eq 3 ]; then
    echo "Error: run the sudo command printed above, then re-run ./install.sh"
    exit 1
elif [ "$deps_rc" -ne 0 ]; then
    echo "Error: dependency installation failed (exit $deps_rc)"
    exit 1
fi

# The path goes into a systemd unit, a desktop entry and a shortcut
# command. Stop now if one of them cannot hold it.
python3 "$HELPER" check-path "$SCRIPT_DIR" || exit 1

# Step 2: Create data directories
echo "[2/6] Creating data directories..."
mkdir -p "$DATA_DIR/images"

# Step 3: Install GNOME Shell extension for native clipboard monitoring
echo "[3/6] Installing GNOME Shell clipboard extension..."
mkdir -p "$EXTENSION_DIR"
cp "$SCRIPT_DIR/extension/metadata.json" "$EXTENSION_DIR/"
cp "$SCRIPT_DIR/extension/extension.js" "$EXTENSION_DIR/"
GNOME_SHELL=0
if ! has_schema org.gnome.shell; then
    echo "  GNOME Shell was not found. Clipman is built for GNOME, so it may"
    echo "  not see what you copy on this desktop."
else
    GNOME_SHELL=1
    if gnome-extensions enable "$EXTENSION_UUID" 2>/dev/null; then
        echo "  Extension enabled. Log out and back in to load this version."
    elif enable_at_next_login; then
        echo "  Extension installed. It starts when you log out and back in."
    else
        echo "  Warning: could not enable the extension. After you log back in, run:"
        echo "    gnome-extensions enable $EXTENSION_UUID"
    fi
    if [ "$(gsettings get org.gnome.shell disable-user-extensions)" = true ]; then
        echo "  Warning: extensions are turned off in GNOME. Turn them on in the"
        echo "  Extensions app, or Clipman cannot see what you copy."
    fi
    shell_version=$(gnome-shell --version 2>/dev/null | awk '{print $NF}')
    if [ -n "$shell_version" ] &&
        ! python3 "$HELPER" supports-shell "$SCRIPT_DIR/extension/metadata.json" "$shell_version"; then
        echo "  Warning: the extension does not list GNOME Shell $shell_version,"
        echo "  so the Shell may refuse to load it."
    fi
fi

# Step 4: Install application icon and desktop entry
# Clipman autostarts via the systemd user service (Step 6) ONLY. We do not
# also drop an XDG autostart .desktop: running both starts the daemon twice,
# and the two instances race for the com.clipman.Daemon bus name, leaving an
# orphaned process. Remove any autostart file left by an older installer.
echo "[4/6] Installing application icon and desktop entry..."
rm -f "$LEGACY_AUTOSTART"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/data/com.clipman.Clipman.svg" "$ICON_DIR/"
# The desktop entry gives the Clipman window its name and icon in the
# dash and in Alt+Tab. NoDisplay keeps it out of the app grid; the
# autostart key only means something in the autostart folder.
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
python3 "$HELPER" fill "$SCRIPT_DIR/data/com.clipman.Clipman.desktop" "$LAUNCHER" \
    > "$APPS_DIR/com.clipman.Clipman.desktop"
update-desktop-database "$APPS_DIR" 2>/dev/null || true

# Translations, when a language has been contributed. Needs msgfmt from
# the gettext package; without it the app stays in English.
clipman_build_catalogues "$SCRIPT_DIR"

# Step 5: Register the keyboard shortcut. Super+V, unless the user has
# picked another key since the last install.
echo "[5/6] Registering the keyboard shortcut..."

CUSTOM_KEYS_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
CLIPMAN_KEY_PATH="$CUSTOM_KEYS_PATH/clipman/"
CLIPMAN_KEY_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${CLIPMAN_KEY_PATH}"
BINDING=""

if ! has_schema org.gnome.settings-daemon.plugins.media-keys; then
    echo "  GNOME's keyboard settings were not found. Bind a key to this command:"
    printf '    %q toggle\n' "$LAUNCHER"
else
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
            NEW_LIST=$(echo "$EXISTING" | sed "s|]$|, '$CLIPMAN_KEY_PATH']|")
        fi
        gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$NEW_LIST"
    fi

    gsettings set "$CLIPMAN_KEY_SCHEMA" name "Clipman Toggle"
    # An assignment, so set -e stops the script if the helper fails.
    SHORTCUT_COMMAND=$(python3 "$HELPER" shortcut-command "$LAUNCHER")
    gsettings set "$CLIPMAN_KEY_SCHEMA" command "$SHORTCUT_COMMAND"

    # Keep a key the user chose. Before, every run reset it to Super+V.
    BINDING=$(gsettings get "$CLIPMAN_KEY_SCHEMA" binding)
    BINDING=${BINDING//\'/}
    if [ -z "$BINDING" ]; then
        BINDING="<Super>v"
        gsettings set "$CLIPMAN_KEY_SCHEMA" binding "$BINDING"
    else
        echo "  Keeping your shortcut: $BINDING"
    fi

    # Free Super+V from GNOME's message tray shortcut. Keep the user's other
    # keys, and save the original list so uninstall.sh can put it back.
    CURRENT_MSG_TRAY=$(gsettings get org.gnome.shell.keybindings toggle-message-tray 2>/dev/null || echo "[]")
    if [ "${BINDING,,}" = "<super>v" ] && echo "$CURRENT_MSG_TRAY" | grep -qi "'<Super>v'"; then
        [ -f "$DATA_DIR/toggle-message-tray.orig" ] || echo "$CURRENT_MSG_TRAY" > "$DATA_DIR/toggle-message-tray.orig"
        NEW_MSG_TRAY=$(echo "$CURRENT_MSG_TRAY" | python3 -c "
import ast, sys
text = sys.stdin.read().strip()
keys = ast.literal_eval(text[4:] if text.startswith('@as ') else text)
print([k for k in keys if k.lower() != '<super>v'])
")
        gsettings set org.gnome.shell.keybindings toggle-message-tray "$NEW_MSG_TRAY"
        echo "  Removed Super+V from GNOME's message tray shortcut (other keys kept)."
    fi
fi

# Step 6: Install systemd user service (auto-restart on crash)
echo "[6/6] Installing systemd user service..."
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"
python3 "$HELPER" fill "$SCRIPT_DIR/data/clipman.service" "$LAUNCHER" > "$SYSTEMD_DIR/clipman.service"
systemctl --user daemon-reload
systemctl --user enable clipman.service 2>/dev/null || true
echo "  Service installed. It will start automatically on login."

echo ""
echo "=== Installation Complete ==="
echo ""
if [ "$GNOME_SHELL" = 1 ]; then
    echo "IMPORTANT: Log out and back in to activate the clipboard extension."
    echo ""
fi
echo "Usage:"
printf '  Start daemon:  python3 %q\n' "$CLIPMAN_PY"
if [ -n "$BINDING" ]; then
    label=$BINDING
    [ "${BINDING,,}" != "<super>v" ] || label="Super+V"
    printf '  Toggle popup:  %s (or: python3 %q toggle)\n' "$label" "$CLIPMAN_PY"
else
    printf '  Toggle popup:  python3 %q toggle\n' "$CLIPMAN_PY"
fi
echo ""
echo "The daemon will autostart on your next login."
printf 'To start it now, run: python3 %q &\n' "$CLIPMAN_PY"
