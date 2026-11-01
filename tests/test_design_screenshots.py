"""The website's screenshots of the design pages.

scripts/design-screenshots.py makes them. These tests need no browser:
they check that the files in docs/design/screenshots/ are the ones the
script makes, at the size it gives them, and that the website shows
each one in both themes.
"""
import importlib.util
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "design_screenshots", ROOT / "scripts" / "design-screenshots.py"
)
shots = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(shots)


def png_size(path):
    with open(path, "rb") as png:
        head = png.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} is not a PNG file")
    return struct.unpack(">II", head[16:24])


class TestScreenshots(unittest.TestCase):
    def test_the_folder_holds_exactly_what_the_script_makes(self):
        expected = {path.name for path in shots.outputs()}
        present = {path.name for path in shots.OUT.iterdir()}
        self.assertEqual(present, expected)

    def test_each_screenshot_has_the_size_the_script_gives_it(self):
        for path, (_page, width, height, _element, _theme) in shots.outputs().items():
            with self.subTest(path=path.name):
                self.assertEqual(png_size(path),
                                 (width * shots.SCALE, height * shots.SCALE))

    def test_each_page_exists(self):
        for name, (page, *_rest) in shots.SHOTS.items():
            with self.subTest(name=name):
                self.assertTrue((shots.DOCS / page.split("?")[0]).is_file())

    def test_the_website_shows_each_one_in_both_themes(self):
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        used = set(re.findall(r"design/screenshots/([\w-]+\.png)", html))
        self.assertEqual(used, {path.name for path in shots.outputs()})
        for name in shots.SHOTS:
            with self.subTest(name=name):
                for theme in shots.THEMES:
                    self.assertIn(
                        f'data-img-{theme}="design/screenshots/{name}-{theme}.png"',
                        html)


if __name__ == "__main__":
    unittest.main()
