import St from 'gi://St';
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const PASTE_DBUS_IFACE = `
<node>
  <interface name="org.gnome.Shell.Extensions.clipman">
    <method name="SimulatePaste">
      <arg type="s" direction="in" name="mode"/>
    </method>
    <method name="MoveWindowToCursor">
      <arg type="s" direction="in" name="title"/>
    </method>
  </interface>
</node>`;

const TERMINAL_WM_CLASSES = [
    'gnome-terminal-server', 'tilix', 'kitty', 'alacritty',
    'terminator', 'xterm', 'konsole', 'foot', 'wezterm',
    'st', 'sakura', 'xfce4-terminal', 'mate-terminal',
    'lxterminal', 'guake', 'tilda', 'cool-retro-term',
];

// Keystroke recipes: ordered list of (keyval, modifiers-implied-by-keystroke).
// The first element of each pair is the actual keyval to press; modifier
// keys are emitted around the press/release.
const PASTE_RECIPES = {
    'ctrl-v': {modifiers: ['Control_L'], key: 'v'},
    'ctrl-shift-v': {modifiers: ['Control_L', 'Shift_L'], key: 'v'},
    'shift-insert': {modifiers: ['Shift_L'], key: 'Insert'},
};

const KEY_LOOKUP = {
    'Control_L': Clutter.KEY_Control_L,
    'Shift_L': Clutter.KEY_Shift_L,
    'Alt_L': Clutter.KEY_Alt_L,
    'Super_L': Clutter.KEY_Super_L,
    'v': Clutter.KEY_v,
    'Insert': Clutter.KEY_Insert,
};

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
            'org.gnome.Shell.Extensions.clipman',
            Gio.BusNameOwnerFlags.NONE,
            null, null
        );

        // Expose D-Bus interface so the daemon can request paste simulation
        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(
            PASTE_DBUS_IFACE, this
        );
        this._dbusImpl.export(Gio.DBus.session, '/org/gnome/Shell/Extensions/clipman');
    }

    disable() {
        if (this._clipboardTimeout) {
            GLib.source_remove(this._clipboardTimeout);
            this._clipboardTimeout = null;
        }
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

    SimulatePaste(mode) {
        const recipe = this._resolveRecipe(mode);
        this._dispatchKeystroke(recipe);
    }

    _resolveRecipe(mode) {
        // 'auto' (or missing) -> Ctrl+V unless focused window is a terminal,
        // in which case Ctrl+Shift+V. Explicit modes override.
        if (mode && PASTE_RECIPES[mode])
            return PASTE_RECIPES[mode];

        const focusWin = global.display.get_focus_window();
        const wmClass = focusWin?.get_wm_class()?.toLowerCase() ?? '';
        const isTerminal = TERMINAL_WM_CLASSES.some(c => wmClass.includes(c));
        return isTerminal ? PASTE_RECIPES['ctrl-shift-v'] : PASTE_RECIPES['ctrl-v'];
    }

    _dispatchKeystroke(recipe) {
        const seat = Clutter.get_default_backend().get_default_seat();
        const vk = seat.create_virtual_device(
            Clutter.InputDeviceType.KEYBOARD_DEVICE
        );

        for (const mod of recipe.modifiers) {
            vk.notify_keyval(Clutter.CURRENT_TIME,
                KEY_LOOKUP[mod], Clutter.KeyState.PRESSED);
        }
        vk.notify_keyval(Clutter.CURRENT_TIME,
            KEY_LOOKUP[recipe.key], Clutter.KeyState.PRESSED);
        vk.notify_keyval(Clutter.CURRENT_TIME,
            KEY_LOOKUP[recipe.key], Clutter.KeyState.RELEASED);
        for (const mod of [...recipe.modifiers].reverse()) {
            vk.notify_keyval(Clutter.CURRENT_TIME,
                KEY_LOOKUP[mod], Clutter.KeyState.RELEASED);
        }
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

        // Debounce: wait 150ms for the new clipboard owner to make
        // content available. Rapid copies cancel the previous read.
        if (this._clipboardTimeout) {
            GLib.source_remove(this._clipboardTimeout);
            this._clipboardTimeout = null;
        }

        this._clipboardTimeout = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, 150, () => {
                this._clipboardTimeout = null;
                this._getClipboardText().then(text => {
                    if (text) {
                        this._sendToDaemon('text', text);
                    } else {
                        this._sendToDaemon('image', '');
                    }
                }).catch(() => {});
                return GLib.SOURCE_REMOVE;
            }
        );
    }

    _getClipboardText() {
        const clipboard = St.Clipboard.get_default();
        const mimeTypes = [
            'text/plain;charset=utf-8',
            'UTF8_STRING',
            'text/plain',
            'STRING',
        ];

        const tryType = (index) => {
            if (index >= mimeTypes.length)
                return Promise.resolve(null);

            return new Promise(resolve => {
                clipboard.get_content(
                    St.ClipboardType.CLIPBOARD,
                    mimeTypes[index],
                    (_cb, bytes) => {
                        if (bytes && bytes.get_size() > 0) {
                            let data = bytes.get_data();
                            // Trim trailing null byte (some X11 apps include it)
                            if (data.length > 0 && data[data.length - 1] === 0)
                                data = data.slice(0, -1);
                            resolve(new TextDecoder().decode(data));
                        } else {
                            resolve(null);
                        }
                    }
                );
            }).then(text => text || tryType(index + 1));
        };

        return tryType(0);
    }

    _sendToDaemon(contentType, content) {
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
    }
}
