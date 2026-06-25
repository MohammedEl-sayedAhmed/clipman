#!/usr/bin/env bash
# bump-version.sh <new-version>
#
# Updates the version string across every place it lives in the repo and
# stages a commit. Pass the bare version (no "v" prefix), e.g. 1.0.5.
#
# Files touched:
#   - pyproject.toml          ([project] version)
#   - snap/snapcraft.yaml     (version: '...')
#   - flathub/*.json          (tag URL in source array)
#   - aur/PKGBUILD            (pkgver= line)
#
# The GNOME Shell extension's metadata.json uses an unrelated integer
# version (bumped on D-Bus / behavior changes), so it is left alone.

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <new-version>" >&2
    echo "e.g.   $0 1.0.5" >&2
    exit 2
fi

new="$1"
if ! [[ "$new" =~ ^[0-9]+\.[0-9]+\.[0-9]+([a-z0-9.-]*)?$ ]]; then
    echo "error: '$new' doesn't look like a version (e.g. 1.0.5)" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

old=$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)
echo "Bumping $old -> $new"

# pyproject.toml
sed -i -E "s/^(version = )\"[^\"]+\"/\1\"$new\"/" pyproject.toml

# clipman/_version.py — daemon-side __version__ constant. (Moved out of
# __init__.py to break a CodeQL py/cyclic-import; __init__.py now re-
# exports from _version, so the public ``clipman.__version__`` API is
# unchanged.)
if [ -f clipman/_version.py ]; then
    sed -i -E "s/^(__version__ = )\"[^\"]+\"/\1\"$new\"/" clipman/_version.py
fi

# snap/snapcraft.yaml
sed -i -E "s/^(version: )'?[^'\"]+'?/\1'$new'/" snap/snapcraft.yaml

# flathub manifest — bump any tag-based source URL that ends in /v<old>.tar.gz
if [ -d flathub ]; then
    sed -i -E "s|/v$old(\.tar\.gz)|/v$new\1|g" flathub/*.json 2>/dev/null || true
    sed -i -E "s|\"tag\":\s*\"v$old\"|\"tag\": \"v$new\"|g" flathub/*.json 2>/dev/null || true
fi

# AUR PKGBUILD
if [ -f aur/PKGBUILD ]; then
    sed -i -E "s/^(pkgver=).*/\1$new/" aur/PKGBUILD
fi

# Summary of changes (don't commit automatically — let caller review)
echo
echo "Diff summary:"
git --no-pager diff --stat pyproject.toml snap/snapcraft.yaml flathub aur 2>/dev/null || true
echo
echo "Next steps:"
echo "  1. Update CHANGELOG.md (rename ## [Unreleased] -> ## [$new] - $(date -I))"
echo "  2. git add -p && git commit -m \"chore: bump to $new\""
echo "  3. git tag -s v$new -m \"v$new\"  # or unsigned: git tag v$new"
echo "  4. git push && git push --tags"
echo "     (the tag push triggers .github/workflows/release.yml)"
echo "  5. Once the tag is on the remote, refresh AUR metadata:"
echo "     ./scripts/update-aur.sh  # computes sha256, regenerates .SRCINFO"
echo "     then commit aur/ and push to ssh://aur@aur.archlinux.org/clipman-clipboard.git"
