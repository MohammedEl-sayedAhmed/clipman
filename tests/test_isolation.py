"""tests/__init__.py keeps the suite away from the real data and desktop."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from clipman import database

ROOT = Path(__file__).resolve().parent.parent

# Prints what a test module sees once the tests package is imported.
PROBE = (
    "import json, os, tests; "
    "print(json.dumps({k: os.environ.get(k) for k in "
    "('HOME', 'XDG_DATA_HOME', 'GSETTINGS_BACKEND', 'GDK_BACKEND', "
    "'DISPLAY', 'WAYLAND_DISPLAY')}))"
)

# What a terminal on the desktop passes down.
LIVE = {
    "HOME": "/home/someone",
    "DISPLAY": ":0",
    "WAYLAND_DISPLAY": "wayland-0",
    "GDK_BACKEND": "wayland",
}


def _probe(**env):
    base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    result = subprocess.run(
        [sys.executable, "-c", PROBE], cwd=ROOT, env={**base, **env},
        capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(result.stdout)


class TestIsolation(unittest.TestCase):
    def test_this_run_uses_a_scratch_data_dir(self):
        self.assertTrue(
            str(database.DATA_DIR).startswith(tempfile.gettempdir()), database.DATA_DIR
        )
        self.assertIn("clipman-tests-", str(database.DATA_DIR))

    def test_a_desktop_environment_is_cut_off(self):
        seen = _probe(**LIVE)
        self.assertNotEqual(seen["HOME"], LIVE["HOME"])
        self.assertTrue(seen["XDG_DATA_HOME"].startswith(seen["HOME"]))
        self.assertEqual(seen["GSETTINGS_BACKEND"], "memory")
        self.assertEqual(seen["GDK_BACKEND"], "x11")
        self.assertIsNone(seen["WAYLAND_DISPLAY"])
        self.assertIsNone(seen["DISPLAY"])

    def test_xvfb_run_display_is_kept(self):
        seen = _probe(**{**LIVE, "DISPLAY": ":99", "XAUTHORITY": "/tmp/xvfb-run.Ab12/Xauthority"})
        self.assertEqual(seen["DISPLAY"], ":99")
        self.assertEqual(seen["GDK_BACKEND"], "x11")
        self.assertIsNone(seen["WAYLAND_DISPLAY"])

    def test_declared_private_display_is_kept(self):
        seen = _probe(**{**LIVE, "DISPLAY": ":5", "CLIPMAN_TEST_PRIVATE_DISPLAY": "1"})
        self.assertEqual(seen["DISPLAY"], ":5")

    def test_broadway_is_left_alone(self):
        seen = _probe(**{**LIVE, "GDK_BACKEND": "broadway"})
        self.assertEqual(seen["GDK_BACKEND"], "broadway")
        self.assertIsNone(seen["WAYLAND_DISPLAY"])
        self.assertIsNone(seen["DISPLAY"])


if __name__ == "__main__":
    unittest.main()
