"""The diagrams in the docs: scripts/diagrams.py draws them.

The committed SVGs must match what the script draws, be valid SVG, keep
the project's contrast rules (4.5:1 for text, 3:1 for lines) in both
themes, and be the ones the docs show.
"""
import importlib.util
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "diagrams", ROOT / "scripts" / "diagrams.py"
)
diagrams = importlib.util.module_from_spec(_SPEC)
# dataclasses look the module up by name while the script runs.
sys.modules[_SPEC.name] = diagrams
_SPEC.loader.exec_module(diagrams)

SVG = "{http://www.w3.org/2000/svg}"


def luminance(color):
    channels = []
    for i in (1, 3, 5):
        c = int(color[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def blend(base, top, alpha):
    """``top`` at ``alpha`` over ``base``, as a hex colour."""
    mix = []
    for i in (1, 3, 5):
        b, t = int(base[i:i + 2], 16), int(top[i:i + 2], 16)
        mix.append(round(b + (t - b) * alpha))
    return "#" + "".join(f"{c:02x}" for c in mix)


class TestFiles(unittest.TestCase):
    def test_the_committed_svgs_match_the_script(self):
        """Run scripts/diagrams.py and commit what it writes."""
        for path, content in diagrams.outputs().items():
            with self.subTest(path=path.name):
                self.assertTrue(path.exists(), f"{path.name} is missing")
                self.assertEqual(path.read_text(encoding="utf-8"), content,
                                 f"{path.name} is out of date")

    def test_no_stray_svgs(self):
        expected = {p.name for p in diagrams.outputs()}
        present = {p.name for p in diagrams.OUT.glob("*.svg")}
        self.assertEqual(present, expected)

    def test_each_svg_is_an_accessible_image(self):
        for path in diagrams.outputs():
            with self.subTest(path=path.name):
                root = ET.parse(path).getroot()
                self.assertEqual(root.tag, SVG + "svg")
                self.assertEqual(root.get("role"), "img")
                self.assertTrue(root.find(SVG + "title").text)
                self.assertGreater(len(root.find(SVG + "desc").text), 100)

    def test_light_and_dark_differ_only_in_colour(self):
        def shape(path):
            text = path.read_text(encoding="utf-8")
            return re.sub(r'#[0-9a-f]{6}|(?<=opacity=")[0-9.]+', "C", text)

        names = {p.name.rsplit("-", 1)[0] for p in diagrams.outputs()}
        for name in names:
            with self.subTest(diagram=name):
                self.assertEqual(shape(diagrams.OUT / f"{name}-light.svg"),
                                 shape(diagrams.OUT / f"{name}-dark.svg"))


class TestContrast(unittest.TestCase):
    """AGENTS.md: 4.5:1 for text, 3:1 for graphics."""

    def test_text_is_readable_in_both_themes(self):
        for name, t in diagrams.THEMES.items():
            pairs = {
                "title on card": (t["text"], t["card"]),
                "title on panel": (t["text"], t["panel"]),
                "subtitle on card": (t["subtext"], t["card"]),
                "muted on panel": (t["muted"], t["panel"]),
                "muted on canvas": (t["muted"], t["canvas"]),
                "badge": (t["badge_text"], t["badge"]),
                "line label": (t["label_text"], t["label"]),
            }
            # A pill sits on the hatched card; count the hatch as tint too.
            for group, color in t["groups"].items():
                tint = t["pill_opacity"] + t["hatch_opacity"]
                pairs[f"{group} pill"] = (color, blend(t["card"], color, tint))
            for what, (fg, bg) in pairs.items():
                with self.subTest(theme=name, pair=what):
                    self.assertGreaterEqual(contrast(fg, bg), 4.5)

    def test_lines_stand_out(self):
        for name, t in diagrams.THEMES.items():
            for bg in ("panel", "canvas"):
                with self.subTest(theme=name, on=bg):
                    self.assertGreaterEqual(contrast(t["edge"], t[bg]), 3)


class TestDocs(unittest.TestCase):
    """The docs show both themes with <picture>, and no Mermaid."""

    SHOWN = {
        "ARCHITECTURE.md": "docs/diagrams/architecture",
        "docs/ci-cd.md": "diagrams/release-pipeline",
        "docs/releases/README.md": "../diagrams/release-pipeline",
    }

    def test_each_doc_shows_its_diagram_in_both_themes(self):
        for doc, stem in self.SHOWN.items():
            text = (ROOT / doc).read_text(encoding="utf-8")
            with self.subTest(doc=doc):
                self.assertIn(f'srcset="{stem}-dark.svg"', text)
                self.assertIn(f'src="{stem}-light.svg"', text)
                for ref in (f"{stem}-dark.svg", f"{stem}-light.svg"):
                    self.assertTrue((ROOT / doc).parent.joinpath(ref).resolve().exists())

    def test_the_docs_have_no_mermaid_left(self):
        docs = [ROOT / "ARCHITECTURE.md", *sorted((ROOT / "docs").rglob("*.md"))]
        for doc in docs:
            with self.subTest(doc=doc.relative_to(ROOT)):
                self.assertNotIn("```mermaid", doc.read_text(encoding="utf-8"))


class TestTextFits(unittest.TestCase):
    def test_a_label_too_long_for_its_box_is_an_error(self):
        with self.assertRaises(ValueError):
            diagrams.check_fits("a label far too long for this box", 12, False, 40)
        diagrams.check_fits("fits", 12, False, 40)


if __name__ == "__main__":
    unittest.main()
