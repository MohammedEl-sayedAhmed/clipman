#!/usr/bin/env python3
"""Refresh self-hosted GitHub stats: star-history SVGs + downloads history.

Run daily by .github/workflows/refresh-numbers.yml (and locally for
seeding). Produces:

- ``docs/assets/star-history-dark.svg`` / ``star-history-light.svg`` —
  a cumulative star chart generated from the stargazer timestamps.
  Self-hosted because the star-history.com SVG endpoint rate-limits
  behind GitHub's image proxy and then the README shows "no data".
- ``docs/_data/stats_history.json`` — append-only daily series of
  ``{date, stars, gh_downloads}`` so release-download growth (which
  GitHub only exposes as a live total) accrues a history we own.

Deterministic on unchanged inputs: same stars + same downloads produce
byte-identical files, so the bot's "no diff → no PR" invariant holds.

Auth: uses ``GH_TOKEN`` / ``GITHUB_TOKEN`` when set (the runner's token);
anonymous works locally within rate limits.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.request

REPO = "MohammedEl-sayedAhmed/clipman"
HISTORY_PATH = "docs/_data/stats_history.json"
SVG_DARK = "docs/assets/star-history-dark.svg"
SVG_LIGHT = "docs/assets/star-history-light.svg"
UA = f"clipman-stats/1.0 (+https://github.com/{REPO})"

THEMES = {
    SVG_DARK: {
        "id": "d", "text": "#cdd6f4", "muted": "#a6adc8",
        "grid": "#45475a", "line": "#cba6f7", "fill": "#cba6f7",
    },
    SVG_LIGHT: {
        "id": "l", "text": "#1c1917", "muted": "#57534e",
        "grid": "#d6d3d1", "line": "#2563eb", "fill": "#2563eb",
    },
}


def _get_json(url, accept="application/json"):
    headers = {"User-Agent": UA, "Accept": accept}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, ValueError) as e:
        print(f"WARN: fetch {url} failed: {e}", file=sys.stderr)
        return None


def fetch_star_dates():
    """All stargazer timestamps (ISO dates), oldest first; None on failure."""
    dates, page = [], 1
    while True:
        batch = _get_json(
            f"https://api.github.com/repos/{REPO}/stargazers"
            f"?per_page=100&page={page}",
            accept="application/vnd.github.star+json",
        )
        if batch is None:
            return None
        for item in batch:
            ts = item.get("starred_at")
            if ts:
                dates.append(ts[:10])
        if len(batch) < 100:
            return sorted(dates)
        page += 1


def fetch_release_downloads():
    """(total, {tag: downloads}) across all releases; None on failure."""
    rels = _get_json(
        f"https://api.github.com/repos/{REPO}/releases?per_page=100"
    )
    if rels is None:
        return None
    per_tag = {
        r["tag_name"]: sum(a.get("download_count", 0)
                           for a in r.get("assets", []))
        for r in rels
    }
    return sum(per_tag.values()), per_tag


def _smooth_path(pts):
    """A Catmull-Rom spline through pts as an SVG path `d` (cubic Béziers).

    Matches the star-history.com look: a gently curved rising line rather
    than a hard step function. Endpoints are clamped so the curve starts
    and ends exactly on the data.
    """
    if len(pts) == 1:
        px, py = pts[0]
        return f"M{px:.1f},{py:.1f}"
    d = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[0]
        p1 = pts[i]
        p2 = pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else pts[n - 1]
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        # Time is strictly increasing, so keep each segment's control points
        # within [p1.x, p2.x] — prevents the horizontal overshoot that would
        # otherwise backtrack past the axis and wobble the line.
        lo, hi = p1[0], p2[0]
        c1x = min(max(c1x, lo), hi)
        c2x = min(max(c2x, lo), hi)
        d.append(
            f"C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} "
            f"{p2[0]:.1f},{p2[1]:.1f}"
        )
    return " ".join(d)


def build_star_svg(dates, theme):
    """Cumulative star-history chart as a standalone SVG string."""
    w, h, pad_l, pad_r, pad_t, pad_b = 800, 360, 64, 28, 46, 46
    if not dates:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
            f'<text x="{w / 2}" y="{h / 2}" text-anchor="middle" '
            f'fill="{theme["text"]}" font-family="sans-serif" '
            f'font-size="16">No stars yet — be the first ★</text></svg>'
        )
    d0 = datetime.date.fromisoformat(dates[0])
    d1 = datetime.date.fromisoformat(dates[-1])
    span = max((d1 - d0).days, 1)
    total = len(dates)
    y_max = max(total, 4)
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b

    def x(d):
        return pad_l + plot_w * (datetime.date.fromisoformat(d) - d0).days / span

    def y(n):
        return pad_t + plot_h * (1 - n / y_max)

    # One vertex per star (cumulative), preceded by the (start, 0) origin —
    # the smoother curves through these to mirror star-history.com.
    verts = [(x(dates[0]), y(0))]
    for i, d in enumerate(dates, start=1):
        verts.append((x(d), y(i)))
    curve = _smooth_path(verts)
    base = y(0)
    area = (f"{curve} L{verts[-1][0]:.1f},{base:.1f} "
            f"L{verts[0][0]:.1f},{base:.1f} Z")

    grid_lines, labels = [], []
    for i in range(5):
        n = round(y_max * i / 4)
        gy = y(n)
        grid_lines.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" '
            f'y2="{gy:.1f}" stroke="{theme["grid"]}" stroke-width="1" '
            f'stroke-dasharray="3,4"/>'
        )
        labels.append(
            f'<text x="{pad_l - 10}" y="{gy + 4:.1f}" text-anchor="end" '
            f'fill="{theme["muted"]}" font-size="12" '
            f'font-family="sans-serif">{n}</text>'
        )
    labels.append(
        f'<text x="{pad_l}" y="{h - 16}" fill="{theme["muted"]}" '
        f'font-size="12" font-family="sans-serif">{d0.isoformat()}</text>'
    )
    labels.append(
        f'<text x="{w - pad_r}" y="{h - 16}" text-anchor="end" '
        f'fill="{theme["muted"]}" font-size="12" '
        f'font-family="sans-serif">{d1.isoformat()}</text>'
    )
    # Rotated y-axis title, like star-history's "GitHub Stars".
    cy = pad_t + plot_h / 2
    labels.append(
        f'<text x="16" y="{cy:.1f}" fill="{theme["muted"]}" font-size="12" '
        f'font-family="sans-serif" text-anchor="middle" '
        f'transform="rotate(-90 16 {cy:.1f})">GitHub Stars</text>'
    )
    # Endpoint marker.
    lx, ly = verts[-1]
    marker = (
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" '
        f'fill="{theme["line"]}"/>'
    )
    # Legend chip: colour swatch + repo name (star-history top-left legend).
    gid = f'sh-grad-{theme["id"]}'
    legend = (
        f'<line x1="{pad_l}" y1="24" x2="{pad_l + 22}" y2="24" '
        f'stroke="{theme["line"]}" stroke-width="2.5" '
        f'stroke-linecap="round"/>'
        f'<circle cx="{pad_l + 11}" cy="24" r="3.5" fill="{theme["line"]}"/>'
        f'<text x="{pad_l + 30}" y="28" fill="{theme["text"]}" '
        f'font-size="13" font-weight="600" '
        f'font-family="sans-serif">{REPO}</text>'
        f'<text x="{w - pad_r}" y="28" text-anchor="end" '
        f'fill="{theme["line"]}" font-size="14" font-weight="700" '
        f'font-family="sans-serif">★ {total}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="sans-serif">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{theme["fill"]}" stop-opacity="0.28"/>'
        f'<stop offset="1" stop-color="{theme["fill"]}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        + "".join(grid_lines)
        + f'<path d="{area}" fill="url(#{gid})"/>'
        + f'<path d="{curve}" fill="none" stroke="{theme["line"]}" '
          f'stroke-width="2.5" stroke-linejoin="round" '
          f'stroke-linecap="round"/>'
        + marker
        + legend
        + "".join(labels)
        + "</svg>\n"
    )


def update_history(stars, downloads_total, per_tag):
    """Append today's point only when a value moved (no-churn invariant)."""
    try:
        with open(HISTORY_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {
            "_comment": ("Daily series appended by scripts/refresh_stats.py "
                         "(refresh-numbers workflow). A point is added only "
                         "when a value changes."),
            "series": [],
        }
    series = data.setdefault("series", [])
    last = series[-1] if series else {}
    if (last.get("stars") != stars
            or last.get("gh_downloads") != downloads_total):
        series.append({
            "date": datetime.date.today().isoformat(),
            "stars": stars,
            "gh_downloads": downloads_total,
            "per_tag": per_tag,
        })
        with open(HISTORY_PATH, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        return True
    return False


def main():
    os.makedirs(os.path.dirname(SVG_DARK), exist_ok=True)
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)

    dates = fetch_star_dates()
    if dates is not None:
        for path, theme in THEMES.items():
            with open(path, "w") as f:
                f.write(build_star_svg(dates, theme))
        print(f"star SVGs written ({len(dates)} stars)")
    else:
        print("WARN: stargazers fetch failed; SVGs left as-is",
              file=sys.stderr)

    rel = fetch_release_downloads()
    if rel is not None and dates is not None:
        total, per_tag = rel
        changed = update_history(len(dates), total, per_tag)
        print(f"downloads total={total} history_changed={changed}")
    else:
        print("WARN: releases fetch failed; history left as-is",
              file=sys.stderr)


if __name__ == "__main__":
    main()
