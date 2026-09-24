#!/usr/bin/env bash
#
# Install the built wheel into a clean venv and run it, the way a user
# gets it from PyPI. CI runs this on every pull request (test.yml), and
# the release runs it on the exact files it uploads (release.yml), so the
# two check the same things.
#
# Usage: wheel-smoke.sh <dist-dir> <expected-version>
# Uses $PYTHON (default python3) to create the venv.

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <dist-dir> <expected-version>" >&2
    exit 2
fi
dist=$(cd "$1" && pwd)
expected="$2"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

"${PYTHON:-python3}" -m venv "$work/venv"
"$work/venv/bin/pip" install --quiet --no-deps "$dist"/*.whl

# The sdist must ship the stylesheet. List to a file first: `tar | grep -q`
# can fail under pipefail when grep exits before tar has finished writing.
tar tzf "$dist"/*.tar.gz > "$work/sdist-files.txt"
grep -q 'clipman/style.css' "$work/sdist-files.txt"

# Leave the checkout so the installed package, not the source tree, is
# imported.
cd "$work"
actual=$("$work/venv/bin/clipman" --version)
if [ "$actual" != "clipman $expected" ]; then
    echo "::error::the wheel reports '$actual', expected 'clipman $expected'" >&2
    exit 1
fi
"$work/venv/bin/python" -m clipman --version
"$work/venv/bin/python" -c "from importlib.resources import files; assert files('clipman').joinpath('style.css').is_file()"
echo "wheel smoke: OK ($actual)"
