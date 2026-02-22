import gettext
import os

LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locale"
)
gettext.bindtextdomain("clipman", LOCALE_DIR)
gettext.textdomain("clipman")
_ = gettext.gettext
