"""scripts/release-notes.py writes the GitHub Release text.

For v1.3.0 the notes went missing: GitHub dropped the job output that
carried them. The release job now writes them to a file with this
script.
"""
import contextlib
import importlib.util
import io
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "scripts" / "release-notes.py"
)
release_notes = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release_notes)

CHANGELOG = """\
# Changelog

## [Unreleased]

## [1.3.0] - 2026-10-12

A summary.

### Fixed - one thing

- Detail.

## [1.2.1] - 2026-08-22

Older notes.
"""


class TestSection(unittest.TestCase):
    def test_takes_only_the_versions_section(self):
        notes = release_notes.section(CHANGELOG, "1.3.0")
        self.assertEqual(notes, "A summary.\n\n### Fixed - one thing\n\n- Detail.")

    def test_the_last_section_runs_to_the_end(self):
        self.assertEqual(release_notes.section(CHANGELOG, "1.2.1"), "Older notes.")

    def test_a_missing_or_empty_section_is_none(self):
        for version in ("9.9.9", "Unreleased", "1.3"):
            with self.subTest(version=version):
                self.assertIsNone(release_notes.section(CHANGELOG, version))

    def test_the_version_is_matched_literally(self):
        # "1.3.0" must not match "1x3x0".
        text = "## [1x3x0] - 2026-01-01\n\nWrong.\n"
        self.assertIsNone(release_notes.section(text, "1.3.0"))


class TestBody(unittest.TestCase):
    def test_notes_then_the_files_part_for_this_tag(self):
        text = release_notes.body("A summary.", "1.3.0")
        self.assertTrue(text.startswith("A summary.\n\n---\n\n## Assets\n"))
        self.assertIn("Download `clipman-extension-v1.3.0.zip` and upload it", text)
        self.assertNotIn("TAG", text)

    def test_notes_too_long_for_github_are_cut_before_a_subsection(self):
        part = "### Fixed - something\n\n" + "- a line of detail\n" * 50
        notes = "A summary.\n\n" + "\n".join([part] * 40)
        text = release_notes.body(notes, "1.3.0", limit=8_000)
        self.assertLessEqual(len(text), 8_000)
        kept = text.split("\n\n---\n\n## Assets", 1)[0]
        self.assertTrue(kept.endswith(
            "The full notes are in [CHANGELOG.md](https://github.com/"
            "MohammedEl-sayedAhmed/clipman/blob/v1.3.0/CHANGELOG.md)."))
        # The cut lands between subsections, never inside one.
        self.assertEqual(kept.count("### Fixed"),
                         kept.count("- a line of detail") // 50)

    def test_short_notes_are_kept_whole(self):
        text = release_notes.body("A summary.", "1.3.0")
        self.assertNotIn("The full notes are in", text)


class TestMain(unittest.TestCase):
    def _run(self, version):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = release_notes.main([version])
        return status, out.getvalue(), err.getvalue()

    def test_missing_notes_fail_loudly(self):
        """The old step published "See CHANGELOG.md" instead."""
        status, out, err = self._run("0.0.1")
        self.assertEqual(status, 1)
        self.assertEqual(out, "")
        self.assertIn("::error::CHANGELOG.md has no notes for 0.0.1", err)

    def test_the_released_version_has_notes_that_fit(self):
        """The version in pyproject.toml is either the last release or the
        one being prepared; either way CHANGELOG.md must have its notes."""
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        version = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
        status, out, _err = self._run(version)
        self.assertEqual(status, 0)
        self.assertLessEqual(len(out), release_notes.MAX_BODY)
        self.assertIn(f"clipman-extension-v{version}.zip", out)


if __name__ == "__main__":
    unittest.main()
