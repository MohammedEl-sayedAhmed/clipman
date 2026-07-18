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
        "text": "#cdd6f4", "grid": "#45475a",
        "line": "#cba6f7", "fill": "rgba(203,166,247,0.18)",
    },
    SVG_LIGHT: {
        "text": "#1c1917", "grid": "#d6d3d1",
        "line": "#2563eb", "fill": "rgba(37,99,235,0.14)",
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


def build_star_svg(dates, theme):
    """Cumulative star-history chart as a standalone SVG string."""
    w, h, pad_l, pad_r, pad_t, pad_b = 800, 340, 56, 24, 28, 44
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
    y_max = max(total, 5)
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b

    def x(d):
        return pad_l + plot_w * (datetime.date.fromisoformat(d) - d0).days / span

    def y(n):
        return pad_t + plot_h * (1 - n / y_max)

    # Step-after cumulative points.
    pts = []
    count = 0
    for d in dates:
        pts.append((x(d), y(count)))   # step
        count += 1
        pts.append((x(d), y(count)))   # rise
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = (f"{pad_l:.1f},{y(0):.1f} " + line
            + f" {pts[-1][0]:.1f},{y(0):.1f}")

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
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" '
            f'fill="{theme["text"]}" font-size="12" '
            f'font-family="sans-serif">{n}</text>'
        )
    labels.append(
        f'<text x="{pad_l}" y="{h - 14}" fill="{theme["text"]}" '
        f'font-size="12" font-family="sans-serif">{d0.isoformat()}</text>'
    )
    labels.append(
        f'<text x="{w - pad_r}" y="{h - 14}" text-anchor="end" '
        f'fill="{theme["text"]}" font-size="12" '
        f'font-family="sans-serif">{d1.isoformat()}</text>'
    )
    lx, ly = pts[-1]
    labels.append(
        f'<text x="{min(lx, w - pad_r - 4):.1f}" y="{max(ly - 8, 16):.1f}" '
        f'text-anchor="end" fill="{theme["line"]}" font-size="14" '
        f'font-weight="bold" font-family="sans-serif">★ {total}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">'
        f'<text x="{pad_l}" y="18" fill="{theme["text"]}" font-size="13" '
        f'font-family="sans-serif" font-weight="bold">GitHub stars over time'
        f'</text>'
        + "".join(grid_lines)
        + f'<polygon points="{area}" fill="{theme["fill"]}"/>'
        + f'<polyline points="{line}" fill="none" stroke="{theme["line"]}" '
          f'stroke-width="2.5" stroke-linejoin="round"/>'
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
