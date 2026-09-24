"""scripts/snap-plan.sh decides what snap-refresh builds and publishes.

A wrong plan publishes main to stable, or rolls stable back to an older
release. The script runs here with stand-ins for gh (the latest GitHub
Release) and curl (the Snap Store's channel map); jq is the real one.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "snap-plan.sh"

# gh prints STUB_TAG. curl prints a channel map with STUB_STORE on stable,
# or fails like a store outage when STUB_STORE is empty.
STUBS = {
    "gh": 'printf "%s\\n" "$STUB_TAG"',
    "curl": """[ -n "$STUB_STORE" ] || exit 22
printf '{"channel-map": [
  {"channel": {"name": "stable", "architecture": "amd64"}, "version": "%s"},
  {"channel": {"name": "edge", "architecture": "amd64"}, "version": "9.9.9"}
]}\\n' "$STUB_STORE"
""",
}

FULL = [
    {"ref": "main", "channels": "edge", "slug": "edge"},
    {"ref": "v1.2.1", "channels": "beta,candidate,stable", "slug": "stable"},
]
EDGE_ONLY = [{"ref": "main", "channels": "edge", "slug": "edge"}]


@unittest.skipUnless(shutil.which("jq"), "needs jq")
class TestSnapPlan(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for name, body in STUBS.items():
            stub = bin_dir / name
            stub.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
            stub.chmod(0o700)
        self.path = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"

    def plan(self, event, channel="", tag="v1.2.1", store="1.2.1"):
        """Return (exit code, matrix or None, output) for one run."""
        output = self.tmp / "github_output"
        output.write_text("", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            env={
                "PATH": self.path,
                "EVENT": event,
                "CHANNEL": channel,
                "GITHUB_REPOSITORY": "owner/clipman",
                "GITHUB_OUTPUT": str(output),
                "STUB_TAG": tag,
                "STUB_STORE": store,
            },
            capture_output=True, text=True, timeout=30,
        )
        matrix = None
        for line in output.read_text(encoding="utf-8").splitlines():
            if line.startswith("matrix="):
                matrix = json.loads(line[len("matrix="):])
        return result.returncode, matrix, result.stdout + result.stderr

    def test_schedule_rebuilds_edge_and_the_release(self):
        rc, matrix, _ = self.plan("schedule")
        self.assertEqual((rc, matrix), (0, FULL))

    def test_schedule_skips_stable_when_the_store_is_ahead(self):
        # A release reached the store but not the GitHub Release.
        rc, matrix, out = self.plan("schedule", store="1.2.2")
        self.assertEqual((rc, matrix), (0, EDGE_ONLY))
        self.assertIn("::warning::", out)

    def test_schedule_rebuilds_when_the_store_is_behind(self):
        rc, matrix, _ = self.plan("schedule", store="1.2.0")
        self.assertEqual((rc, matrix), (0, FULL))

    def test_versions_compare_as_versions_not_text(self):
        rc, matrix, _ = self.plan("schedule", tag="v1.9.0", store="1.10.0")
        self.assertEqual((rc, matrix), (0, EDGE_ONLY))

    def test_store_outage_keeps_the_weekly_rebuild(self):
        rc, matrix, _ = self.plan("schedule", store="")
        self.assertEqual((rc, matrix), (0, FULL))

    def test_no_release_tag_never_falls_back_to_main(self):
        for tag in ("", "main", "latest"):
            with self.subTest(tag=tag):
                rc, matrix, out = self.plan("schedule", tag=tag)
                self.assertEqual(rc, 1)
                self.assertIsNone(matrix)
                self.assertIn("could not resolve the latest release tag", out)

    def test_dispatch_to_stable_refuses_when_the_store_is_ahead(self):
        rc, matrix, out = self.plan("workflow_dispatch", channel="stable", store="1.2.2")
        self.assertEqual(rc, 1)
        self.assertIsNone(matrix)
        self.assertIn("::error::", out)

    def test_dispatch_to_stable_builds_the_release_tag(self):
        rc, matrix, _ = self.plan("workflow_dispatch", channel="stable")
        self.assertEqual(
            (rc, matrix), (0, [{"ref": "v1.2.1", "channels": "stable", "slug": "stable"}])
        )

    def test_dispatch_to_edge_builds_main(self):
        # Edge never needs the release lookup, even when it would fail.
        rc, matrix, _ = self.plan("workflow_dispatch", channel="edge", tag="", store="")
        self.assertEqual((rc, matrix), (0, [{"ref": "main", "channels": "edge", "slug": "edge"}]))

    def test_push_only_builds(self):
        for event in ("push", "pull_request"):
            with self.subTest(event=event):
                rc, matrix, _ = self.plan(event)
                self.assertEqual((rc, matrix), (0, [{"ref": "", "channels": "", "slug": "ci"}]))


if __name__ == "__main__":
    unittest.main()
