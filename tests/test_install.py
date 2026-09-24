"""install.sh, uninstall.sh and the helper they share.

The helper is checked against the parsers that read its output: GLib's
GVariant and shell parsers, GAppInfo, and systemd-analyze. The scripts run
for real in a scratch home. The system tools they call (package manager,
systemctl, gnome-extensions, gdbus) are stubs; gsettings is the real tool
with the keyfile backend and small copies of the GNOME schemas.
"""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

try:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = GLib = None

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "install_helper", ROOT / "scripts" / "install_helper.py"
)
helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helper)

# A folder name with what broke the old sed substitution and the unquoted
# Exec lines: a space, &, |, parentheses, # and ;.
AWKWARD = "My Apps (R&D) | tools #1; naïve"

UUID = "clipman@clipman.com"
KEY_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipman/"
KEY_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:" + KEY_PATH


def _parse(type_string, text):
    return GLib.Variant.parse(GLib.VariantType.new(type_string), text, None, None)


class TestPathCheck(unittest.TestCase):
    def test_accepts_spaces_and_shell_characters(self):
        self.assertEqual(helper.path_problem(f"/home/u/{AWKWARD}/clipman"), "")

    def test_refuses_what_a_unit_or_desktop_entry_cannot_hold(self):
        for char in "%$\"'`\\\n\t\x7f":
            with self.subTest(char=char):
                self.assertNotEqual(helper.path_problem(f"/home/u/a{char}b"), "")

    def test_refuses_a_path_that_is_not_utf8(self):
        self.assertIn("UTF-8", helper.path_problem("/home/u/\udcff"))


class TestStrv(unittest.TestCase):
    def test_add_and_remove_keep_the_other_items(self):
        self.assertEqual(helper.parse_strv("@as []"), [])
        self.assertEqual(helper.format_strv([]), "@as []")
        self.assertEqual(
            helper.format_strv(helper.parse_strv("['a@b', 'c@d']") + [UUID]),
            f"['a@b', 'c@d', '{UUID}']",
        )

    @unittest.skipIf(GLib is None, "needs PyGObject")
    def test_round_trips_through_glib(self):
        items = ["a@b", "it's", 'say "hi"', "back\\slash", "ü"]
        # What `gsettings get` prints, and what `gsettings set` parses.
        self.assertEqual(helper.parse_strv(GLib.Variant("as", items).print_(True)), items)
        self.assertEqual(_parse("as", helper.format_strv(items)).unpack(), items)
        self.assertEqual(_parse("as", helper.format_strv([])).unpack(), [])


class TestSupportsShell(unittest.TestCase):
    def test_compares_the_major_version(self):
        metadata = '{"shell-version": ["45", "46"]}'
        self.assertTrue(helper.supports_shell(metadata, "46.2"))
        self.assertFalse(helper.supports_shell(metadata, "47.0"))

    def test_shipped_metadata_lists_the_supported_shells(self):
        metadata = (ROOT / "extension" / "metadata.json").read_text(encoding="utf-8")
        for version in ("45.0", "50.1"):
            with self.subTest(version=version):
                self.assertTrue(helper.supports_shell(metadata, version))


