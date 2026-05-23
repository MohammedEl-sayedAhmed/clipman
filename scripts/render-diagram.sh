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
# We deliberately use ONE renderer (cairosvg) for both local and CI so
# the byte-for-byte CI comparison stays stable. cairosvg is pure
# Python plus libcairo, available without sudo, and produces
# deterministic output across machines for the same SVG. rsvg-convert
# would also work but yields different bytes than cairosvg for the
# same SVG, which broke the verify workflow when the two were mixed.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SVG="$ROOT/docs/architecture.svg"
PNG="$ROOT/docs/architecture.png"
WIDTH=1600
VENV="${XDG_CACHE_HOME:-$HOME/.cache}/clipman-render-venv"

if [[ ! -f "$SVG" ]]; then
    echo "error: source SVG missing at $SVG" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 is required" >&2
    exit 1
fi

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "setting up one-shot venv at $VENV (cairosvg)..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet 'cairosvg==2.9.0'
fi

"$VENV/bin/python" - "$SVG" "$PNG" "$WIDTH" <<'PY'
import sys
import cairosvg
cairosvg.svg2png(
    url=sys.argv[1],
    write_to=sys.argv[2],
    output_width=int(sys.argv[3]),
)
PY

echo "rendered $SVG -> $PNG (cairosvg, ${WIDTH}px wide)"
