"""Best-effort calls from the daemon to the GNOME Shell extension."""

import logging

import dbus

logger = logging.getLogger(__name__)

EXT_BUS_NAME = "org.gnome.Shell.Extensions.clipman"
EXT_OBJECT_PATH = "/org/gnome/Shell/Extensions/clipman"
EXT_IFACE = "org.gnome.Shell.Extensions.clipman"


def extension_iface():
    """Return a proxy for the extension, or None when it is absent."""
    try:
        bus = dbus.SessionBus()
        if not bus.name_has_owner(EXT_BUS_NAME):
            return None
        proxy = bus.get_object(EXT_BUS_NAME, EXT_OBJECT_PATH)
        return dbus.Interface(proxy, EXT_IFACE)
    except dbus.DBusException:
        logger.debug("extension proxy unavailable", exc_info=True)
        return None


def set_paused(paused):
    """Tell the extension to stop or resume clipboard reads.

    Return True when the call succeeded. Extensions older than
    contract version 8 have no SetPaused method; that returns False.
    """
    iface = extension_iface()
    if iface is None:
        return False
    try:
        iface.SetPaused(bool(paused))
        return True
    except dbus.DBusException as exc:
        logger.debug("SetPaused not accepted by the extension: %s", exc)
        return False
