"""Keep the test suite away from the user's real data and desktop.

This runs before any test module imports clipman. Both runners import the
tests as a package: pytest, and `unittest discover -s tests -t .`, which
is what scripts/dev.sh runs.
"""

import atexit
import os
import shutil
import tempfile

# clipman.database takes its paths from Path.home() when it is imported,
# and GLib and GTK read HOME and the XDG variables. A scratch home means
# no test, and no process a test starts, can open, migrate or delete the
# real ~/.local/share/clipman.
_home = tempfile.mkdtemp(prefix="clipman-tests-")
atexit.register(shutil.rmtree, _home, ignore_errors=True)
os.environ["HOME"] = _home
for _name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
    os.environ[_name] = os.path.join(_home, _name[4:-5].lower())

# The keybinding code runs `gsettings set`. With the default backend that
# writes the user's real GNOME settings; the memory backend keeps nothing.
os.environ["GSETTINGS_BACKEND"] = "memory"
# GTK's in-process accessibility backend: widgets keep their accessible
# names, so tests can check them, and nothing talks to the session's
# accessibility bus. ("none" dropped the names.)
os.environ["GTK_A11Y"] = "test"
os.environ["NO_AT_BRIDGE"] = "1"


def _private_display():
    """Return True if DISPLAY belongs to a server made for this run."""
    if os.environ.get("CLIPMAN_TEST_PRIVATE_DISPLAY") == "1":
        return True
    # xvfb-run keeps its X authority file in a folder named xvfb-run.XXXXXX.
    return "xvfb-run." in os.environ.get("XAUTHORITY", "")


# GTK must never reach the live session: many tests leave a window
# mapped, and one writes the clipboard. GDK's Wayland backend falls back
# to the default socket (wayland-0) even without WAYLAND_DISPLAY, so it is
# not allowed at all. X11 is used only on a private server. Broadway is
# always a private server, and needs no DISPLAY.
os.environ.pop("WAYLAND_DISPLAY", None)
if os.environ.get("GDK_BACKEND") != "broadway":
    os.environ["GDK_BACKEND"] = "x11"
if not _private_display():
    os.environ.pop("DISPLAY", None)