class TestLauncherQuoting(unittest.TestCase):
    """Each file that names the launcher must start it, with the path whole."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.launcher = self.tmp / AWKWARD / "launcher.sh"
        self.launcher.parent.mkdir()
        self.record = self.tmp / "record"
        self.launcher.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "$0" "$@" > "{self.record}.tmp"\n'
            f'mv "{self.record}.tmp" "{self.record}"\n',
            encoding="utf-8",
        )
        self.launcher.chmod(0o700)

    def wait_for_record(self):
        deadline = time.monotonic() + 10
        while not self.record.exists():
            if time.monotonic() > deadline:
                self.fail("the launcher did not run")
            time.sleep(0.05)
        return self.record.read_text(encoding="utf-8").splitlines()

    def fill(self, template):
        text = (ROOT / "data" / template).read_text(encoding="utf-8")
        target = self.tmp / template
        target.write_text(helper.fill(text, str(self.launcher)), encoding="utf-8")
        return target

    @unittest.skipIf(Gio is None, "needs PyGObject")
    def test_desktop_entry_starts_the_launcher(self):
        entry = self.fill("com.clipman.Clipman.desktop")
        self.assertNotIn("X-GNOME-Autostart-enabled", entry.read_text(encoding="utf-8"))
        info = Gio.DesktopAppInfo.new_from_filename(str(entry))
        self.assertIsNotNone(info)
        info.launch([], None)
        self.assertEqual(self.wait_for_record(), [str(self.launcher)])

    @unittest.skipUnless(shutil.which("systemd-analyze"), "needs systemd-analyze")
    def test_unit_passes_systemd_analyze(self):
        # System mode needs no user session, and it reads ExecStart= by
        # the same rules as --user.
        def verify(unit):
            return subprocess.run(
                ["systemd-analyze", "verify", str(unit)],
                capture_output=True, text=True,
            )

        unit = self.fill("clipman.service")
        result = verify(unit)
        self.assertEqual(result.returncode, 0, result.stderr)
        # A misspelled key only warns, and systemd ignores it.
        self.assertNotIn("Unknown key", result.stderr)
        self.assertNotIn("Unknown section", result.stderr)
        # The old substitution: the unquoted path, split at the space.
        template = (ROOT / "data" / "clipman.service").read_text(encoding="utf-8")
        old = self.tmp / "old.service"
        old.write_text(
            template.replace("CLIPMAN_PATH_PLACEHOLDER", str(self.launcher.parent)),
            encoding="utf-8",
        )
        self.assertNotEqual(verify(old).returncode, 0)

    @unittest.skipIf(Gio is None, "needs PyGObject")
    def test_shortcut_command_runs_like_gnome_settings_daemon(self):
        command = _parse("s", helper.shortcut_command(str(self.launcher))).get_string()
        self.assertEqual(GLib.shell_parse_argv(command)[1], [str(self.launcher), "toggle"])
        # gsd-media-keys (GNOME 45 to 50) doubles each % and launches the
        # command through GAppInfo.
        info = Gio.AppInfo.create_from_commandline(
            command.replace("%", "%%"), None, Gio.AppInfoCreateFlags.NONE
        )
        info.launch([], None)
        self.assertEqual(self.wait_for_record(), [str(self.launcher), "toggle"])
        # The old command was split at the spaces in the path.
        old = f"{self.launcher} toggle"
        self.assertNotEqual(GLib.shell_parse_argv(old)[1], [str(self.launcher), "toggle"])


# Copies of the GNOME keys the scripts touch, with the real types and
# defaults.
GNOME_SCHEMAS = """\
<schemalist>
  <schema id="org.gnome.shell" path="/org/gnome/shell/">
    <key name="enabled-extensions" type="as"><default>[]</default></key>
    <key name="disabled-extensions" type="as"><default>[]</default></key>
    <key name="disable-user-extensions" type="b"><default>false</default></key>
  </schema>
  <schema id="org.gnome.shell.keybindings" path="/org/gnome/shell/keybindings/">
    <key name="toggle-message-tray" type="as">
      <default>['&lt;Super&gt;v', '&lt;Super&gt;m']</default>
    </key>
  </schema>
  <schema id="org.gnome.settings-daemon.plugins.media-keys"
          path="/org/gnome/settings-daemon/plugins/media-keys/">
    <key name="custom-keybindings" type="as"><default>[]</default></key>
  </schema>
  <schema id="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding">
    <key name="name" type="s"><default>''</default></key>
    <key name="command" type="s"><default>''</default></key>
    <key name="binding" type="s"><default>''</default></key>
  </schema>
</schemalist>
"""

# A desktop without GNOME: one unrelated schema, so the directory compiles.
OTHER_SCHEMAS = """\
<schemalist>
  <schema id="org.example.other" path="/org/example/other/">
    <key name="flag" type="b"><default>false</default></key>
  </schema>
