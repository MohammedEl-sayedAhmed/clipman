#!/usr/bin/env bash
#
# Refresh the release hashes for the version in pyproject.toml.
#
# Downloads the GitHub source tarball for v<version>, writes its sha256
# into aur/PKGBUILD and the Flatpak manifest, and regenerates
# aur/.SRCINFO from aur/PKGBUILD. Run it after the tag exists on GitHub,
# because the tarball is generated from the tag. It does not push to AUR.

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

# aur/.SRCINFO mirrors aur/PKGBUILD. makepkg is not available on the
# Debian-based CI runners, so read the PKGBUILD variables in a subshell.
# shellcheck disable=SC2154  # the variables come from aur/PKGBUILD
gen_srcinfo() {
    (
        # shellcheck source=/dev/null
        source aur/PKGBUILD
        printf 'pkgbase = %s\n' "$pkgname"
        printf '\tpkgdesc = %s\n' "$pkgdesc"
        printf '\tpkgver = %s\n' "$pkgver"
        printf '\tpkgrel = %s\n' "$pkgrel"
        printf '\turl = %s\n' "$url"
        for item in "${arch[@]}"; do printf '\tarch = %s\n' "$item"; done
        for item in "${license[@]}"; do printf '\tlicense = %s\n' "$item"; done
        for item in "${depends[@]}"; do printf '\tdepends = %s\n' "$item"; done
        for item in "${optdepends[@]}"; do printf '\toptdepends = %s\n' "$item"; done
        for item in "${source[@]}"; do printf '\tsource = %s\n' "$item"; done
        for item in "${sha256sums[@]}"; do printf '\tsha256sums = %s\n' "$item"; done
        printf '\npkgname = %s\n' "$pkgname"
    )
}
# Print the .SRCINFO for the current aur/PKGBUILD and stop. The tests use
# this to check that the committed file has not drifted.
if [ "${1:-}" = "--print-srcinfo" ]; then
    gen_srcinfo
    exit 0
fi

version=$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)
pkgver=$(grep -m1 '^pkgver=' aur/PKGBUILD | cut -d= -f2)
if [ "$pkgver" != "$version" ]; then
    echo "error: aur/PKGBUILD has pkgver=$pkgver but pyproject.toml says $version" >&2
    echo "       run scripts/bump-version.sh first" >&2
    exit 1
fi

tarball_url="https://github.com/MohammedEl-sayedAhmed/clipman/archive/refs/tags/v$version.tar.gz"
echo "Refreshing release hashes for v$version"
echo "Fetching $tarball_url ..."
tmp=$(mktemp -t clipman-tarball.XXXXXX)
trap 'rm -f "$tmp"' EXIT
curl -fsSL "$tarball_url" -o "$tmp"

sha=$(sha256sum "$tmp" | cut -d' ' -f1)
echo "sha256: $sha"

# aur/PKGBUILD: the sha256sums line. Then regenerate aur/.SRCINFO from it.
sed -i -E "s/^(sha256sums=\()'[^']+'\)/\1'$sha')/" aur/PKGBUILD
gen_srcinfo > aur/.SRCINFO

# Flatpak manifest: the sha256 of the clipman tarball source. The old
# value is replaced as text so the file keeps its formatting.
for manifest in flathub/*.json; do
    [ -f "$manifest" ] || continue
    python3 - "$manifest" "$version" "$sha" <<'PY'
import json
import sys

path, version, sha = sys.argv[1:]
text = open(path, encoding="utf-8").read()
module = next(m for m in json.loads(text)["modules"] if m["name"] == "clipman")
source = next(s for s in module["sources"] if s.get("type") == "archive")
if not source["url"].endswith(f"/v{version}.tar.gz"):
    sys.exit(f"{path}: the clipman source is {source['url']}, not v{version}")
old = source["sha256"]
if text.count(old) != 1:
    sys.exit(f"{path}: expected the old sha256 once, found {text.count(old)}")
open(path, "w", encoding="utf-8").write(text.replace(old, sha))
PY
done

echo
echo "Updated:"
git --no-pager diff --stat aur/ flathub/ 2>/dev/null || true
echo
echo "Next steps:"
echo "  1. Review the diff above and open a PR with the updated aur/ and flathub/ files."
echo "  2. The publish-aur job in release.yml pushes PKGBUILD and .SRCINFO to AUR on a"
echo "     tag. By hand: clone ssh://aur@aur.archlinux.org/clipman-clipboard.git, copy"
echo "     aur/PKGBUILD and aur/.SRCINFO into it, commit 'Update to $version', push."
