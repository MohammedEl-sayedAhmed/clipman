import subprocess
import unittest
from unittest.mock import patch

from clipman import keybindings

# Probe for real GTK / Gdk so the TestKeyvalToBinding class can skip
# cleanly when running on a stock CI image without the typelibs. We do
# NOT mutate sys.modules from these tests — previous iterations stubbed
# ``gi`` in setUp and ``addCleanup``-restored a captured snapshot, but
# the snapshot was taken AFTER the stubs were already installed so
# tearDown left the stub in place and leaked it into every subsequent
# test module (test_window.py errored with AttributeError: 'module'
# object has no attribute 'require_version'). Skipping is simpler and
# safer than mock-patching sys.modules.
try:
    import importlib

    import gi
    gi.require_version("Gdk", "4.0")
    # Touching the attribute is the actual typelib probe: importing
    # ``gi.repository`` succeeds even when the Gdk typelib is missing,
    # but the attribute lookup raises in that case. Using importlib
    # avoids binding an unused name (CodeQL py/unused-import fires on
    # ``from gi.repository import Gdk as _RealGdk`` even with a ruff
    # suppression comment).
    importlib.import_module("gi.repository").Gdk
    _HAS_GDK = True
except (ImportError, ValueError, AttributeError, RuntimeError):
    _HAS_GDK = False


class TestFormatBindingForDisplay(unittest.TestCase):
    def test_super_v(self):
        self.assertEqual(
            keybindings.format_binding_for_display("<Super>v"), "Super+V"
        )

    def test_ctrl_shift_v(self):
        self.assertEqual(
            keybindings.format_binding_for_display("<Ctrl><Shift>v"),
            "Ctrl+Shift+V",
        )

    def test_shift_insert(self):
        self.assertEqual(
            keybindings.format_binding_for_display("<Shift>Insert"),
            "Shift+Insert",
        )

    def test_super_only(self):
        self.assertEqual(
            keybindings.format_binding_for_display("<Super>"), "Super"
        )

    def test_empty(self):
        self.assertEqual(keybindings.format_binding_for_display(""), "")

    def test_no_modifiers_single_letter_uppercased(self):
        self.assertEqual(keybindings.format_binding_for_display("a"), "A")

    def test_multichar_keyname_titled(self):
        self.assertEqual(
            keybindings.format_binding_for_display("<Ctrl>F1"),
            "Ctrl+F1",
        )


class TestIsClipmanBindingRegistered(unittest.TestCase):
    def test_registered_list_contains_clipman_path(self):
        out = (
            "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipman/']"
        )
        with patch("clipman.keybindings._gsettings_get", return_value=out):
            self.assertTrue(keybindings.is_clipman_binding_registered())

    def test_registered_in_multi_path_list(self):
        out = (
            "['/org/.../custom-keybindings/other/', "
            "'/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipman/']"
        )
        with patch("clipman.keybindings._gsettings_get", return_value=out):
            self.assertTrue(keybindings.is_clipman_binding_registered())

    def test_not_registered_empty_list(self):
        with patch("clipman.keybindings._gsettings_get", return_value="@as []"):
            self.assertFalse(keybindings.is_clipman_binding_registered())

    def test_not_registered_other_paths_only(self):
        out = "['/org/.../custom-keybindings/other/']"
        with patch("clipman.keybindings._gsettings_get", return_value=out):
            self.assertFalse(keybindings.is_clipman_binding_registered())

    def test_gsettings_unavailable(self):
        with patch("clipman.keybindings._gsettings_get", return_value=None):
            self.assertFalse(keybindings.is_clipman_binding_registered())

    def test_garbage_output(self):
        with patch("clipman.keybindings._gsettings_get", return_value="not parseable"):
            self.assertFalse(keybindings.is_clipman_binding_registered())


class TestGetSetToggleBinding(unittest.TestCase):
    def test_get_strips_quotes_and_whitespace(self):
        with patch("clipman.keybindings._gsettings_get", return_value="  '<Super>v'  "):
            self.assertEqual(keybindings.get_toggle_binding(), "<Super>v")

    def test_get_returns_none_when_unavailable(self):
        with patch("clipman.keybindings._gsettings_get", return_value=None):
            self.assertIsNone(keybindings.get_toggle_binding())

    def test_set_passes_quoted_binding_to_gsettings(self):
        with patch("clipman.keybindings._gsettings_set", return_value=True) as mset:
            self.assertTrue(keybindings.set_toggle_binding("<Shift><Super>v"))
            mset.assert_called_once_with(
                keybindings.CUSTOM_KEY_SUBSCHEMA,
                "binding",
                "'<Shift><Super>v'",
                path=keybindings.CUSTOM_KEY_PATH,
            )

    def test_set_returns_false_on_failure(self):
        with patch("clipman.keybindings._gsettings_set", return_value=False):
            self.assertFalse(keybindings.set_toggle_binding("<Super>v"))


