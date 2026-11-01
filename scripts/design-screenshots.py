#!/usr/bin/env python3
"""Remake the website's screenshots of the design pages.

docs/index.html shows each screenshot in a dark and a light version.
Each one is a capture of a page in docs/design/ at twice its CSS size,
with the theme picked by ``?theme=``. Before it saves a capture, the
script checks that the page's theme toggle marks the theme it asked
for. (The light screenshots from June 2026 showed "Dark" selected.)

Playwright is not part of the dev extras. To set it up once:

    python3 -m venv ~/.cache/clipman-pw
    ~/.cache/clipman-pw/bin/pip install playwright
    ~/.cache/clipman-pw/bin/playwright install chromium

Then, from the repository root:

    ~/.cache/clipman-pw/bin/python scripts/design-screenshots.py

``--only NAME`` remakes one screenshot, and ``--chromium PATH`` uses a
Chromium that is already on disk. Look at every image before you commit
it. tests/test_design_screenshots.py checks that the files in
docs/design/screenshots/ are the ones this script makes, at the right
size, and that the website uses all of them.
"""
import argparse
import functools
import http.server
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "design" / "screenshots"
THEMES = ("dark", "light")
SCALE = 2

# Name: (page under docs/, CSS width, CSS height, element to centre on).
# A shot with no element is the whole viewport. A shot with one is cut
# from a wider page, centred on that element: main-window.html switches
# to its phone layout at 640 px and below.
SHOTS = {
    "main-window": ("design/main-window.html", 540, 760, ".window"),
    "preferences-appearance": ("design/preferences.html?pane=appearance", 950, 720, None),
    "preferences-privacy": ("design/preferences.html?pane=privacy", 950, 720, None),
    "preferences-storage": ("design/preferences.html?pane=storage", 950, 720, None),
    "snippets-editing": ("design/snippets.html", 950, 680, None),
    "states-incognito-on": ("design/states.html?state=incognito-on", 900, 800, None),
}
WIDE_VIEWPORT = 960


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        """Keep the request log out of the script's output."""


def outputs():
    """Map each screenshot path to its (page, width, height, element, theme)."""
    return {
        OUT / f"{name}-{theme}.png": (page, width, height, element, theme)
        for name, (page, width, height, element) in SHOTS.items()
        for theme in THEMES
    }


def page_url(base, page, theme):
    separator = "&" if "?" in page else "?"
    return f"{base}/{page}{separator}theme={theme}"


def capture(browser, url, width, height, element, theme, path):
    """Save one screenshot. Return a problem as text, or None."""
    viewport = {"width": WIDE_VIEWPORT if element else width, "height": height}
    # A new context starts with empty storage, so only ?theme= decides.
    context = browser.new_context(
        viewport=viewport,
        device_scale_factor=SCALE,
        color_scheme=theme,
    )
    try:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="networkidle")
        page.evaluate("() => document.fonts.ready.then(() => true)")
        marked = page.eval_on_selector(
            ".theme-toggle button.active",
            "button => button.textContent.trim().toLowerCase()",
        )
        classes = page.eval_on_selector("body", "body => body.className").split()
        if errors:
            return f"script errors on the page: {errors}"
        if marked != theme or f"theme-{theme}" not in classes:
            return (f"the page shows theme {classes} with {marked!r} marked "
                    f"in its toggle, not {theme!r}")
        clip = None
        if element:
            box = page.locator(element).bounding_box()
            clip = {"x": box["x"] + box["width"] / 2 - width / 2, "y": 0,
                    "width": width, "height": height}
            if (box["x"] < clip["x"] or box["y"] < 0
                    or box["x"] + box["width"] > clip["x"] + width
                    or box["y"] + box["height"] > height):
                return f"{element} ({box}) does not fit in {width}x{height}"
        page.screenshot(path=str(path), clip=clip)
        return None
    finally:
        context.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Remake the website's screenshots of the design pages.")
    parser.add_argument("--only", action="append", choices=sorted(SHOTS),
                        metavar="NAME", help="remake only this screenshot")
    parser.add_argument("--chromium", metavar="PATH",
                        help="use this Chromium instead of Playwright's")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("This script needs Playwright; see the setup steps at the "
              "top of scripts/design-screenshots.py.", file=sys.stderr)
        return 2

    # Serve docs/ over HTTP, as GitHub Pages does, so the pages behave as
    # they do on the website.
    handler = functools.partial(_QuietHandler, directory=str(DOCS))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    failed = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium)
            for path, (page, width, height, element, theme) in outputs().items():
                if args.only and path.stem.rsplit("-", 1)[0] not in args.only:
                    continue
                url = page_url(base, page, theme)
                problem = capture(browser, url, width, height, element, theme,
                                  path)
                if problem:
                    failed = True
                    print(f"FAILED {path.name}: {problem}", file=sys.stderr)
                else:
                    print(path.relative_to(ROOT))
            browser.close()
    finally:
        server.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
