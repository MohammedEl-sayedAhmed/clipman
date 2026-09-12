"""In-app update-availability checker.

Polls the public GitHub Releases API for the latest tag, compares it to
the daemon's own ``__version__``, and exposes the result to the UI via
the existing ``settings`` table (no schema migration).

Design notes:
- All network calls run on a background ``threading.Thread`` so the
  GTK main loop never blocks. Results are pushed back to the main
  thread via ``GLib.idle_add``.
- Per-install defaults: snap and flatpak auto-refresh on their own,
  so the opt-in default is OFF on those distributions and ON for
  source / PyPI / AUR installs.
- No user data leaves the daemon — only an anonymous GET with a
  ``User-Agent`` header. There are no query params, no body, no
  cookies. See ADR 0007.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from clipman._version import __version__

# GitHub Releases tag names are user-controlled — a maintainer could
# in theory publish a tag like "v1.0.0\nDROP TABLE settings" and we'd
# round-trip it through the settings table into the GTK banner. None
# of Clipman's real tags use anything outside this character set, so
# reject anything that isn't a short alnum/dot/plus/hyphen string
# BEFORE it touches the DB.
_TAG_RE = re.compile(r"[A-Za-z0-9.+-]{1,40}")

RELEASES_URL = (
    "https://api.github.com/repos/MohammedEl-sayedAhmed/clipman/releases/latest"
)
HTTP_TIMEOUT_SECONDS = 5
CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # 24h

# DB settings keys this module owns.
SETTING_ENABLED = "check_for_updates"
SETTING_LAST_CHECK = "last_update_check"
SETTING_LATEST_VERSION = "latest_known_version"
SETTING_DISMISSED_VERSION = "dismissed_version"


def install_kind() -> str:
    """Return one of ``'snap'``, ``'flatpak'``, ``'other'``.

    Detection is purely environment-variable-based, so the test suite
    can simulate any kind by setting ``SNAP`` or ``FLATPAK_ID``.
    """
    if os.environ.get("SNAP"):
        return "snap"
    if os.environ.get("FLATPAK_ID"):
        return "flatpak"
    return "other"


def default_enabled() -> bool:
    """Default value for the ``check_for_updates`` setting.

    Snap and Flatpak refresh on their own, so users on those
    distributions don't need (and likely don't want) Clipman to also
    poll. Source / PyPI / AUR installs do not auto-update — default
    ON.
    """
    return install_kind() == "other"


def _tuple_version(s: str) -> tuple:
    """Parse ``X.Y.Z`` into an integer tuple (the fallback).

    Each chunk contributes its leading digits, so ``1.2.3-hotfix``
    compares like ``1.2.3``.
    """
    parts: list[int] = []
    for chunk in (s or "").strip().lstrip("v").split("."):
        match = re.match(r"\d+", chunk)
        if match is None:
            break
        parts.append(int(match.group()))
    return tuple(parts) if parts else (0,)


def _parse_version(s: str):
    """Return a packaging Version, or None if missing or invalid."""
    s = (s or "").strip().lstrip("v")
    try:
        from packaging.version import parse as _pv  # type: ignore
        return _pv(s)
    except Exception:
        return None


def _is_newer(candidate: str, current: str) -> bool:
    """``True`` iff ``candidate`` is strictly newer than ``current``."""
    a, b = _parse_version(candidate), _parse_version(current)
    if a is None or b is None:
        # One side did not parse; compare both the simple way.
        return _tuple_version(candidate) > _tuple_version(current)
    return a > b


def _http_get(url: str = RELEASES_URL) -> dict | None:
    """Issue the anonymous GET. Returns the parsed JSON, or ``None``
    on any network/parse error (the daemon never fails because of an
    update check)."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"clipman/{__version__}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — fixed https URL above
            request, timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
        return json.loads(body)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _safe_tag(raw: str | None) -> str | None:
    """Return ``raw`` (stripped of a leading 'v') iff it matches the
    allow-list regex, else ``None``.

    The settings table happily stores any string, and the banner UI
    just renders it — so a malformed tag would either silently break
    version compare or, worse, smuggle markup into the banner. This
    gate is the single chokepoint for both persistence paths
    (``check_async`` and ``dismiss``).
    """
    if not raw:
        return None
    candidate = raw.strip().lstrip("v")
    if not candidate:
        return None
    if _TAG_RE.fullmatch(candidate):
        return candidate
    return None


