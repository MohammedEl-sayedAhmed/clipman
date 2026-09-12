import St from 'gi://St';
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// The popup's Wayland app_id / wm_class (clipman/app.py application_id).
const CLIPMAN_WM_CLASS = 'com.clipman.Clipman';

// Only the process that owns this name may call the methods below.
const DAEMON_BUS_NAME = 'com.clipman.Daemon';
const DAEMON_OBJECT_PATH = '/com/clipman/Daemon';

// Same limit as the daemon's MAX_TEXT_SIZE; it drops longer clips anyway.
const MAX_TEXT_LENGTH = 10 * 1024 * 1024;

const OWN_BUS_NAME = 'org.gnome.Shell.Extensions.clipman';
const OWN_OBJECT_PATH = '/org/gnome/Shell/Extensions/clipman';

function _isClipmanWindow(win) {
    if (!win)
        return false;
    const cls = win.get_wm_class ? win.get_wm_class() : win.wm_class;
    return cls === CLIPMAN_WM_CLASS;
}

const PASTE_DBUS_IFACE = `
<node>
  <interface name="org.gnome.Shell.Extensions.clipman">
    <method name="SimulatePaste">
      <arg type="s" direction="in" name="mode"/>
    </method>
    <method name="MoveWindowToCursor">
      <arg type="s" direction="in" name="title"/>
    </method>
    <method name="RestorePreviousFocus"/>
    <method name="SetPaused">
      <arg type="b" direction="in" name="paused"/>
    </method>
  </interface>
</node>`;

const TERMINAL_WM_CLASSES = [
    'gnome-terminal-server', 'tilix', 'kitty', 'alacritty',
    'terminator', 'xterm', 'konsole', 'foot', 'wezterm',
    'st', 'sakura', 'xfce4-terminal', 'mate-terminal',
    'lxterminal', 'guake', 'tilda', 'cool-retro-term',
];

// Null-prototype tables: a mode such as "__proto__" must not resolve.
const PASTE_RECIPES = Object.assign(Object.create(null), {
    'ctrl-v': {modifiers: ['Control_L'], key: 'v'},
    'ctrl-shift-v': {modifiers: ['Control_L', 'Shift_L'], key: 'v'},
    'shift-insert': {modifiers: ['Shift_L'], key: 'Insert'},
});

const KEY_LOOKUP = Object.assign(Object.create(null), {
    'Control_L': Clutter.KEY_Control_L,
    'Shift_L': Clutter.KEY_Shift_L,
    'v': Clutter.KEY_v,
    'Insert': Clutter.KEY_Insert,
});

export default class ClipmanExtension extends Extension {
    enable() {
        this._destroyed = false;
        this._paused = false;
        this._prevFocus = null;
        this._hiddenWindows = new Set();
        this._daemonOwner = null;
        this._daemonPid = 0;
        this._deniedSenders = new Set();
        this._virtualKeyboard = null;
        this._clipboardTimeout = null;

        this._selection = global.display.get_selection();
        this._ownerChangedId = this._selection.connect(
            'owner-changed',
            this._onOwnerChanged.bind(this)
        );

        // Learn which connection owns the daemon name; only it may call us.
        this._daemonWatchId = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            DAEMON_BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            (_connection, _name, owner) => this._onDaemonAppeared(owner),
            () => this._onDaemonVanished()
        );

        this._busNameId = Gio.bus_own_name_on_connection(
            Gio.DBus.session,
            OWN_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            null,
            () => console.warn(`clipman: lost the bus name ${OWN_BUS_NAME}`)
        );

        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(
            PASTE_DBUS_IFACE, this
        );
        this._dbusImpl.export(Gio.DBus.session, OWN_OBJECT_PATH);

