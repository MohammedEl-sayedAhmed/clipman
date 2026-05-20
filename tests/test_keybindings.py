import subprocess
import unittest
from unittest.mock import patch

from clipman import keybindings


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


class TestKeyvalToBinding(unittest.TestCase):
    """Use a stub Gdk so the test doesn't require gi at import time."""

    def setUp(self):
        # Inject a fake gi.repository.Gdk into sys.modules so the
        # local-import inside keyval_to_binding picks it up.
        import sys
        import types

        gi_mod = types.ModuleType("gi")
        repo_mod = types.ModuleType("gi.repository")
        gdk_mod = types.ModuleType("gi.repository.Gdk")

        class _ModifierType:
            CONTROL_MASK = 1 << 2
            SHIFT_MASK = 1 << 0
            MOD1_MASK = 1 << 3      # Alt
            SUPER_MASK = 1 << 26

        # Map of fake keyval -> name; only fixtures we use in tests.
        _KEYVAL_NAMES = {
            0x76: "v",
            0xff63: "Insert",
            0xffbe: "F1",
            0xffe1: "Shift_L",
            0xffe3: "Control_L",
        }

        def _keyval_name(keyval):
            return _KEYVAL_NAMES.get(keyval)

        gdk_mod.ModifierType = _ModifierType
        gdk_mod.keyval_name = _keyval_name

        sys.modules["gi"] = gi_mod
        sys.modules["gi.repository"] = repo_mod
        sys.modules["gi.repository.Gdk"] = gdk_mod
        repo_mod.Gdk = gdk_mod
        gi_mod.repository = repo_mod

        self._ModifierType = _ModifierType
        self.addCleanup(self._restore)
        self._original = {
            "gi": sys.modules.get("gi"),
            "gi.repository": sys.modules.get("gi.repository"),
            "gi.repository.Gdk": sys.modules.get("gi.repository.Gdk"),
        }

    def _restore(self):
        import sys
        for k, v in self._original.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_super_v(self):
        m = self._ModifierType.SUPER_MASK
        self.assertEqual(keybindings.keyval_to_binding(0x76, m), "<Super>v")

    def test_ctrl_shift_v(self):
        m = self._ModifierType.CONTROL_MASK | self._ModifierType.SHIFT_MASK
        self.assertEqual(keybindings.keyval_to_binding(0x76, m), "<Ctrl><Shift>v")

    def test_shift_insert(self):
        m = self._ModifierType.SHIFT_MASK
        self.assertEqual(
            keybindings.keyval_to_binding(0xff63, m), "<Shift>Insert"
        )

    def test_rejects_pure_modifier_key(self):
        m = self._ModifierType.SHIFT_MASK
        self.assertIsNone(keybindings.keyval_to_binding(0xffe1, m))

    def test_rejects_no_modifier(self):
        self.assertIsNone(keybindings.keyval_to_binding(0x76, 0))

    def test_rejects_unknown_keyval(self):
        m = self._ModifierType.SUPER_MASK
        self.assertIsNone(keybindings.keyval_to_binding(0xdeadbeef, m))

    def test_alt_plus_function_key(self):
        m = self._ModifierType.MOD1_MASK  # Alt
        self.assertEqual(keybindings.keyval_to_binding(0xffbe, m), "<Alt>F1")

    def test_all_four_modifiers(self):
        m = (self._ModifierType.CONTROL_MASK
             | self._ModifierType.SHIFT_MASK
             | self._ModifierType.MOD1_MASK
             | self._ModifierType.SUPER_MASK)
        self.assertEqual(
            keybindings.keyval_to_binding(0x76, m),
            "<Ctrl><Super><Alt><Shift>v",
        )

    def test_round_trip_super_v(self):
        # keyval_to_binding(...) → format_binding_for_display(...)
        m = self._ModifierType.SUPER_MASK
        b = keybindings.keyval_to_binding(0x76, m)
        self.assertEqual(keybindings.format_binding_for_display(b), "Super+V")

    def test_round_trip_ctrl_shift_v(self):
        m = self._ModifierType.CONTROL_MASK | self._ModifierType.SHIFT_MASK
        b = keybindings.keyval_to_binding(0x76, m)
        self.assertEqual(
            keybindings.format_binding_for_display(b), "Ctrl+Shift+V"
        )


if __name__ == "__main__":
    unittest.main()
