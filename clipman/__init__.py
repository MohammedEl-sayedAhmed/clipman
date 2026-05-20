import gettext
import os

# Source of truth for the running daemon version.
# scripts/bump-version.sh keeps this in sync with pyproject.toml.
__version__ = "1.0.6"

LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locale"
)
gettext.bindtextdomain("clipman", LOCALE_DIR)
gettext.textdomain("clipman")
_ = gettext.gettext