def check_for_update(current_version: str = __version__) -> tuple[bool, str | None, str | None]:
    """Synchronous check. ``(is_newer, latest_version, release_url)``.

    On any failure, returns ``(False, None, None)``. Safe to call from
    a background thread.
    """
    payload = _http_get()
    if not payload:
        return (False, None, None)
    tag = _safe_tag(payload.get("tag_name"))
    url = payload.get("html_url") or None
    if not tag:
        return (False, None, url)
    return (_is_newer(tag, current_version), tag, url)


def should_check_now(db, now: float | None = None) -> bool:
    """``True`` iff a check should run now.

    Honours the user's opt-out and the 24-hour rate limit. ``now`` is
    injectable for tests.
    """
    if not _enabled(db):
        return False
    if now is None:
        now = time.time()
    raw = db.get_setting(SETTING_LAST_CHECK, "0")
    try:
        last = float(raw)
    except (TypeError, ValueError):
        last = 0.0
    return (now - last) >= CHECK_INTERVAL_SECONDS


def check_async(db, callback=None) -> threading.Thread:
    """Kick off a check in a background thread.

    The thread:
      1. Marks ``last_update_check`` immediately so a flapping check
         doesn't fan out into N concurrent fetches if called rapidly.
      2. Fetches + parses the latest release.
      3. Hands the result to the GTK main loop via ``GLib.idle_add``,
         which persists ``latest_known_version`` and then calls
         ``callback(is_newer, latest_version, url)``. SQLite is never
         touched from the thread. ``callback`` may be ``None``.

    Returns the started thread (useful for tests that want to ``join``).
    """
    db.set_setting(SETTING_LAST_CHECK, str(time.time()))

    def _run() -> None:
        is_newer, latest, url = check_for_update()

        def _finish():
            # SQLite is only touched from the main loop.
            if latest:
                db.set_setting(SETTING_LATEST_VERSION, latest)
            if callback is not None:
                callback(is_newer, latest, url)
            return False

        try:
            from gi.repository import GLib
            GLib.idle_add(_finish)
        except Exception:
            # No GTK loop (test context) — run inline.
            _finish()

    thread = threading.Thread(target=_run, daemon=True, name="clipman-update-check")
    thread.start()
    return thread


def latest_known(db) -> str | None:
    """Read the cached latest version. ``None`` if never checked."""
    raw = db.get_setting(SETTING_LATEST_VERSION, "")
    return raw or None


def dismissed_version(db) -> str | None:
    raw = db.get_setting(SETTING_DISMISSED_VERSION, "")
    return raw or None


def dismiss(db, version: str) -> None:
    safe = _safe_tag(version)
    if safe is None:
        # Refuse to persist a tag that wouldn't survive a round-trip
        # through _safe_tag — the banner would never re-match it
        # anyway, so storing it just wastes a settings row.
        return
    db.set_setting(SETTING_DISMISSED_VERSION, safe)


def should_show_banner(db, current_version: str = __version__) -> tuple[bool, str | None]:
    """The settings UI calls this to decide whether to show the banner.

    Returns ``(show, latest_version)``. ``show`` is ``True`` only when:
    - the user hasn't opted out;
    - a latest version is cached;
    - that version is strictly newer than ``current_version``;
    - the user hasn't already dismissed that exact version.
    """
    if not _enabled(db):
        return (False, None)
    latest = latest_known(db)
    if not latest:
        return (False, None)
    if not _is_newer(latest, current_version):
        return (False, latest)
    if dismissed_version(db) == latest:
        return (False, latest)
    return (True, latest)


def _enabled(db) -> bool:
    """Read the opt-in flag from the DB, defaulting per install kind."""
    raw = db.get_setting(SETTING_ENABLED, "")
    if raw == "":
        return default_enabled()
    return raw.lower() == "true"


def set_enabled(db, enabled: bool) -> None:
    db.set_setting(SETTING_ENABLED, "true" if enabled else "false")
