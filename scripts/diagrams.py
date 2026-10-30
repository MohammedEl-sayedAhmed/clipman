#!/usr/bin/env python3
"""Draw the diagrams in the docs as SVG, in a light and a dark version.

Each diagram is a row of numbered columns. A column holds cards, and
lines between the cards show what calls or feeds what. The colours come
from docs/design/tokens.css: warm stone for light, Catppuccin Mocha for
dark. The docs show the pair with <picture>, so each reader gets the
version that matches their GitHub theme.

    python3 scripts/diagrams.py          # write docs/diagrams/*.svg
    python3 scripts/diagrams.py --check  # exit 1 if a file is out of date

The output depends only on this file, so it is the same on every run.
Text is measured roughly; a label too long for its box is an error, not
an overflow.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "diagrams"

FONT = ("Inter, 'Segoe UI', -apple-system, BlinkMacSystemFont, "
        "'Helvetica Neue', 'Noto Sans', Cantarell, Arial, sans-serif")
MONO = "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace"

# docs/design/tokens.css: warm stone (light), Catppuccin Mocha (dark).
THEMES = {
    "light": {
        "canvas": "#fafaf9", "canvas_line": "#e7e5e4",
        "panel": "#f5f5f4", "panel_line": "#e7e5e4",
        "text": "#1c1917", "subtext": "#44403c", "muted": "#57534e",
        "badge": "#e7e5e4", "badge_text": "#44403c",
        "card": "#ffffff", "card_line_opacity": 0.55, "hatch_opacity": 0.09,
        "pill_opacity": 0.11,
        "edge": "#57534e",
        "label": "#ffffff", "label_line": "#d6d3d1", "label_text": "#44403c",
        # One step darker than the app's accents, so small text on a
        # tinted pill keeps 4.5:1 (tests/test_diagrams.py checks it).
        "groups": {
            "blue": "#1d4ed8", "amber": "#92400e", "violet": "#6d28d9",
            "green": "#166534", "teal": "#115e59", "gray": "#57534e",
        },
    },
    "dark": {
        "canvas": "#1e1e2e", "canvas_line": "#313244",
        "panel": "#181825", "panel_line": "#313244",
        "text": "#cdd6f4", "subtext": "#bac2de", "muted": "#a6adc8",
        "badge": "#313244", "badge_text": "#cdd6f4",
        "card": "#1e1e2e", "card_line_opacity": 0.7, "hatch_opacity": 0.1,
        "pill_opacity": 0.14,
        "edge": "#9399b2",
        "label": "#1e1e2e", "label_line": "#45475a", "label_text": "#bac2de",
        "groups": {
            "blue": "#89b4fa", "amber": "#f9e2af", "violet": "#cba6f7",
            "green": "#a6e3a1", "teal": "#94e2d5", "gray": "#bac2de",
        },
    },
}

# 16 x 16 line icons, drawn with the card's colour.
ICONS = {
    "app": '<rect x="1.5" y="2.5" width="13" height="11" rx="2"/>'
           '<path d="M1.5 5.5h13M4 4h.01M6 4h.01"/>',
    "person": '<circle cx="8" cy="5.2" r="2.7"/>'
              '<path d="M2.8 14c0-2.9 2.3-4.6 5.2-4.6s5.2 1.7 5.2 4.6"/>',
    "keyboard": '<rect x="1.5" y="4" width="13" height="8.5" rx="1.8"/>'
                '<path d="M4 7h.01M6.7 7h.01M9.3 7h.01M12 7h.01M5 10h6"/>',
    "clipboard": '<rect x="3" y="3" width="10" height="11.5" rx="1.8"/>'
                 '<rect x="5.6" y="1.5" width="4.8" height="3" rx="1"/>',
    "puzzle": '<path d="M3 5.5h2.6a1.6 1.6 0 1 1 3.2 0H11.5v2.6a1.6 1.6 0 '
              '1 1 0 3.2V14H3z"/>',
    "eye": '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 '
           '1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>',
    "bus": '<circle cx="3.5" cy="8" r="1.8"/><circle cx="12.5" cy="3.8" '
           'r="1.8"/><circle cx="12.5" cy="12.2" r="1.8"/>'
           '<path d="M5.2 7.2l5.6-2.6M5.2 8.8l5.6 2.6"/>',
    "window": '<rect x="1.5" y="2" width="13" height="12" rx="2"/>'
              '<path d="M4.5 6h7M4.5 8.6h7M4.5 11.2h4.5"/>',
    "refresh": '<path d="M13.2 8a5.2 5.2 0 1 1-1.6-3.8"/>'
               '<path d="M13.2 2.2v2.7h-2.7"/>',
    "database": '<ellipse cx="8" cy="3.8" rx="5" ry="2"/>'
                '<path d="M3 3.8v8.4c0 1.1 2.2 2 5 2s5-.9 5-2V3.8"/>'
                '<path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/>',
    "image": '<rect x="1.5" y="2.5" width="13" height="11" rx="2"/>'
             '<circle cx="5.4" cy="6" r="1.2"/>'
             '<path d="M2 12l3.8-3.3 2.8 2.3 2-1.6 3.4 2.9"/>',
    "globe": '<circle cx="8" cy="8" r="6.2"/>'
             '<ellipse cx="8" cy="8" rx="2.6" ry="6.2"/><path d="M1.8 8h12.4"/>',
    "tag": '<path d="M2 2h5.6L14 8.4 8.4 14 2 7.6z"/>'
           '<circle cx="5" cy="5" r="1.1"/>',
    "shield": '<path d="M8 1.6l5.2 2v4c0 3.3-2.2 5.6-5.2 6.8C5 13.2 2.8 '
              '10.9 2.8 7.6v-4z"/><path d="M5.6 8l1.7 1.7 3.2-3.4"/>',
    "flask": '<path d="M6 1.8h4M7 1.8v4.4L3.1 12.8a1.1 1.1 0 0 0 1 1.7h7.8'
             'a1.1 1.1 0 0 0 1-1.7L9 6.2V1.8M4.8 10h6.4"/>',
    "box": '<path d="M8 1.8l5.6 3v6.4L8 14.2l-5.6-3V4.8z"/>'
           '<path d="M2.4 4.8L8 7.8l5.6-3M8 7.8v6.4"/>',
    "upload": '<path d="M8 10.5V2.5M4.6 5.9L8 2.5l3.4 3.4M2.5 13.5h11"/>',
    "release": '<path d="M3 14V2.5M3 3h8.2l-1.7 2.8L11.2 8.6H3"/>',
    "hand": '<path d="M5 8.5V3.2a1.1 1.1 0 0 1 2.2 0v4.3M7.2 7V2.4a1.1 1.1 0 '
            '0 1 2.2 0V7M9.4 7V3.4a1.1 1.1 0 0 1 2.2 0V9c0 3-1.8 5-4.4 5-2.2 '
            '0-3.3-1.2-4.4-3.2L1.9 9.1a1 1 0 0 1 1.6-1.2L5 9.4"/>',
}

# Card and layout sizes, in px.
PAD = 20          # canvas padding
HEADER = 70       # column header height
CARD_INSET = 14   # card inset inside its column
CARD_H = 92
ROW_GAP = 36
CORNER = 8        # radius of a line's bends
HOP = 5           # radius of the hop where two lines cross


def text_width(text, size, bold=False):
    """A rough width for ``text`` in a common UI sans; on the wide side."""
    width = 0.0
    for ch in text:
        if ch in "il.,:;|'!`":
            width += 0.3
        elif ch in "frtjI -()[]/":
            width += 0.4
        elif ch in "mwMW":
            width += 0.86
        elif ch.isupper() or ch in "+=_<>%#@&":
            width += 0.68
        else:
            width += 0.57
    return width * size * (1.06 if bold else 1.0)


def num(value):
    """Format a coordinate without float noise."""
    value = round(value, 2)
    return str(int(value)) if value == int(value) else f"{value:g}"


@dataclass
class Card:
    key: str
    col: int
    row: float
    title: str
    sub: str
    pill: str
    icon: str
    group: str
    dashed: bool = False
    # Filled in by the layout.
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = CARD_H

    def right(self, dy=0):
        return (self.x + self.w, self.y + self.h / 2 + dy)

    def left(self, dy=0):
        return (self.x, self.y + self.h / 2 + dy)

    def top(self, dx=0):
        return (self.x + self.w / 2 + dx, self.y)

    def bottom(self, dx=0):
        return (self.x + self.w / 2 + dx, self.y + self.h)


@dataclass
class Edge:
    points: list
    label: str = ""
    label_at: tuple | None = None   # a point on the line
    dashed: bool = False
    both: bool = False              # arrowheads at both ends
    hops: list = field(default_factory=list)


@dataclass
class Diagram:
    name: str
    title: str
    desc: str
    columns: list           # (title, subtitle)
    cards: list
    col_w: float
    col_gap: float
    rows: int
    legend: bool = True
    edges: list = field(default_factory=list)

    def __post_init__(self):
        self.by_key = {}
        for card in self.cards:
            card.x = self.col_x(card.col) + CARD_INSET
            card.y = self.row_y(card.row)
            card.w = self.col_w - 2 * CARD_INSET
            self.by_key[card.key] = card

    def col_x(self, col):
        return PAD + col * (self.col_w + self.col_gap)

    def row_y(self, row):
        return PAD + HEADER + row * (CARD_H + ROW_GAP)

    def gap_x(self, col, frac=0.5):
        """An x in the gap right of column ``col`` (0 = its edge)."""
        return self.col_x(col) + self.col_w + self.col_gap * frac

    def __getitem__(self, key):
        return self.by_key[key]

    @property
    def panel_bottom(self):
        return self.row_y(self.rows) - ROW_GAP + 18

    @property
    def width(self):
        return 2 * PAD + len(self.columns) * self.col_w + \
            (len(self.columns) - 1) * self.col_gap

    @property
    def height(self):
        return self.panel_bottom + (58 if self.legend else PAD)


# ---------------------------------------------------------------- drawing


def segments(points):
    return list(zip(points, points[1:]))


def add_hops(edges):
    """Mark where a horizontal run of one line crosses a vertical run of
    another, so the later line can hop over it."""
    for i, edge in enumerate(edges):
        for (x1, y1), (x2, y2) in segments(edge.points):
            if y1 != y2:
                continue
            lo, hi = sorted((x1, x2))
            for j, other in enumerate(edges):
                if j == i:
                    continue
                for (ox1, oy1), (ox2, oy2) in segments(other.points):
                    if ox1 != ox2:
                        continue
                    olo, ohi = sorted((oy1, oy2))
                    if lo + 2 * HOP < ox1 < hi - 2 * HOP and \
                            olo < y1 < ohi:
                        edge.hops.append((ox1, y1))


def path_d(points, hops):
    """An SVG path through ``points`` with rounded bends and hops."""
    for (x1, y1), (x2, y2) in segments(points):
        if x1 != x2 and y1 != y2:
            raise ValueError(f"line is not straight: {(x1, y1)} -> {(x2, y2)}")
    d = [f"M{num(points[0][0])} {num(points[0][1])}"]
    last = len(points) - 1
    for i, (start, end) in enumerate(segments(points)):
        (x1, y1), (x2, y2) = start, end
        # Stop short of a bend to round it.
        r_out = CORNER if i + 1 < last else 0
        if y1 == y2:   # horizontal
            sign = 1 if x2 > x1 else -1
            crossing = sorted((hx for hx, hy in hops
                               if hy == y1 and min(x1, x2) < hx < max(x1, x2)),
                              reverse=sign < 0)
            for hx in crossing:
                d.append(f"L{num(hx - sign * HOP)} {num(y1)}")
                d.append(f"A{HOP} {HOP} 0 0 {1 if sign > 0 else 0} "
                         f"{num(hx + sign * HOP)} {num(y1)}")
            d.append(f"L{num(x2 - sign * r_out)} {num(y2)}")
        else:          # vertical
            sign = 1 if y2 > y1 else -1
            d.append(f"L{num(x2)} {num(y2 - sign * r_out)}")
        if r_out:
            nx, ny = points[i + 2]
            if y1 == y2:   # turning from horizontal to vertical
                vs = 1 if ny > y2 else -1
                d.append(f"Q{num(x2)} {num(y2)} {num(x2)} {num(y2 + vs * CORNER)}")
            else:          # turning from vertical to horizontal
                hs = 1 if nx > x2 else -1
                d.append(f"Q{num(x2)} {num(y2)} {num(x2 + hs * CORNER)} {num(y2)}")
    return " ".join(d)


def arrowhead(tip, before, color):
    """A small filled triangle at ``tip``, pointing away from ``before``."""
    (x, y), (bx, by) = tip, before
    size, half = 7, 4
    if bx == x:
        s = 1 if y > by else -1
        pts = [(x, y), (x - half, y - s * size), (x + half, y - s * size)]
    else:
        s = 1 if x > bx else -1
        pts = [(x, y), (x - s * size, y - half), (x - s * size, y + half)]
    return ('<path d="M' + " L".join(f"{num(px)} {num(py)}" for px, py in pts)
            + f' Z" fill="{color}"/>')


def pill(x, y, text, color, opacity, height=20, size=11):
    width = text_width(text, size, bold=True) + 16
    return (f'<rect x="{num(x)}" y="{num(y)}" width="{num(width)}" '
            f'height="{height}" rx="{height / 2:g}" fill="{color}" '
            f'fill-opacity="{opacity}"/>'
            f'<text x="{num(x + 8)}" y="{num(y + height / 2 + size * 0.36)}" '
            f'font-size="{size}" font-weight="600" fill="{color}">'
            f'{escape(text)}</text>'), width


def render(diagram, theme_name):
    theme = THEMES[theme_name]
    groups = theme["groups"]
    out = []
    w, h = diagram.width, diagram.height
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(w)} {num(h)}" '
        f'width="{num(w)}" height="{num(h)}" role="img" '
        f'aria-labelledby="title desc" font-family="{FONT}">')
    out.append(f'<title id="title">{escape(diagram.title)}</title>')
    out.append(f'<desc id="desc">{escape(diagram.desc)}</desc>')

    # Hatching, one pattern per colour in use.
    out.append("<defs>")
    for name in sorted({c.group for c in diagram.cards}):
        out.append(
            f'<pattern id="hatch-{name}" width="7" height="7" '
            f'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<line x1="0" y1="0" x2="0" y2="7" stroke="{groups[name]}" '
            f'stroke-width="1.4" stroke-opacity="{theme["hatch_opacity"]}"/>'
            f'</pattern>')
    out.append("</defs>")

    out.append(f'<rect x="0.5" y="0.5" width="{num(w - 1)}" height="{num(h - 1)}" '
               f'rx="16" fill="{theme["canvas"]}" stroke="{theme["canvas_line"]}"/>')

    # Columns.
    for i, (title, subtitle) in enumerate(diagram.columns):
        x = diagram.col_x(i)
        y = PAD
        out.append(f'<rect x="{num(x)}" y="{num(y)}" width="{num(diagram.col_w)}" '
                   f'height="{num(diagram.panel_bottom - y)}" rx="14" '
                   f'fill="{theme["panel"]}" stroke="{theme["panel_line"]}"/>')
        out.append(f'<circle cx="{num(x + 26)}" cy="{num(y + 28)}" r="11" '
                   f'fill="{theme["badge"]}"/>')
        out.append(f'<text x="{num(x + 26)}" y="{num(y + 32)}" font-size="12" '
                   f'font-weight="700" text-anchor="middle" '
                   f'fill="{theme["badge_text"]}">{i + 1}</text>')
        check_fits(title, 15, True, diagram.col_w - 56)
        check_fits(subtitle, 12, False, diagram.col_w - 32)
        out.append(f'<text x="{num(x + 45)}" y="{num(y + 33)}" font-size="15" '
                   f'font-weight="700" fill="{theme["text"]}">'
                   f'{escape(title)}</text>')
        out.append(f'<text x="{num(x + 16)}" y="{num(y + 56)}" font-size="12" '
                   f'fill="{theme["muted"]}">{escape(subtitle)}</text>')

    # Cards.
    for card in diagram.cards:
        color = groups[card.group]
        dash = ' stroke-dasharray="5 4"' if card.dashed else ""
        out.append('<g>')
        out.append(f'<rect x="{num(card.x)}" y="{num(card.y)}" width="{num(card.w)}" '
                   f'height="{num(card.h)}" rx="12" fill="{theme["card"]}"/>')
        if not card.dashed:
            out.append(f'<rect x="{num(card.x)}" y="{num(card.y)}" '
                       f'width="{num(card.w)}" height="{num(card.h)}" rx="12" '
                       f'fill="url(#hatch-{card.group})"/>')
        out.append(f'<rect x="{num(card.x + 0.75)}" y="{num(card.y + 0.75)}" '
                   f'width="{num(card.w - 1.5)}" height="{num(card.h - 1.5)}" '
                   f'rx="11.5" fill="none" stroke="{color}" stroke-width="1.5" '
                   f'stroke-opacity="{theme["card_line_opacity"]}"{dash}/>')
        tag, _width = pill(card.x + 14, card.y + 14, card.pill, color,
                          theme["pill_opacity"])
        check_fits(card.pill, 11, True, card.w - 28 - 24, extra=16)
        out.append(tag)
        out.append(f'<g transform="translate({num(card.x + card.w - 30)} '
                   f'{num(card.y + 16)})" fill="none" stroke="{color}" '
                   f'stroke-width="1.5" stroke-linecap="round" '
                   f'stroke-linejoin="round">{ICONS[card.icon]}</g>')
        check_fits(card.title, 15, True, card.w - 28)
        check_fits(card.sub, 12, False, card.w - 28)
        out.append(f'<text x="{num(card.x + 14)}" y="{num(card.y + 58)}" '
                   f'font-size="15" font-weight="700" fill="{theme["text"]}">'
                   f'{escape(card.title)}</text>')
        out.append(f'<text x="{num(card.x + 14)}" y="{num(card.y + 78)}" '
                   f'font-size="12" fill="{theme["subtext"]}">'
                   f'{escape(card.sub)}</text>')
        out.append("</g>")

    # Lines, then their arrowheads and labels on top.
    edges = diagram.edges
    for edge in edges:
        edge.hops = []
    add_hops(edges)
    for edge in edges:
        dash = ' stroke-dasharray="6 5"' if edge.dashed else ""
        out.append(f'<path d="{path_d(edge.points, edge.hops)}" fill="none" '
                   f'stroke="{theme["edge"]}" stroke-width="1.5" '
                   f'stroke-linecap="round" stroke-linejoin="round"{dash}/>')
        out.append(arrowhead(edge.points[-1], edge.points[-2], theme["edge"]))
        if edge.both:
            out.append(arrowhead(edge.points[0], edge.points[1], theme["edge"]))
    for edge in edges:
        if not edge.label:
            continue
        lx, ly = edge.label_at
        width = text_width(edge.label, 11) + 16
        out.append(f'<rect x="{num(lx - width / 2)}" y="{num(ly - 10)}" '
                   f'width="{num(width)}" height="20" rx="10" '
                   f'fill="{theme["label"]}" stroke="{theme["label_line"]}"/>')
        out.append(f'<text x="{num(lx)}" y="{num(ly + 4)}" font-size="11" '
                   f'text-anchor="middle" fill="{theme["label_text"]}">'
                   f'{escape(edge.label)}</text>')

    if diagram.legend:
        out.append(legend(diagram, theme))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def legend(diagram, theme):
    """Line styles, under the columns."""
    y = diagram.panel_bottom + 30
    x = PAD + 6
    parts = []
    samples = [("calls or data", False, False), ("optional or by hand", True, False),
               ("both ways", False, True)]
    for label, dashed, both in samples:
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        parts.append(f'<path d="M{num(x)} {num(y)} L{num(x + 34)} {num(y)}" '
                     f'stroke="{theme["edge"]}" stroke-width="1.5"{dash}/>')
        parts.append(arrowhead((x + 36, y), (x, y), theme["edge"]))
        if both:
            parts.append(arrowhead((x - 2, y), (x + 34, y), theme["edge"]))
        parts.append(f'<text x="{num(x + 46)}" y="{num(y + 4)}" font-size="12" '
                     f'fill="{theme["muted"]}">{escape(label)}</text>')
        x += 46 + text_width(label, 12) + 34
    hop_x = x + 6
    parts.append(f'<path d="M{num(hop_x)} {num(y)} L{num(hop_x + 12)} {num(y)} '
                 f'A{HOP} {HOP} 0 0 1 {num(hop_x + 22)} {num(y)} '
                 f'L{num(hop_x + 34)} {num(y)}" fill="none" '
                 f'stroke="{theme["edge"]}" stroke-width="1.5"/>')
    parts.append(f'<path d="M{num(hop_x + 17)} {num(y - 10)} '
                 f'L{num(hop_x + 17)} {num(y + 10)}" stroke="{theme["edge"]}" '
                 f'stroke-width="1.5"/>')
    parts.append(f'<text x="{num(hop_x + 46)}" y="{num(y + 4)}" font-size="12" '
                 f'fill="{theme["muted"]}">lines cross, they do not join</text>')
    return "\n".join(parts)


def check_fits(text, size, bold, room, extra=0):
    need = text_width(text, size, bold) + extra
    if need > room:
        raise ValueError(f"{text!r} needs about {need:.0f} px, has {room:.0f}")


# ---------------------------------------------------------------- diagrams


def architecture():
    cards = [
        Card("app", 0, 0, "Any app", "copies, gets the paste",
             "Wayland client", "app", "blue"),
        Card("you", 0, 1, "You", "press Super+V", "keyboard", "person", "blue"),
        Card("shortcut", 0, 2, "GNOME shortcut", "runs clipman toggle",
             "gsettings", "keyboard", "blue"),
        Card("clipboard", 1, 0, "Wayland clipboard", "Meta.Selection (Mutter)",
             "compositor", "clipboard", "amber"),
        Card("extension", 1, 1, "Clipman extension", "sees copies, types pastes",
             "gjs · v9", "puzzle", "amber"),
        Card("monitor", 2, 0, "Clipboard monitor", "dedupe, secret check",
             "Python", "eye", "violet"),
        Card("dbus", 2, 1, "D-Bus service", "com.clipman.Daemon",
             "session bus", "bus", "violet"),
        Card("popup", 2, 2, "Popup window", "history and snippets",
             "GTK 4 + Adw", "window", "violet"),
        Card("updates", 2, 3, "Update check", "once a day, in a thread",
             "opt-in", "refresh", "violet", dashed=True),
        Card("images", 3, 0, "images/", "PNG files named by hash",
             "files · 0600", "image", "green"),
        Card("db", 3, 1, "clipman.db", "clips, snippets, settings",
             "SQLite · WAL", "database", "green"),
        Card("github", 3, 3, "GitHub Releases API", "the latest release",
             "HTTPS · opt-in", "globe", "gray", dashed=True),
    ]
    d = Diagram(
        name="architecture",
        title="Clipman architecture",
        desc=("Capture: an app copies to the Wayland clipboard. The Clipman "
              "GNOME Shell extension sees the owner-changed signal and sends "
              "the text to the daemon's D-Bus service with NewEntry; images "
              "are read with wl-paste. The clipboard monitor drops duplicates "
              "by SHA-256 hash, checks for secrets, and stores the clip in "
              "clipman.db (SQLite, WAL) and images/. Paste: Super+V runs "
              "clipman toggle, which calls Toggle on the D-Bus service to "
              "show the popup. The popup reads the history, puts the chosen "
              "clip on the clipboard with wl-copy, and asks the extension to "
              "give focus back and type the paste keys into the app. The "
              "daemon runs as a systemd user service; its only network call "
              "is an opt-in daily update check to the GitHub Releases API."),
        columns=[("Your session", "apps, keys and shortcuts"),
                 ("GNOME Shell", "Mutter and the extension"),
                 ("Clipman daemon", "Python · systemd user service"),
                 ("Disk and network", "local files, one opt-in call")],
        cards=cards, col_w=224, col_gap=76, rows=4,
    )
    app, you, shortcut = d["app"], d["you"], d["shortcut"]
    clip, ext = d["clipboard"], d["extension"]
    mon, bus, pop, upd = d["monitor"], d["dbus"], d["popup"], d["updates"]
    img, db, gh = d["images"], d["db"], d["github"]
    g0a, g0b = d.gap_x(0, 0.35), d.gap_x(0, 0.65)
    g1 = d.gap_x(1, 0.5)
    g2 = d.gap_x(2, 0.5)

    def mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    p = {}
    p["copy"] = [app.right(-14), clip.left(-14)]
    p["owner"] = [clip.bottom(), ext.top()]
    p["image"] = [clip.right(-14), mon.left(-14)]
    p["bus"] = [ext.right(-14), bus.left(-14)]
    p["new"] = [bus.top(), mon.bottom()]
    p["toggle"] = [bus.bottom(), pop.top()]
    p["png"] = [mon.right(-14), img.left(-14)]
    p["store"] = [mon.right(16), (g2, mon.right(16)[1]),
                  (g2, db.left(-14)[1]), db.left(-14)]
    p["read"] = [pop.right(), (g2 + 12, pop.right()[1]),
                 (g2 + 12, db.left(16)[1]), db.left(16)]
    p["keys"] = [you.bottom(), shortcut.top()]
    p["run"] = [shortcut.right(-16), (g1, shortcut.right(-16)[1]),
                (g1, bus.left(18)[1]), bus.left(18)]
    # Into the clipboard from below, between it and the extension, so it
    # does not run alongside the paste line into the app.
    below_clip = (clip.y + clip.h + ext.y) / 2
    p["wlcopy"] = [pop.left(16), (g0a, pop.left(16)[1]), (g0a, below_clip),
                   (clip.bottom(-70)[0], below_clip), clip.bottom(-70)]
    p["paste"] = [ext.left(), (g0b, ext.left()[1]),
                  (g0b, app.right(16)[1]), app.right(16)]
    p["check"] = [upd.right(), gh.left()]
    d.edges = [
        Edge(p["copy"], "copies", mid(*p["copy"])),
        Edge(p["owner"], "owner-changed", mid(*p["owner"])),
        Edge(p["image"], "wl-paste", mid(*p["image"])),
        Edge(p["bus"], "D-Bus", mid(*p["bus"]), both=True),
        Edge(p["new"], "NewEntry", mid(*p["new"])),
        Edge(p["toggle"], "Toggle", mid(*p["toggle"])),
        Edge(p["png"], "image", mid(*p["png"])),
        Edge(p["store"], "SHA-256", mid(p["store"][1], p["store"][2])),
        Edge(p["read"], "history", (g2 + 12, (pop.right()[1] + db.left(16)[1]) / 2),
             both=True),
        Edge(p["keys"], "Super+V", mid(*p["keys"])),
        Edge(p["run"], "clipman toggle",
             ((shortcut.right()[0] + ext.x + ext.w) / 2 + 30,
              shortcut.right(-16)[1])),
        Edge(p["wlcopy"], "wl-copy", (g0a, (below_clip + pop.left(16)[1]) / 2)),
        Edge(p["paste"], "paste keys", (g0b, (below_clip + ext.left()[1]) / 2 + 4)),
        Edge(p["check"], "HTTPS GET", mid(*p["check"]), dashed=True),
    ]
    return d


def release():
    cards = [
        Card("tag", 0, 0, "Tag v1.2.3", "made through the API",
             "trigger", "tag", "blue"),
        Card("preflight", 0, 1, "pre-flight", "versions and release notes",
             "gate", "shield", "amber"),
        Card("tests", 0, 2, "tests", "Python 3.10 to 3.14",
             "gate", "flask", "amber"),
        Card("pypi", 1, 0, "build-pypi", "wheel + sdist, smoke test",
             "build", "box", "teal"),
        Card("snap", 1, 1, "build-snap", "core24 + gnome extension",
             "build", "box", "teal"),
        Card("ext", 1, 2, "bundle-extension", "the extension zip",
             "build", "box", "teal"),
        Card("pkgs", 1, 3, "build-distpkgs", ".deb and .rpm (fpm)",
             "build", "box", "teal"),
        Card("ppypi", 2, 0, "publish-pypi", "OIDC trusted publishing",
             "publish", "upload", "violet"),
        Card("psnap", 2, 1, "publish-snap", "stable, candidate, beta",
             "publish", "upload", "violet"),
        Card("ghr", 3, 0, "github-release", "files + CHANGELOG notes",
             "release", "release", "green"),
        Card("aur", 3, 1, "publish-aur", "PKGBUILD and .SRCINFO",
             "publish", "upload", "violet"),
        Card("ego", 3, 2, "extensions.gnome.org", "upload the zip",
             "by hand", "hand", "gray", dashed=True),
    ]
    d = Diagram(
        name="release-pipeline",
        title="Clipman release pipeline",
        desc=("A version tag starts release.yml. pre-flight checks that every "
              "version carrier matches the tag and that CHANGELOG.md has notes "
              "for it; tests run on Python 3.10 to 3.14. Then four builds run "
              "side by side: build-pypi (wheel and sdist, smoke-tested), "
              "build-snap, bundle-extension and build-distpkgs (.deb and "
              ".rpm). publish-pypi uploads with OIDC trusted publishing and "
              "publish-snap releases to stable, candidate and beta. Once both "
              "succeed, github-release attaches every file with the CHANGELOG "
              "notes, and publish-aur pushes the PKGBUILD. The extension zip is "
              "uploaded to extensions.gnome.org by hand."),
        columns=[("Start", "a tag, then the checks"),
                 ("Build", "side by side, after the tests"),
                 ("Publish", "to PyPI and the Snap Store"),
                 ("Release", "after every publish")],
        cards=cards, col_w=224, col_gap=76, rows=4,
    )
    tag, pre, tests = d["tag"], d["preflight"], d["tests"]
    pypi, snap, ext, pkgs = d["pypi"], d["snap"], d["ext"], d["pkgs"]
    ppypi, psnap = d["ppypi"], d["psnap"]
    ghr, aur, ego = d["ghr"], d["aur"], d["ego"]
    g0 = d.gap_x(0, 0.5)
    g2 = d.gap_x(2, 0.5)

    def mid(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    fan_out = [[tests.right(), (g0, tests.right()[1]), (g0, b.left()[1]), b.left()]
               for b in (pypi, snap, pkgs)]
    fan_in = [[src.right(), (g2, src.right()[1]), (g2, ghr.left(16)[1]),
               ghr.left(16)] for src in (psnap, ext, pkgs)]
    d.edges = [
        Edge([tag.bottom(), pre.top()], "starts", mid(tag.bottom(), pre.top())),
        Edge([pre.bottom(), tests.top()], "passes", mid(pre.bottom(), tests.top())),
        Edge([tests.right(), ext.left()], "all pass", mid(tests.right(), ext.left())),
        *[Edge(points) for points in fan_out],
        Edge([pypi.right(), ppypi.left()], "wheel", mid(pypi.right(), ppypi.left())),
        Edge([snap.right(), psnap.left()], ".snap", mid(snap.right(), psnap.left())),
        Edge([ppypi.right(-14), ghr.left(-14)], "then", mid(ppypi.right(-14),
                                                            ghr.left(-14))),
        *[Edge(points) for points in fan_in],
        Edge([ghr.bottom(), aur.top()], "then", mid(ghr.bottom(), aur.top())),
        # The zip is built by bundle-extension and attached to the release;
        # the upload to extensions.gnome.org is done by hand.
        Edge([ext.right(18), ego.left(18)], "the zip, by hand",
             (d.col_x(2) + d.col_w / 2, ext.right(18)[1]), dashed=True),
    ]
    return d


DIAGRAMS = [architecture, release]


def outputs():
    """Every file this script writes, mapped to its content."""
    files = {}
    for make in DIAGRAMS:
        for theme in THEMES:
            diagram = make()
            files[OUT / f"{diagram.name}-{theme}.svg"] = render(diagram, theme)
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Draw the docs diagrams.")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when a file is out of date; change nothing")
    args = parser.parse_args(argv)
    stale = []
    for path, content in outputs().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        stale.append(path.relative_to(ROOT))
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if args.check and stale:
        print("Out of date (run scripts/diagrams.py): "
              + ", ".join(str(p) for p in stale), file=sys.stderr)
        return 1
    print(f"{'checked' if args.check else 'wrote'} {len(outputs())} files"
          + (f", {len(stale)} changed" if stale and not args.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
