"""The packaging files must agree on the version and the tarball hash."""

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _first(pattern, text):
    match = re.search(pattern, text, re.M)
    return match.group(1) if match else None


class TestReleaseMetadata(unittest.TestCase):
    def test_version_is_the_same_everywhere(self):
        version = _first(r'^version = "([^"]+)"', _read("pyproject.toml"))
        manifest = next(ROOT.glob("flathub/*.json"))
        found = {
            "clipman/_version.py": _first(
                r'^__version__ = "([^"]+)"', _read("clipman/_version.py")
            ),
            "snap/snapcraft.yaml": _first(
                r"^version: '([^']+)'", _read("snap/snapcraft.yaml")
            ),
            "CITATION.cff": _first(r"^version: (\S+)", _read("CITATION.cff")),
            "aur/PKGBUILD": _first(r"^pkgver=(\S+)", _read("aur/PKGBUILD")),
            "aur/.SRCINFO": _first(r"^\tpkgver = (\S+)", _read("aur/.SRCINFO")),
            manifest.name: _first(
                r"/clipman/archive/refs/tags/v([^/\"]+)\.tar\.gz",
                manifest.read_text(encoding="utf-8"),
            ),
        }
        for metainfo in sorted(ROOT.glob("data/*.metainfo.xml")):
            found[metainfo.name] = _first(
                r'<release version="([^"]+)"', metainfo.read_text(encoding="utf-8")
            )
        for name, value in found.items():
            with self.subTest(file=name):
                self.assertEqual(value, version)

    def test_srcinfo_matches_pkgbuild(self):
        result = subprocess.run(
            ["bash", "scripts/update-aur.sh", "--print-srcinfo"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout, _read("aur/.SRCINFO"))

    def test_tarball_hash_is_the_same_in_aur_and_flatpak(self):
        sha = _first(r"^sha256sums=\('([0-9a-f]{64})'\)", _read("aur/PKGBUILD"))
        self.assertIsNotNone(sha)
        self.assertIn(f"sha256sums = {sha}", _read("aur/.SRCINFO"))
        manifest = json.loads(next(ROOT.glob("flathub/*.json")).read_text())
        module = next(m for m in manifest["modules"] if m["name"] == "clipman")
        archive = next(s for s in module["sources"] if s.get("type") == "archive")
        self.assertEqual(archive["sha256"], sha)


if __name__ == "__main__":
    unittest.main()
