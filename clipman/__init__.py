import gettext
import os

# Public version constant — re-exported from the leaf ``_version`` module
# so submodules can import ``__version__`` without re-entering the
# package root (CodeQL py/cyclic-import).
from clipman._version import __version__

LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locale"
)
gettext.bindtextdomain("clipman", LOCALE_DIR)
gettext.textdomain("clipman")
_ = gettext.gettext

__all__ = ["__version__", "_", "LOCALE_DIR"]