        // Before GNOME 49 there is no hide_from_window_list(); filter the
        // alt-tab and dash lists instead.
        if (!Meta.Window.prototype.hide_from_window_list)
            this._installWindowListPatches();
    }

    disable() {
        this._destroyed = true;
        this._removeWindowListPatches();
        if (this._clipboardTimeout) {
            GLib.source_remove(this._clipboardTimeout);
            this._clipboardTimeout = null;
        }
        if (this._ownerChangedId) {
            this._selection.disconnect(this._ownerChangedId);
            this._ownerChangedId = null;
        }
        this._selection = null;
        if (this._dbusImpl) {
            this._dbusImpl.unexport();
            this._dbusImpl = null;
        }
        if (this._busNameId) {
            Gio.bus_unown_name(this._busNameId);
            this._busNameId = null;
        }
        if (this._daemonWatchId) {
            Gio.bus_unwatch_name(this._daemonWatchId);
            this._daemonWatchId = 0;
        }
        this._showHiddenWindows();
        this._prevFocus = null;
        this._daemonOwner = null;
        this._daemonPid = 0;
        this._deniedSenders.clear();
        this._virtualKeyboard = null;
    }

    // ---- Window list patches (GNOME 45 to 48) -------------------------

    _installWindowListPatches() {
        this._origGetTabList = global.display.get_tab_list;
        const origGetTabList = this._origGetTabList;
        global.display.get_tab_list = function (type, workspace) {
            return origGetTabList.call(this, type, workspace)
                .filter(w => !_isClipmanWindow(w));
        };

        this._origAppGetWindows = Shell.App.prototype.get_windows;
        const origAppGetWindows = this._origAppGetWindows;
        Shell.App.prototype.get_windows = function () {
            return origAppGetWindows.call(this)
                .filter(w => !_isClipmanWindow(w));
        };

        // The dash lists running apps; the popup has no .desktop file, so
        // it would show up as a window-backed app. Use the original
        // get_windows here, or the app would look window-less.
        this._origGetRunning = Shell.AppSystem.prototype.get_running;
        const origGetRunning = this._origGetRunning;
        Shell.AppSystem.prototype.get_running = function () {
            return origGetRunning.call(this).filter(app => {
                let wins;
                try {
                    wins = origAppGetWindows.call(app);
                } catch {
                    return true;
                }
                return !(wins.length > 0 && wins.every(_isClipmanWindow));
            });
        };
    }

    _removeWindowListPatches() {
        if (this._origGetTabList) {
            global.display.get_tab_list = this._origGetTabList;
            this._origGetTabList = null;
        }
        if (this._origAppGetWindows) {
            Shell.App.prototype.get_windows = this._origAppGetWindows;
            this._origAppGetWindows = null;
        }
        if (this._origGetRunning) {
            Shell.AppSystem.prototype.get_running = this._origGetRunning;
            this._origGetRunning = null;
        }
    }

    // ---- Caller authentication ---------------------------------------

    _onDaemonAppeared(owner) {
        this._daemonOwner = owner;
        this._daemonPid = 0;
        this._deniedSenders.clear();
        // The pid lets MoveWindowToCursor check that a window is ours.
        Gio.DBus.session.call(
            'org.freedesktop.DBus',
            '/org/freedesktop/DBus',
            'org.freedesktop.DBus',
            'GetConnectionUnixProcessID',
            new GLib.Variant('(s)', [owner]),
            new GLib.VariantType('(u)'),
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (connection, result) => {
                try {
                    const [pid] = connection.call_finish(result).deepUnpack();
                    if (this._daemonOwner === owner)
                        this._daemonPid = pid;
                } catch (e) {
                    console.warn(`clipman: pid lookup failed: ${e.message}`);
                }
            }
        );
    }

    _onDaemonVanished() {
        this._daemonOwner = null;
        this._daemonPid = 0;
    }

    // Reply with AccessDenied unless the caller owns the daemon name.
    _authorize(invocation) {
        const sender = invocation.get_sender();
        if (this._daemonOwner !== null && sender === this._daemonOwner)
            return true;
        if (!this._deniedSenders.has(sender)) {
            this._deniedSenders.add(sender);
            console.warn(
                `clipman: denied ${invocation.get_method_name()} from ` +
                `${sender}: not the owner of ${DAEMON_BUS_NAME}`
            );
        }
        invocation.return_error_literal(
            Gio.DBusError,
            Gio.DBusError.ACCESS_DENIED,
            `Only the owner of ${DAEMON_BUS_NAME} may call this method`
        );
        return false;
    }

    // ---- D-Bus methods -----------------------------------------------

    SimulatePasteAsync([mode], invocation) {
        if (!this._authorize(invocation))
            return;
        try {
            this._dispatchKeystroke(this._resolveRecipe(mode));
            invocation.return_value(null);
        } catch (e) {
            invocation.return_dbus_error(
                'org.gnome.Shell.Extensions.clipman.Error', e.message);
        }
    }

    MoveWindowToCursorAsync([title], invocation) {
        if (!this._authorize(invocation))
            return;
        try {
            this._moveWindowToCursor(title);
            invocation.return_value(null);
        } catch (e) {
            invocation.return_dbus_error(
                'org.gnome.Shell.Extensions.clipman.Error', e.message);
        }
    }

    RestorePreviousFocusAsync(_params, invocation) {
        if (!this._authorize(invocation))
            return;
        const prev = this._prevFocus;
        this._prevFocus = null;
        if (prev && !_isClipmanWindow(prev)) {
            try {
                prev.activate(global.get_current_time());
            } catch {
                // The window closed meanwhile; the paste goes to the
                // current focus.
            }
        }
        invocation.return_value(null);
    }

    SetPausedAsync([paused], invocation) {
        if (!this._authorize(invocation))
            return;
        this._paused = Boolean(paused);
        if (this._paused && this._clipboardTimeout) {
            GLib.source_remove(this._clipboardTimeout);
            this._clipboardTimeout = null;
        }
        invocation.return_value(null);
    }

    // ---- Paste -------------------------------------------------------

    _resolveRecipe(mode) {
        if (typeof mode === 'string' && Object.hasOwn(PASTE_RECIPES, mode))
            return PASTE_RECIPES[mode];

        // 'auto': Ctrl+V, or Ctrl+Shift+V when a terminal has focus.
        const focusWin = global.display.get_focus_window();
        const wmClass = focusWin?.get_wm_class()?.toLowerCase() ?? '';
        const isTerminal = TERMINAL_WM_CLASSES.some(c => wmClass.includes(c));
        return isTerminal ? PASTE_RECIPES['ctrl-shift-v'] : PASTE_RECIPES['ctrl-v'];
    }

    _getVirtualKeyboard() {
        if (!this._virtualKeyboard) {
            const seat = Clutter.get_default_backend().get_default_seat();
            this._virtualKeyboard = seat.create_virtual_device(
                Clutter.InputDeviceType.KEYBOARD_DEVICE);
        }
        return this._virtualKeyboard;
    }

    _dispatchKeystroke(recipe) {
        const vk = this._getVirtualKeyboard();
        const pressed = [];
        try {
            for (const mod of recipe.modifiers) {
                vk.notify_keyval(Clutter.CURRENT_TIME,
                    KEY_LOOKUP[mod], Clutter.KeyState.PRESSED);
                pressed.push(mod);
            }
            vk.notify_keyval(Clutter.CURRENT_TIME,
                KEY_LOOKUP[recipe.key], Clutter.KeyState.PRESSED);
            vk.notify_keyval(Clutter.CURRENT_TIME,
                KEY_LOOKUP[recipe.key], Clutter.KeyState.RELEASED);
        } finally {
            // Never leave a modifier held down.
            for (const mod of pressed.reverse()) {
                vk.notify_keyval(Clutter.CURRENT_TIME,
                    KEY_LOOKUP[mod], Clutter.KeyState.RELEASED);
            }
        }
    }

    // ---- Popup placement ---------------------------------------------

    _moveWindowToCursor(title) {
        const [x, y] = global.get_pointer();
        const monitor = global.display.get_current_monitor();
        const workArea = global.display.get_workspace_manager()
            .get_active_workspace().get_work_area_for_monitor(monitor);

        for (const actor of global.get_window_actors()) {
            const metaWin = actor.get_meta_window();
            if (!metaWin || !_isClipmanWindow(metaWin))
                continue;
            if (this._daemonPid && metaWin.get_pid() !== this._daemonPid)
                continue;
            if (metaWin.get_title() !== title)
                continue;

            const rect = metaWin.get_frame_rect();
            let winX = Math.min(x, workArea.x + workArea.width - rect.width);
            let winY = Math.min(y, workArea.y + workArea.height - rect.height);
            winX = Math.max(workArea.x, winX);
            winY = Math.max(workArea.y, winY);
            metaWin.move_frame(true, winX, winY);

            // Remember the user's window before we take focus, so the
            // paste can go back to it.
            const focused = global.display.get_focus_window();
            if (focused && !_isClipmanWindow(focused))
                this._prevFocus = focused;

            this._hideFromWindowList(metaWin);
            // A background daemon's window is mapped without focus; only
            // the Shell can give it focus on Wayland.
            metaWin.activate(global.get_current_time());
            break;
        }
    }

    _hideFromWindowList(metaWin) {
        if (!metaWin.hide_from_window_list)
            return;
        metaWin.hide_from_window_list();
        this._hiddenWindows.add(metaWin);
    }

    _showHiddenWindows() {
        for (const win of this._hiddenWindows) {
            try {
                if (win.show_in_window_list)
                    win.show_in_window_list();
            } catch {
                // The window is gone already.
            }
        }
        this._hiddenWindows.clear();
    }

    // ---- Clipboard capture -------------------------------------------

    _onOwnerChanged(_selection, selectionType, _selectionSource) {
        if (selectionType !== Meta.SelectionType.SELECTION_CLIPBOARD)
            return;
        if (this._paused)
            return;

        // Wait 150 ms for the new owner to make the content available.
        // Rapid copies cancel the previous read.
        if (this._clipboardTimeout) {
            GLib.source_remove(this._clipboardTimeout);
            this._clipboardTimeout = null;
        }

        this._clipboardTimeout = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, 150, () => {
                this._clipboardTimeout = null;
                this._getClipboardText().then(text => {
                    if (this._destroyed || this._paused)
                        return;
                    if (text)
                        this._sendToDaemon('text', text);
                    else
                        this._sendToDaemon('image', '');
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
                            // Some X11 apps include a trailing null byte.
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
        if (content.length > MAX_TEXT_LENGTH)
            return;
        Gio.DBus.session.call(
            DAEMON_BUS_NAME,
            DAEMON_OBJECT_PATH,
            DAEMON_BUS_NAME,
            'NewEntry',
            new GLib.Variant('(ss)', [contentType, content]),
            null,
            Gio.DBusCallFlags.NO_AUTO_START,
            -1,
            null,
            (connection, result) => {
                try {
                    connection.call_finish(result);
                } catch (e) {
                    console.debug(`clipman: NewEntry not delivered: ${e.message}`);
                }
            }
        );
    }
}
