#!/usr/bin/env bash
# Regenerate docs/architecture.png from docs/architecture.svg.
#
# Why we keep both: the SVG is authoritative and renders crisply on
# GitHub-flavored markdown (the README and ARCHITECTURE.md embed it
# directly). The PNG companion exists for downstream consumers that
# do not handle SVG well — the dev.to mirror of the writeup at
# https://dev.to/mammar in particular — and for any future RSS reader
# or social-card surface that wants a raster image.
#
# Run this whenever docs/architecture.svg changes. The CI verify
# workflow at .github/workflows/verify-architecture-png.yml will fail
# the PR if you forget.
#
# Requires either rsvg-convert (from librsvg2-bin) or a Python venv
# with cairosvg. We try rsvg-convert first because it's the canonical
# tool; cairosvg is the portable fallback for machines without sudo.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SVG="$ROOT/docs/architecture.svg"
PNG="$ROOT/docs/architecture.png"
WIDTH=1600

if [[ ! -f "$SVG" ]]; then
    echo "error: source SVG missing at $SVG" >&2
    exit 1
fi

if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w "$WIDTH" -o "$PNG" "$SVG"
    echo "rendered $SVG -> $PNG (rsvg-convert, ${WIDTH}px wide)"
elif command -v python3 >/dev/null 2>&1; then
    venv="${XDG_CACHE_HOME:-$HOME/.cache}/clipman-render-venv"
    if [[ ! -x "$venv/bin/python" ]]; then
        echo "setting up one-shot venv at $venv (cairosvg fallback)..."
        python3 -m venv "$venv"
        "$venv/bin/pip" install --quiet cairosvg
    fi
    "$venv/bin/python" - "$SVG" "$PNG" "$WIDTH" <<'PY'
import sys
import cairosvg
cairosvg.svg2png(url=sys.argv[1], write_to=sys.argv[2], output_width=int(sys.argv[3]))
PY
    echo "rendered $SVG -> $PNG (cairosvg, ${WIDTH}px wide)"
else
    cat >&2 <<'EOF'
error: need rsvg-convert (from librsvg2-bin) or python3 with venv support.
       on Debian/Ubuntu: sudo apt install librsvg2-bin
EOF
    exit 1
fi
