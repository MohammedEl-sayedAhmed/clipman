"""The packaging files must agree on the version and the tarball hash."""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# What scripts/bump-version.sh edits and scripts/release-preflight.sh
# reads, and the scripts themselves.
BUMPED_FILES = (
    "pyproject.toml",
    "clipman/_version.py",
    "snap/snapcraft.yaml",
    "aur/PKGBUILD",
    "aur/.SRCINFO",
    "CITATION.cff",
    "CHANGELOG.md",
    "scripts/bump-version.sh",
    "scripts/update-aur.sh",
    "scripts/release-preflight.sh",
)
BUMPED_GLOBS = ("flathub/*.json", "data/*.metainfo.xml")


def _read(rel, root=ROOT):
    return (root / rel).read_text(encoding="utf-8")


def _first(pattern, text):
    match = re.search(pattern, text, re.M)
    return match.group(1) if match else None


def _versions(root):
    """Return the version that each packaging file under root carries."""
    manifest = next(root.glob("flathub/*.json"))
    found = {
        "clipman/_version.py": _first(
            r'^__version__ = "([^"]+)"', _read("clipman/_version.py", root)
        ),
        "snap/snapcraft.yaml": _first(
            r"^version: '([^']+)'", _read("snap/snapcraft.yaml", root)
        ),
        "CITATION.cff": _first(r"^version: (\S+)", _read("CITATION.cff", root)),
        "aur/PKGBUILD": _first(r"^pkgver=(\S+)", _read("aur/PKGBUILD", root)),
        "aur/.SRCINFO": _first(r"^\tpkgver = (\S+)", _read("aur/.SRCINFO", root)),
        manifest.name: _first(
            r"/clipman/archive/refs/tags/v([^/\"]+)\.tar\.gz",
            manifest.read_text(encoding="utf-8"),
        ),
    }
    for metainfo in sorted(root.glob("data/*.metainfo.xml")):
        found[metainfo.name] = _first(
            r'<release version="([^"]+)"', metainfo.read_text(encoding="utf-8")
        )
    return found


def _copy_release_files(dest):
    """Copy the files a release bump touches into dest."""
    sources = [ROOT / rel for rel in BUMPED_FILES]
    for pattern in BUMPED_GLOBS:
        sources.extend(ROOT.glob(pattern))
    for src in sources:
        target = dest / src.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


def _preflight(root, version):
    """Run the release workflow's version check in root."""
    return subprocess.run(
        ["bash", "scripts/release-preflight.sh", version],
        cwd=root, capture_output=True, text=True,
    )


def _srcinfo(root):
    """Return the .SRCINFO that update-aur.sh renders from root's PKGBUILD."""
    return subprocess.run(
        ["bash", "scripts/update-aur.sh", "--print-srcinfo"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout


class TestReleaseMetadata(unittest.TestCase):
    def test_version_is_the_same_everywhere(self):
        version = _first(r'^version = "([^"]+)"', _read("pyproject.toml"))
        for name, value in _versions(ROOT).items():
            with self.subTest(file=name):
                self.assertEqual(value, version)

    def test_srcinfo_matches_pkgbuild(self):
        self.assertEqual(_srcinfo(ROOT), _read("aur/.SRCINFO"))

    def test_bump_version_moves_every_file(self):
        # A file the bump leaves behind fails the release pre-flight and
        # the two tests above. aur/.SRCINFO was one, before the bump
        # rendered it.
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            _copy_release_files(copy)
            subprocess.run(
                ["bash", "scripts/bump-version.sh", "9.8.7"],
                cwd=copy, capture_output=True, text=True, check=True,
            )
            self.assertEqual(
                _first(r'^version = "([^"]+)"', _read("pyproject.toml", copy)),
                "9.8.7",
            )
            for name, value in _versions(copy).items():
                with self.subTest(file=name):
                    self.assertEqual(value, "9.8.7")
            self.assertEqual(_srcinfo(copy), _read("aur/.SRCINFO", copy))

    def test_preflight_passes_on_this_checkout(self):
        # main always carries a released version with a dated CHANGELOG
        # section, and a release PR must too.
        version = _first(r'^version = "([^"]+)"', _read("pyproject.toml"))
        result = _preflight(ROOT, version)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_preflight_names_each_mismatch(self):
        result = _preflight(ROOT, "0.0.1")
        self.assertEqual(result.returncode, 1)
        for name in ("pyproject.toml", "aur/.SRCINFO", "flathub-manifest", "CHANGELOG.md"):
            with self.subTest(file=name):
                self.assertIn(f"::error::{name}", result.stdout)

    def test_release_path_from_bump_to_preflight(self):
        # The documented path: bump-version.sh, then the dated CHANGELOG
        # section. The release workflow's pre-flight must accept the
        # result; the 1.2.2 bump failed it on aur/.SRCINFO.
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            _copy_release_files(copy)
            subprocess.run(
                ["bash", "scripts/bump-version.sh", "9.8.7"],
                cwd=copy, capture_output=True, text=True, check=True,
            )
            result = _preflight(copy, "9.8.7")
            self.assertEqual(result.returncode, 1)
            errors = [line for line in result.stdout.splitlines() if "::error::" in line]
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("CHANGELOG.md", errors[0])
            with open(copy / "CHANGELOG.md", "a", encoding="utf-8") as changelog:
                changelog.write("\n## [9.8.7] - 2026-01-02\n\n- A test release.\n")
            result = _preflight(copy, "9.8.7")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
