"""GNOME gsettings keybinding helpers + display/parsing utilities.

Used by the in-app "Toggle shortcut" customizer in the settings panel.
Kept in its own module so the gsettings shell-outs can be mocked in
tests without pulling GTK into the test path.
"""

from __future__ import annotations

import ast
import subprocess

CUSTOM_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_KEYS_KEY = "custom-keybindings"
CUSTOM_KEY_PATH = (
    "/org/gnome/settings-daemon/plugins/media-keys"
    "/custom-keybindings/clipman/"
)
CUSTOM_KEY_SUBSCHEMA = (
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
)
DEFAULT_TOGGLE_BINDING = "<Super>v"

_MODIFIER_KEY_NAMES = frozenset({
    "Shift_L", "Shift_R", "Control_L", "Control_R",
    "Alt_L", "Alt_R", "Super_L", "Super_R", "Meta_L", "Meta_R",
    "Hyper_L", "Hyper_R",
})


def _gsettings_get(schema: str, key: str, path: str | None = None) -> str | None:
    cmd = ["gsettings", "get",
           f"{schema}:{path}" if path else schema, key]
    try:
        return subprocess.check_output(cmd, text=True, timeout=5).strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def _gsettings_set(schema: str, key: str, value: str,
                   path: str | None = None) -> bool:
    cmd = ["gsettings", "set",
           f"{schema}:{path}" if path else schema, key, value]
    try:
        subprocess.check_call(
            cmd, timeout=5,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def get_toggle_binding() -> str | None:
    """Read the Clipman custom keybinding's binding string."""
    raw = _gsettings_get(
        CUSTOM_KEY_SUBSCHEMA, "binding", path=CUSTOM_KEY_PATH
    )
    if raw is None:
        return None
    return raw.strip().strip("'").strip('"')


def set_toggle_binding(binding: str) -> bool:
    """Update the binding (keystroke) on the Clipman custom keybinding."""
    return _gsettings_set(
        CUSTOM_KEY_SUBSCHEMA, "binding", f"'{binding}'",
        path=CUSTOM_KEY_PATH,
    )


def format_binding_for_display(binding: str) -> str:
    """Convert ``<Super><Shift>v`` to ``Super+Shift+V`` for the UI."""
    if not binding:
        return ""
    parts: list[str] = []
    s = binding
    while s.startswith("<"):
        end = s.find(">")
        if end == -1:
            break
        parts.append(s[1:end].title())
        s = s[end + 1:]
    if s:
        parts.append(s.upper() if len(s) == 1 else s.title())
    return "+".join(parts)


def keyval_to_binding(keyval: int, state: int) -> str | None:
    """Convert a Gtk key event (keyval + modifier state) into gsettings syntax.

    Returns None when the press is a pure modifier or has no usable name.
    Requires at least one modifier; pure-letter bindings are not allowed.
    """
    # Local import so importing this module doesn't require Gdk.
    from gi.repository import Gdk

    name = Gdk.keyval_name(keyval)
    if not name or name in _MODIFIER_KEY_NAMES:
        return None

    parts: list[str] = []
    if state & Gdk.ModifierType.CONTROL_MASK:
        parts.append("<Ctrl>")
    if state & Gdk.ModifierType.SUPER_MASK:
        parts.append("<Super>")
    if state & Gdk.ModifierType.MOD1_MASK:
        parts.append("<Alt>")
    if state & Gdk.ModifierType.SHIFT_MASK:
        parts.append("<Shift>")

    if not parts:
        return None  # at least one modifier required

    parts.append(name)
    return "".join(parts)


def is_clipman_binding_registered() -> bool:
    """True iff the GNOME custom-keybindings list already contains the
    Clipman path. Falsey when gsettings is unavailable (snap, etc.)."""
    raw = _gsettings_get(CUSTOM_KEYS_SCHEMA, CUSTOM_KEYS_KEY)
    if raw is None:
        return False
    try:
        current = ast.literal_eval(raw.replace("@as ", "").strip())
    except (SyntaxError, ValueError):
        return False
    if not isinstance(current, list):
        return False
    return any("clipman" in p for p in current)
