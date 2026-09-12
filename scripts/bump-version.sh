#!/usr/bin/env bash
# bump-version.sh <new-version>
#
# Updates the version string in every file that carries it and leaves
# the changes unstaged for review. Pass the bare version (no "v"
# prefix), e.g. 1.0.5.
#
# Files touched:
#   - pyproject.toml          ([project] version)
#   - clipman/_version.py     (__version__)
#   - snap/snapcraft.yaml     (version: '...')
#   - flathub/*.json          (tag URL in the source array)
#   - aur/PKGBUILD            (pkgver= line)
#   - CITATION.cff            (version + date-released)
#   - data/*.metainfo.xml     (a new, empty <release> entry)
#
# The tarball hashes in aur/ and flathub/ can only be computed once the
# tag exists; scripts/update-aur.sh does that. The GNOME Shell
# extension's metadata.json uses an unrelated integer version, so it is
# left alone.

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

# CITATION.cff — project version + release date (cff-version is the CFF
# schema version, not ours; the anchored patterns leave it alone).
if [ -f CITATION.cff ]; then
    sed -i -E "s/^(version: ).*/\1$new/" CITATION.cff
    sed -i -E "s/^(date-released: ).*/\1$(date -I)/" CITATION.cff
fi

# AppStream metainfo — add an empty <release> entry at the top of the
# list. Fill in the notes together with the CHANGELOG.
for metainfo in data/*.metainfo.xml; do
    [ -f "$metainfo" ] || continue
    if grep -q "<release version=\"$new\"" "$metainfo"; then
        continue
    fi
    sed -i -E "s|^( *)<releases>|\1<releases>\n\1  <release version=\"$new\" date=\"$(date -I)\"/>|" "$metainfo"
done

# Summary of changes (don't commit automatically — let caller review)
echo
echo "Diff summary:"
git --no-pager diff --stat pyproject.toml clipman/_version.py snap/snapcraft.yaml \
    flathub aur CITATION.cff data 2>/dev/null || true
echo
echo "Next steps (AGENTS.md, Release chain):"
echo "  1. Update CHANGELOG.md: rename ## [Unreleased] -> ## [$new] - $(date -I),"
echo "     and put the release notes into the new <release> entry in data/*.metainfo.xml."
echo "  2. Open a release PR and squash-merge it."
echo "  3. Create the tag through the GitHub API, pointing at the squash commit:"
echo "       gh api repos/MohammedEl-sayedAhmed/clipman/git/refs \\"
echo "           -f ref=refs/tags/v$new -f sha=<squash commit sha>"
echo "     (the pre-push hook rejects git push --tags for squash commits)"
echo "  4. The tag triggers .github/workflows/release.yml."
echo "  5. Once the tag exists, run scripts/update-aur.sh to refresh the AUR and"
echo "     Flatpak tarball hashes, then open a PR with the result."
