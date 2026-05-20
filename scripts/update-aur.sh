#!/usr/bin/env bash
# update-aur.sh
#
# Refresh aur/PKGBUILD and aur/.SRCINFO for the **already-tagged** release.
# Run this AFTER `git tag vX.Y.Z && git push --tags` because it computes the
# sha256 of the GitHub source tarball, which only exists once the tag is on
# the remote.
#
# What it does:
#   1. Reads the current version from pyproject.toml.
#   2. Downloads the v<version>.tar.gz tarball from GitHub.
#   3. Updates the sha256sums line in aur/PKGBUILD.
#   4. Regenerates aur/.SRCINFO (manual parse — no makepkg needed).
#
# What it does NOT do:
#   - Push to AUR. That's a separate manual step against
#     ssh://aur@aur.archlinux.org/clipman-clipboard.git (see README).

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

version=$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)
echo "Refreshing AUR files for v$version"

tarball_url="https://github.com/MohammedEl-sayedAhmed/clipman/archive/v$version.tar.gz"
echo "Fetching $tarball_url ..."
tmp=$(mktemp -t aur-tarball.XXXXXX.tar.gz)
trap 'rm -f "$tmp"' EXIT
curl -fsSL "$tarball_url" -o "$tmp"

sha=$(sha256sum "$tmp" | cut -d' ' -f1)
echo "sha256: $sha"

# PKGBUILD: update sha256sums=
sed -i -E "s/^(sha256sums=\\()'[^']+'\\)/\\1'$sha')/" aur/PKGBUILD

# .SRCINFO: regenerate from PKGBUILD (manual — no makepkg needed)
pkgrel=$(grep -m1 '^pkgrel=' aur/PKGBUILD | cut -d= -f2)
{
    echo "pkgbase = clipman-clipboard"
    echo "	pkgdesc = A clipboard history manager for Wayland (GNOME, KDE, Sway, Hyprland, etc.)"
    echo "	pkgver = $version"
    echo "	pkgrel = $pkgrel"
    echo "	url = https://github.com/MohammedEl-sayedAhmed/clipman"
    echo "	arch = any"
    echo "	license = Apache-2.0"
    echo "	depends = python>=3.10"
    echo "	depends = python-gobject"
    echo "	depends = python-dbus"
    echo "	depends = gtk3"
    echo "	depends = wl-clipboard"
    echo "	optdepends = gnome-shell: native clipboard monitoring via GNOME Shell extension"
    echo "	source = clipman-$version.tar.gz::https://github.com/MohammedEl-sayedAhmed/clipman/archive/v$version.tar.gz"
    echo "	sha256sums = $sha"
    echo ""
    echo "pkgname = clipman-clipboard"
} > aur/.SRCINFO

echo
echo "Updated:"
git --no-pager diff --stat aur/ 2>/dev/null || true
echo
echo "Next steps:"
echo "  1. Review the diff above."
echo "  2. Commit the updated aur/PKGBUILD + aur/.SRCINFO to this repo."
echo "  3. Push to AUR (separate repo):"
echo "       git clone ssh://aur@aur.archlinux.org/clipman-clipboard.git /tmp/aur-clipman"
echo "       cp aur/PKGBUILD aur/.SRCINFO /tmp/aur-clipman/"
echo "       cd /tmp/aur-clipman && git add PKGBUILD .SRCINFO"
echo "       git commit -m 'Update to $version'"
echo "       git push"
