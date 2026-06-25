"""Pure-data declarations for the 15 edge states from the mockups.

Each ``StateSpec`` captures everything the renderer needs:
- ``id``: stable identifier used by ``window.py`` to look the state up.
- ``kind``: which Adw widget family carries the message
  (``"statuspage"`` | ``"banner"`` | ``"alertdialog"``).
- ``tone``: visual + CSS class hint
  (``"info"`` | ``"warning"`` | ``"privacy"`` | ``"error"`` | ``"neutral"``).
- ``icon_name``: an Adwaita symbolic icon. The renderer normalises to
  symbolic-suffix because non-symbolic icons in StatusPage look chunky.
- ``title`` + ``body``: localized strings (callers should pass them
  through ``_()`` — these defaults already are).
- ``primary_action`` / ``secondary_action``: optional ``(label, action_id)``
  tuples. ``action_id`` is a stable string the caller dispatches on.

The widget construction in ``render_edge_state`` is intentionally thin
— it knows the three Adw families but nothing about the daemon's
business logic. All wiring lives in ``window.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

from clipman import _

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402


@dataclass(frozen=True)
class StateSpec:
    """Declarative description of one edge state.

    ``primary_action`` and ``secondary_action`` are either ``None`` or
    a ``(label, action_id)`` tuple. The renderer wires the buttons to
    emit a signal — the host window is responsible for translating
    ``action_id`` into actual behaviour.
    """

    id: str
    kind: str
    tone: str
    icon_name: str
    title: str
    body: str
    primary_action: tuple[str, str] | None = None
    secondary_action: tuple[str, str] | None = None


# ---------------------------------------------------------------------
# The 15 specs. Order matches the mockup picker (states.html), reading
# top-to-bottom: Baseline / Informational / Privacy / Setup / Errors.
# ---------------------------------------------------------------------

STATES: dict[str, StateSpec] = {
    "populated": StateSpec(
        id="populated",
        kind="statuspage",  # never actually rendered — list view takes over
        tone="neutral",
        icon_name="edit-paste-symbolic",
        title=_("Populated history"),
        body=_("Clips are showing in the list below."),
    ),
    "empty": StateSpec(
        id="empty",
        kind="statuspage",
        tone="info",
        icon_name="edit-paste-symbolic",
        title=_("Nothing copied yet"),
        body=_("Copy text or an image and it will appear here."),
    ),
    "no-results": StateSpec(
        id="no-results",
        kind="statuspage",
        tone="info",
        icon_name="system-search-symbolic",
        title=_("No clips match that search"),
        body=_("Try a shorter query or clear the search box."),
        primary_action=(_("Clear search"), "clear-search"),
    ),
    "first-run": StateSpec(
        id="first-run",
        kind="statuspage",
        tone="warning",
        icon_name="application-x-addon-symbolic",
        title=_("GNOME Shell extension isn't connected"),
        body=_("Clipman records via wl-paste, but auto-paste needs the "
               "bundled GNOME extension enabled."),
        primary_action=(_("Open Extensions"), "open-extensions"),
        secondary_action=(_("Install guide"), "open-install-guide"),
    ),
    "incognito-on": StateSpec(
        id="incognito-on",
        kind="banner",
        tone="privacy",
        icon_name="view-conceal-symbolic",
        title=_("Incognito is on — new copies are not recorded"),
        body=_("Existing entries stay available."),
        primary_action=(_("Resume recording"), "resume-recording"),
    ),
    "sensitive-shown": StateSpec(
        id="sensitive-shown",
        kind="banner",
        tone="warning",
        icon_name="dialog-password-symbolic",
        title=_("Sensitive clip detected"),
        body=_("This entry will be cleared automatically after the "
               "configured timeout."),
        primary_action=(_("Settings"), "open-prefs-privacy"),
    ),
    "sensitive-cleared": StateSpec(
        id="sensitive-cleared",
        kind="banner",
        tone="info",
        icon_name="security-high-symbolic",
        title=_("Sensitive items cleared"),
        body=_("Clips matching token / password patterns were purged "
               "after the auto-clear timeout."),
        primary_action=(_("Open settings"), "open-prefs-privacy"),
    ),
    "extension-missing": StateSpec(
        id="extension-missing",
        kind="statuspage",
        tone="warning",
        icon_name="application-x-addon-symbolic",
        title=_("GNOME extension required under snap"),
        body=_("Snap confinement blocks wl-paste. Install the bundled "
               "GNOME extension to record clips."),
        primary_action=(_("Open Extensions"), "open-extensions"),
        secondary_action=(_("Snap notes"), "open-snap-notes"),
    ),
    "backup-failed": StateSpec(
        id="backup-failed",
        kind="alertdialog",
        tone="error",
        icon_name="dialog-error-symbolic",
        title=_("Backup failed"),
        body=_("The destination is full, read-only, or otherwise "
               "unwritable. Pick a different folder and retry."),
        primary_action=(_("Retry"), "retry-backup"),
        secondary_action=(_("Choose another location"), "rechoose-backup"),
    ),
    "restore-failed": StateSpec(
        id="restore-failed",
        kind="alertdialog",
        tone="error",
        icon_name="dialog-error-symbolic",
        title=_("Restore failed"),
        body=_("That file isn't a Clipman backup, or it includes "
               "triggers/views we won't import."),
        primary_action=(_("Close"), "close-dialog"),
        secondary_action=(_("Pick another file"), "rechoose-restore"),
    ),
    "network-error": StateSpec(
        id="network-error",
        kind="banner",
        tone="warning",
        icon_name="network-offline-symbolic",
        title=_("Update check failed"),
        body=_("Couldn't reach the GitHub Releases API. We'll try again later."),
        primary_action=(_("Retry"), "retry-update-check"),
    ),
    "db-locked": StateSpec(
        id="db-locked",
        kind="statuspage",
        tone="error",
        icon_name="drive-harddisk-symbolic",
        title=_("Can't open the clipboard database"),
        body=_("Another Clipman process may be running, or the database "
               "file is corrupt."),
        primary_action=(_("Reveal database folder"), "reveal-db-folder"),
        secondary_action=(_("Restore from backup"), "open-restore"),
    ),
    "paused": StateSpec(
        id="paused",
        kind="banner",
        tone="privacy",
        icon_name="media-playback-pause-symbolic",
        title=_("Recording paused"),
        body=_("Clipman is not capturing new clips right now."),
        primary_action=(_("Resume"), "resume-recording"),
    ),
    "paste-target-missing": StateSpec(
        id="paste-target-missing",
        kind="alertdialog",
        tone="warning",
        icon_name="input-keyboard-symbolic",
        title=_("Couldn't auto-paste"),
        body=_("wtype and ydotool aren't installed, so we left the clip "
               "on your clipboard. Paste it manually with Ctrl+V."),
        primary_action=(_("Got it"), "close-dialog"),
        secondary_action=(_("Install help"), "open-install-guide"),
    ),
    "history-too-large": StateSpec(
        id="history-too-large",
        kind="banner",
        tone="warning",
        icon_name="drive-harddisk-symbolic",
        title=_("Clipboard history is getting large"),
        body=_("Older entries will roll off when the cap is reached. "
               "Adjust the limit in Preferences if needed."),
        primary_action=(_("Open Storage settings"), "open-prefs-storage"),
    ),
}


# ---------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------

_TONE_CSS = {
    "info": "info",
    "warning": "warning",
    "privacy": "accent",
    "error": "error",
    "neutral": "dim-label",
}


def render_edge_state(state_id: str, parent_window=None):
    """Construct the Adw widget that visualises ``state_id``.

    Returns:
        - ``Adw.StatusPage`` for ``kind == "statuspage"``,
        - ``Adw.Banner`` for ``kind == "banner"``,
        - ``Adw.AlertDialog`` for ``kind == "alertdialog"``.

    ``parent_window`` is only consulted for alert dialogs (which need
    a transient parent before ``present()``). The button signals do
    nothing here; callers wire ``action_id`` to behaviour via
    ``connect`` after the widget is returned.
    """
    spec = STATES.get(state_id)
    if spec is None:
        # Defensive fallback — a misspelled id shouldn't crash the popup.
        spec = STATES["empty"]

    if spec.kind == "banner":
        banner = Adw.Banner()
        banner.set_title(spec.title)
        if spec.primary_action is not None:
            banner.set_button_label(spec.primary_action[0])
            banner.action_id = spec.primary_action[1]
        banner.set_revealed(True)
        if spec.tone in _TONE_CSS:
            banner.add_css_class(_TONE_CSS[spec.tone])
        banner.state_spec = spec
        return banner

    if spec.kind == "alertdialog":
        dialog = Adw.AlertDialog.new(spec.title, spec.body)
        if spec.secondary_action is not None:
            dialog.add_response(
                spec.secondary_action[1], spec.secondary_action[0]
            )
        if spec.primary_action is not None:
            dialog.add_response(
                spec.primary_action[1], spec.primary_action[0]
            )
            dialog.set_default_response(spec.primary_action[1])
        if spec.tone == "error":
            if spec.primary_action is not None:
                dialog.set_response_appearance(
                    spec.primary_action[1],
                    Adw.ResponseAppearance.DESTRUCTIVE,
                )
        dialog.state_spec = spec
        return dialog

    # Default: status page.
    page = Adw.StatusPage()
    page.set_icon_name(spec.icon_name)
    page.set_title(spec.title)
    page.set_description(spec.body)
    if spec.tone in _TONE_CSS:
        page.add_css_class(_TONE_CSS[spec.tone])

    if spec.primary_action is not None or spec.secondary_action is not None:
        button_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        button_box.set_halign(Gtk.Align.CENTER)
        if spec.secondary_action is not None:
            btn = Gtk.Button(label=spec.secondary_action[0])
            btn.action_id = spec.secondary_action[1]
            button_box.append(btn)
        if spec.primary_action is not None:
            btn = Gtk.Button(label=spec.primary_action[0])
            btn.add_css_class("suggested-action")
            btn.add_css_class("pill")
            btn.action_id = spec.primary_action[1]
            button_box.append(btn)
        page.set_child(button_box)

    page.state_spec = spec
    return page


__all__ = ["StateSpec", "STATES", "render_edge_state"]
