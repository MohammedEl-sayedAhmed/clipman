"""scripts/deps.sh --install tries once more when the package manager fails.

Stub apt-get, apt-cache, dpkg-query and sudo stand in for the real ones,
so nothing is installed and no root is needed.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPS = ROOT / "scripts" / "deps.sh"

STUBS = {
    # Passwordless sudo: run the command as is.
    "sudo": 'if [ "$1" = "-n" ]; then shift; fi\nexec "$@"',
    "apt-cache": 'echo "  Candidate: 1.0"',
    # Everything counts as installed once an install has succeeded.
    "dpkg-query": '[ -e "$STATE/installed" ] && printf "install ok installed"\nexit 0',
    # The first FAIL_INSTALLS installs fail, like a dropped mirror.
    "apt-get": (
        'echo " $* " >> "$STATE/calls"\n'
        'case " $* " in *" install "*)\n'
        '  n=$(grep -c " install " "$STATE/calls")\n'
        '  if [ "$n" -le "${FAIL_INSTALLS:-0}" ]; then exit 100; fi\n'
        '  touch "$STATE/installed" ;;\n'
        'esac\n'
        'exit 0'
    ),
}


class TestInstallRetry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.state = self.base / "state"
        self.state.mkdir()
        stubs = self.base / "bin"
        stubs.mkdir()
        for name, body in STUBS.items():
            stub = stubs / name
            stub.write_text("#!/bin/bash\n" + body + "\n", encoding="utf-8")
            stub.chmod(0o700)
        self.path = f"{stubs}:/usr/bin:/bin"

    def run_deps(self, *args, fail_installs=0):
        env = {
            "PATH": self.path,
            "HOME": str(self.base),
            "STATE": str(self.state),
            "FAIL_INSTALLS": str(fail_installs),
            "CLIPMAN_DEPS_RETRY_DELAY": "0",
            "LANG": "C.UTF-8",
        }
        return subprocess.run(
            ["bash", str(DEPS), "--runtime", "--install", *args],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            env=env, timeout=60,
        )

    def calls(self, verb):
        log = self.state / "calls"
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return [line for line in lines if f" {verb} " in f" {line} "]

    def test_a_failed_install_is_tried_once_more(self):
        result = self.run_deps("--yes", fail_installs=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("trying once more", result.stderr)
        self.assertEqual(len(self.calls("install")), 2)
        # The retry refreshes the package lists too.
        self.assertEqual(len(self.calls("update")), 2)

    def test_it_gives_up_after_the_second_failure(self):
        result = self.run_deps("--yes", fail_installs=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn("package installation failed", result.stderr)
        self.assertEqual(len(self.calls("install")), 2)

    def test_no_retry_when_a_person_could_answer(self):
        # Without --yes (and not on CI), apt asks the person, and a "no"
        # must not be asked again.
        result = self.run_deps(fail_installs=1)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("trying once more", result.stderr)
        self.assertEqual(len(self.calls("install")), 1)

    def test_a_first_success_runs_once(self):
        result = self.run_deps("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("trying once more", result.stderr)
        self.assertEqual(len(self.calls("install")), 1)


if __name__ == "__main__":
    unittest.main()