class TestGsettingsShellouts(unittest.TestCase):
    @patch("clipman.keybindings.subprocess.check_output")
    def test_get_uses_path_suffix_when_provided(self, mock_check):
        mock_check.return_value = "'<Super>v'\n"
        keybindings._gsettings_get(
            keybindings.CUSTOM_KEY_SUBSCHEMA, "binding",
            path=keybindings.CUSTOM_KEY_PATH,
        )
        cmd = mock_check.call_args[0][0]
        self.assertEqual(cmd[0:2], ["gsettings", "get"])
        self.assertTrue(cmd[2].endswith(":" + keybindings.CUSTOM_KEY_PATH))
        self.assertEqual(cmd[3], "binding")

    @patch("clipman.keybindings.subprocess.check_output")
    def test_get_returns_none_when_gsettings_missing(self, mock_check):
        mock_check.side_effect = FileNotFoundError("no gsettings")
        self.assertIsNone(
            keybindings._gsettings_get(keybindings.CUSTOM_KEYS_SCHEMA, "x")
        )

    @patch("clipman.keybindings.subprocess.check_output")
    def test_get_returns_none_on_timeout(self, mock_check):
        mock_check.side_effect = subprocess.TimeoutExpired(cmd="gsettings", timeout=5)
        self.assertIsNone(
            keybindings._gsettings_get(keybindings.CUSTOM_KEYS_SCHEMA, "x")
        )

    @patch("clipman.keybindings.subprocess.check_call")
    def test_set_returns_true_on_success(self, mock_call):
        mock_call.return_value = 0
        self.assertTrue(
            keybindings._gsettings_set(
                keybindings.CUSTOM_KEY_SUBSCHEMA, "binding", "'<Super>v'",
                path=keybindings.CUSTOM_KEY_PATH,
            )
        )

    @patch("clipman.keybindings.subprocess.check_call")
    def test_set_returns_false_on_nonzero_exit(self, mock_call):
        mock_call.side_effect = subprocess.CalledProcessError(1, "gsettings")
        self.assertFalse(
            keybindings._gsettings_set(
                keybindings.CUSTOM_KEY_SUBSCHEMA, "binding", "'<Super>v'",
                path=keybindings.CUSTOM_KEY_PATH,
            )
        )


@unittest.skipUnless(_HAS_GDK, "gi.repository.Gdk not importable")
class TestKeyvalToBinding(unittest.TestCase):
    """Exercise keyval_to_binding against the REAL Gdk typelib.

    Previously this class stubbed ``gi`` in ``sys.modules`` for the
    duration of each test. That approach was fragile: the snapshot used
    to "restore" the original modules was captured AFTER the stubs were
    installed, so tearDown re-stamped the stub into ``sys.modules`` and
    every later test module (e.g. ``test_window``) ran against the
    broken shim. Skipping when GTK isn't available is cleaner — the
    rest of test_keybindings doesn't need GTK at all.
    """

    def setUp(self):
        from gi.repository import Gdk
        self._Gdk = Gdk
        self._ModifierType = Gdk.ModifierType
        # GTK 4 renamed MOD1_MASK -> ALT_MASK. Resolve at runtime so a
        # contributor running GTK 3 introspection bindings (vanishingly
        # rare but possible) doesn't see a spurious test failure.
        self._ALT_MASK = getattr(
            Gdk.ModifierType, "ALT_MASK",
            getattr(Gdk.ModifierType, "MOD1_MASK", 0),
        )

    def _keyval(self, name):
        # Map symbolic names to keyvals via the real typelib so we
        # don't have to hard-code Gdk.KEY_* constants here.
        kv = getattr(self._Gdk, f"KEY_{name}", None)
        if kv is None:
            self.fail(f"Gdk has no KEY_{name}")
        return kv

    def test_super_v(self):
        m = self._ModifierType.SUPER_MASK
        self.assertEqual(
            keybindings.keyval_to_binding(self._keyval("v"), m), "<Super>v"
        )

    def test_ctrl_shift_v(self):
        m = self._ModifierType.CONTROL_MASK | self._ModifierType.SHIFT_MASK
        self.assertEqual(
            keybindings.keyval_to_binding(self._keyval("v"), m),
            "<Ctrl><Shift>v",
        )

    def test_shift_insert(self):
        m = self._ModifierType.SHIFT_MASK
        self.assertEqual(
            keybindings.keyval_to_binding(self._keyval("Insert"), m),
            "<Shift>Insert",
        )

    def test_rejects_pure_modifier_key(self):
        m = self._ModifierType.SHIFT_MASK
        self.assertIsNone(
            keybindings.keyval_to_binding(self._keyval("Shift_L"), m)
        )

    def test_rejects_no_modifier(self):
        self.assertIsNone(
            keybindings.keyval_to_binding(self._keyval("v"), 0)
        )

    def test_rejects_when_keyval_name_returns_none(self):
        # Real Gdk.keyval_name returns a hex-string for any int it
        # doesn't recognise, so we can't drive the "unknown keyval"
        # reject path with a fixture int. Patch keyval_name to None
        # directly — that's the contract keyval_to_binding actually
        # guards (``if not name``).
        m = self._ModifierType.SUPER_MASK
        with patch.object(self._Gdk, "keyval_name", return_value=None):
            self.assertIsNone(keybindings.keyval_to_binding(0x76, m))

    def test_alt_plus_function_key(self):
        m = self._ALT_MASK
        self.assertEqual(
            keybindings.keyval_to_binding(self._keyval("F1"), m), "<Alt>F1"
        )

    def test_all_four_modifiers(self):
        m = (self._ModifierType.CONTROL_MASK
             | self._ModifierType.SHIFT_MASK
             | self._ALT_MASK
             | self._ModifierType.SUPER_MASK)
        self.assertEqual(
            keybindings.keyval_to_binding(self._keyval("v"), m),
            "<Ctrl><Super><Alt><Shift>v",
        )

    def test_round_trip_super_v(self):
        # keyval_to_binding(...) -> format_binding_for_display(...)
        m = self._ModifierType.SUPER_MASK
        b = keybindings.keyval_to_binding(self._keyval("v"), m)
        self.assertEqual(keybindings.format_binding_for_display(b), "Super+V")

    def test_round_trip_ctrl_shift_v(self):
        m = self._ModifierType.CONTROL_MASK | self._ModifierType.SHIFT_MASK
        b = keybindings.keyval_to_binding(self._keyval("v"), m)
        self.assertEqual(
            keybindings.format_binding_for_display(b), "Ctrl+Shift+V"
        )


if __name__ == "__main__":
    unittest.main()
