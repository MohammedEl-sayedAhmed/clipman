import St from 'gi://St';
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const PASTE_DBUS_IFACE = `
<node>
  <interface name="com.clipman.Extension">
    <method name="SimulatePaste"/>
    <method name="MoveWindowToCursor">
      <arg type="s" direction="in" name="title"/>
    </method>
  </interface>
</node>`;

export default class ClipmanExtension extends Extension {
    enable() {
        this._selection = global.display.get_selection();
        this._ownerChangedId = this._selection.connect(
            'owner-changed',
            this._onOwnerChanged.bind(this)
        );

        // Own a bus name so the daemon can find us
        this._busNameId = Gio.bus_own_name_on_connection(
            Gio.DBus.session,
            'com.clipman.Extension',
            Gio.BusNameOwnerFlags.NONE,
            null, null
        );

        // Expose D-Bus interface so the daemon can request paste simulation
        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(
            PASTE_DBUS_IFACE, this
        );
        this._dbusImpl.export(Gio.DBus.session, '/com/clipman/Extension');
    }

    disable() {
        if (this._ownerChangedId) {
            this._selection.disconnect(this._ownerChangedId);
            this._ownerChangedId = null;
        }
        if (this._dbusImpl) {
            this._dbusImpl.unexport();
            this._dbusImpl = null;
        }
        if (this._busNameId) {
            Gio.bus_unown_name(this._busNameId);
            this._busNameId = null;
        }
    }

    SimulatePaste() {
        const seat = Clutter.get_default_backend().get_default_seat();
        const vk = seat.create_virtual_device(
            Clutter.InputDeviceType.KEYBOARD_DEVICE
        );
        vk.notify_keyval(
            Clutter.CURRENT_TIME,
            Clutter.KEY_Control_L, Clutter.KeyState.PRESSED
        );
        vk.notify_keyval(
            Clutter.CURRENT_TIME,
            Clutter.KEY_v, Clutter.KeyState.PRESSED
        );
        vk.notify_keyval(
            Clutter.CURRENT_TIME,
            Clutter.KEY_v, Clutter.KeyState.RELEASED
        );
        vk.notify_keyval(
            Clutter.CURRENT_TIME,
            Clutter.KEY_Control_L, Clutter.KeyState.RELEASED
        );
    }

    MoveWindowToCursor(title) {
        const [x, y] = global.get_pointer();
        const monitor = global.display.get_current_monitor();
        const workArea = global.display.get_workspace_manager()
            .get_active_workspace().get_work_area_for_monitor(monitor);

        for (const actor of global.get_window_actors()) {
            const metaWin = actor.get_meta_window();
            if (metaWin.get_title() === title) {
                const rect = metaWin.get_frame_rect();
                let winX = Math.min(x, workArea.x + workArea.width - rect.width);
                let winY = Math.min(y, workArea.y + workArea.height - rect.height);
                winX = Math.max(workArea.x, winX);
                winY = Math.max(workArea.y, winY);
                metaWin.move_frame(true, winX, winY);
                break;
            }
        }
    }

    _onOwnerChanged(_selection, selectionType, _selectionSource) {
        if (selectionType !== Meta.SelectionType.SELECTION_CLIPBOARD)
            return;

        const clipboard = St.Clipboard.get_default();

        clipboard.get_text(St.ClipboardType.CLIPBOARD, (_cb, text) => {
            if (text && text.length > 0) {
                this._sendToDaemon('text', text);
            } else {
                this._sendToDaemon('image', '');
            }
        });
    }

    _sendToDaemon(contentType, content) {
        try {
            Gio.DBus.session.call(
                'com.clipman.Daemon',
                '/com/clipman/Daemon',
                'com.clipman.Daemon',
                'NewEntry',
                new GLib.Variant('(ss)', [contentType, content]),
                null,
                Gio.DBusCallFlags.NONE,
                -1,
                null,
                null
            );
        } catch (e) {
            // Daemon not running — ignore
        }
    }
}
