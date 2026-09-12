import unittest
from unittest.mock import MagicMock, patch

import dbus

import clipman.shell_bridge as shell_bridge


class TestSetPaused(unittest.TestCase):
    """set_paused never raises; it only reports success or failure."""

    def _bus(self, owned=True):
        bus = MagicMock()
        bus.name_has_owner.return_value = owned
        return bus

    def test_calls_the_extension(self):
        bus = self._bus()
        iface = MagicMock()
        with patch("clipman.shell_bridge.dbus.SessionBus", return_value=bus), \
             patch("clipman.shell_bridge.dbus.Interface", return_value=iface):
            self.assertTrue(shell_bridge.set_paused(True))
        iface.SetPaused.assert_called_once_with(True)

    def test_extension_absent(self):
        with patch("clipman.shell_bridge.dbus.SessionBus",
                   return_value=self._bus(owned=False)):
            self.assertFalse(shell_bridge.set_paused(True))

    def test_old_extension_without_the_method(self):
        bus = self._bus()
        iface = MagicMock()
        iface.SetPaused.side_effect = dbus.DBusException(
            "org.freedesktop.DBus.Error.UnknownMethod")
        with patch("clipman.shell_bridge.dbus.SessionBus", return_value=bus), \
             patch("clipman.shell_bridge.dbus.Interface", return_value=iface):
            self.assertFalse(shell_bridge.set_paused(False))

    def test_bus_unreachable(self):
        with patch("clipman.shell_bridge.dbus.SessionBus",
                   side_effect=dbus.DBusException("no bus")):
            self.assertFalse(shell_bridge.set_paused(True))
