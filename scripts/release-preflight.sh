#!/usr/bin/env bash
#
# Check that every file carrying the version agrees with the release, and
# that CHANGELOG.md has a dated section for it. Run from the repository
# root. The release workflow runs this before it builds anything, and
# tests/test_release_metadata.py runs it on a freshly bumped copy.
#
# Usage: release-preflight.sh <version>    (no "v": 1.2.3)

set -uo pipefail

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <version>" >&2
    exit 2
fi
expected="$1"
fail=0

check() {  # check <label> <actual>
    if [ "$2" != "$expected" ]; then
        echo "::error::$1 version '$2' does not match tag ($expected)"
        fail=1
    else
        echo "OK: $1 $2"
    fi
}

check pyproject.toml       "$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)"
check clipman/_version.py  "$(grep -m1 '^__version__ = ' clipman/_version.py | cut -d'"' -f2)"
check snap/snapcraft.yaml  "$(grep -m1 '^version: ' snap/snapcraft.yaml | sed -E "s/version: ['\"]?([^'\"]+)['\"]?/\1/")"
check CITATION.cff         "$(grep -m1 '^version: ' CITATION.cff | cut -d' ' -f2)"
check aur/PKGBUILD         "$(grep -m1 '^pkgver=' aur/PKGBUILD | cut -d= -f2)"
check aur/.SRCINFO         "$(awk -F' = ' '/^[[:space:]]*pkgver = /{print $2; exit}' aur/.SRCINFO)"
check flathub-manifest     "$(cat flathub/*.json | grep -m1 -o 'clipman/archive/refs/tags/v[^"]*\.tar\.gz' | sed -E 's|.*/v(.*)\.tar\.gz|\1|')"
for f in data/*.metainfo.xml; do
    check "$f (first <release>)" "$(grep -m1 -o '<release version="[^"]*"' "$f" | cut -d'"' -f2)"
done
if ! grep -Eq "^## \[${expected//./\\.}\] - [0-9]{4}-[0-9]{2}-[0-9]{2}" CHANGELOG.md; then
    echo "::error::CHANGELOG.md has no '## [$expected] - <date>' section"
    fail=1
fi
exit "$fail"