</schemalist>
"""

# Each stub logs its call. The STUB_* variables choose what it returns.
STUBS = {
    "apt-get": "exit 0",
    "dpkg-query": "printf 'install ok installed'",
    "sudo": "exit 99",
    "systemctl": "exit 0",
    "update-desktop-database": "exit 0",
    "gdbus": 'exit "${STUB_GDBUS_RC:-1}"',
    # A running Shell refuses an extension it did not find at login.
    "gnome-extensions": 'case "$1" in enable|disable) exit "${STUB_EXT_RC:-2}" ;; esac',
    "gnome-shell": 'echo "GNOME Shell ${STUB_SHELL_VERSION:-50.1}"',
}

CHECKOUT_FILES = (
    "install.sh",
    "uninstall.sh",
    "launcher.sh",
    "clipman.py",
    "scripts/deps.sh",
    "scripts/install_helper.py",
    "extension/extension.js",
    "extension/metadata.json",
    "data/com.clipman.Clipman.desktop",
    "data/com.clipman.Clipman.svg",
    "data/clipman.service",
)


@unittest.skipUnless(
    shutil.which("gsettings") and shutil.which("glib-compile-schemas"),
    "needs gsettings and glib-compile-schemas",
)
class TestInstallScripts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.log = self.base / "stub.log"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        for name, body in STUBS.items():
            stub = self.bin / name
            stub.write_text(
                "#!/bin/bash\n"
                'printf "%s" "${0##*/}" >> "$STUB_LOG"\n'
                'printf " [%s]" "$@" >> "$STUB_LOG"\n'
                'echo >> "$STUB_LOG"\n' + body + "\n",
                encoding="utf-8",
            )
            stub.chmod(0o700)
        self.checkout = self.make_checkout(AWKWARD)
        self.use_schemas(GNOME_SCHEMAS)

    def make_checkout(self, folder):
        checkout = self.base / folder / "clipman"
        for rel in CHECKOUT_FILES:
            (checkout / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, checkout / rel)
        return checkout

    def use_schemas(self, xml):
        self.schemas = self.base / "schemas"
        shutil.rmtree(self.schemas, ignore_errors=True)
        self.schemas.mkdir()
        (self.schemas / "test.gschema.xml").write_text(xml, encoding="utf-8")
        subprocess.run(["glib-compile-schemas", str(self.schemas)], check=True)

    def env(self, **extra):
        # No session bus, runtime dir or display: nothing can reach the
        # live session.
        env = {
            "PATH": f"{self.bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_DIRS": str(self.base / "no-system-data"),
            "GSETTINGS_BACKEND": "keyfile",
            "GSETTINGS_SCHEMA_DIR": str(self.schemas),
            "STUB_LOG": str(self.log),
            "LANG": "C.UTF-8",
        }
        env.update(extra)
        return env

    def run_script(self, name, checkout=None, **extra):
        return subprocess.run(
            ["bash", str((checkout or self.checkout) / name)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            env=self.env(**extra), timeout=120,
        )

    def install(self, **extra):
        result = self.run_script("install.sh", **extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def gget(self, schema, key):
        return subprocess.run(
            ["gsettings", "get", schema, key], env=self.env(),
            capture_output=True, text=True, check=True,
        ).stdout.strip()

    def gset(self, schema, key, value):
        subprocess.run(["gsettings", "set", schema, key, value], env=self.env(), check=True)

    def calls(self):
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    @property
    def launcher(self):
        return str(self.checkout / "launcher.sh")

    def test_fresh_install_enables_the_extension_for_the_next_login(self):
        # Left in disabled-extensions by an earlier uninstall.
        self.gset("org.gnome.shell", "enabled-extensions", "['other@ext']")
        self.gset("org.gnome.shell", "disabled-extensions", f"['{UUID}']")
        out = self.install()
        self.assertEqual(
            helper.parse_strv(self.gget("org.gnome.shell", "enabled-extensions")),
            ["other@ext", UUID],
        )
        self.assertEqual(
            helper.parse_strv(self.gget("org.gnome.shell", "disabled-extensions")), []
        )
        self.assertIn(f"gnome-extensions [enable] [{UUID}]", self.calls())
        self.assertIn("It starts when you log out and back in", out)

    def test_install_writes_the_path_whole_everywhere(self):
        self.install()
        service = self.home / ".config/systemd/user/clipman.service"
        self.assertIn(f'ExecStart="{self.launcher}"', service.read_text(encoding="utf-8"))
        entry = self.home / ".local/share/applications/com.clipman.Clipman.desktop"
        self.assertIn(f'Exec="{self.launcher}"', entry.read_text(encoding="utf-8"))
        self.assertEqual(self.gget(KEY_SCHEMA, "binding"), "'<Super>v'")
        self.assertEqual(self.gget(KEY_SCHEMA, "name"), "'Clipman Toggle'")
        self.assertEqual(
            helper.parse_strv(
                self.gget("org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings")
            ),
            [KEY_PATH],
        )
        self.assertEqual(
            self.gget("org.gnome.shell.keybindings", "toggle-message-tray"), "['<Super>m']"
        )
        if GLib is not None:
            command = _parse("s", self.gget(KEY_SCHEMA, "command")).get_string()
            self.assertEqual(GLib.shell_parse_argv(command)[1], [self.launcher, "toggle"])
        self.assertIn("systemctl [--user] [enable] [clipman.service]", self.calls())
        self.assertNotIn("sudo", self.calls())

    def test_a_shell_that_knows_the_extension_enables_it(self):
        out = self.install(STUB_EXT_RC="0")
        self.assertIn("Extension enabled", out)
        # The Shell writes the setting itself; the fallback stays out.
        self.assertEqual(self.gget("org.gnome.shell", "enabled-extensions"), "@as []")

    def test_rerun_keeps_a_shortcut_the_user_changed(self):
        self.install()
        self.gset(KEY_SCHEMA, "binding", "<Super><Shift>v")
        self.gset("org.gnome.shell.keybindings", "toggle-message-tray", "['<Super>v', '<Super>m']")
        out = self.install()
        self.assertEqual(self.gget(KEY_SCHEMA, "binding"), "'<Super><Shift>v'")
        # Super+V is not Clipman's any more, so the tray keeps it.
        self.assertEqual(
            self.gget("org.gnome.shell.keybindings", "toggle-message-tray"),
            "['<Super>v', '<Super>m']",
        )
        self.assertIn("Keeping your shortcut: <Super><Shift>v", out)

    def test_warns_when_the_extension_cannot_load(self):
        self.gset("org.gnome.shell", "disable-user-extensions", "true")
        out = self.install(STUB_SHELL_VERSION="99.1")
        self.assertIn("extensions are turned off in GNOME", out)
        self.assertIn("does not list GNOME Shell 99.1", out)

    def test_install_without_gnome_still_installs_the_service(self):
        self.use_schemas(OTHER_SCHEMAS)
        out = self.install()
        self.assertIn("GNOME Shell was not found", out)
        self.assertIn("Bind a key to this command", out)
        self.assertNotIn("gnome-extensions", self.calls())
        self.assertTrue((self.home / ".config/systemd/user/clipman.service").exists())

    def test_install_refuses_a_path_it_cannot_write(self):
        checkout = self.make_checkout("Bob's apps")
        result = self.run_script("install.sh", checkout=checkout)
        self.assertEqual(result.returncode, 1)
        self.assertIn("contains '", result.stderr)
        self.assertFalse((self.home / ".config/systemd/user/clipman.service").exists())
        self.assertFalse((self.home / ".local/share/gnome-shell").exists())

    def test_uninstall_without_a_terminal(self):
        self.install()
        data = self.home / ".local/share/clipman"
        self.assertTrue((data / "toggle-message-tray.orig").exists())
        result = self.run_script("uninstall.sh", STUB_GDBUS_RC="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # No terminal to ask: the history stays.
        self.assertIn("Data kept in", result.stdout)
        self.assertTrue(data.is_dir())
        # A daemon started by hand is asked to quit.
        self.assertIn("[--method] [com.clipman.Daemon.Quit]", self.calls())
        self.assertIn("Running daemon stopped", result.stdout)
        # The Shell never loaded the extension, so the setting is edited.
        self.assertEqual(self.gget("org.gnome.shell", "enabled-extensions"), "@as []")
        self.assertEqual(
            self.gget("org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"),
            "@as []",
        )
        self.assertEqual(
            self.gget("org.gnome.shell.keybindings", "toggle-message-tray"),
            "['<Super>v', '<Super>m']",
        )
        self.assertFalse((self.home / ".config/systemd/user/clipman.service").exists())
        self.assertFalse((self.home / ".local/share/gnome-shell/extensions" / UUID).exists())


if __name__ == "__main__":
    unittest.main()
