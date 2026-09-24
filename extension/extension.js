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

// Same limit as the daemon's MAX_TEXT_SIZE, in UTF-8 bytes: it drops
// longer clips anyway, so reading more only costs the Shell memory.
const MAX_TEXT_BYTES = 10 * 1024 * 1024;

// An app that owns the clipboard but never sends its data would hold the
// read, and a pipe, open until it quits.
const READ_TIMEOUT_MS = 5000;
const READ_CHUNK_BYTES = 64 * 1024;

// Text types, most wanted first. Some X11 apps offer only the last two.
const TEXT_MIME_TYPES = [
    'text/plain;charset=utf-8',
    'UTF8_STRING',
    'text/plain',
    'STRING',
];

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

// Terminals paste with Ctrl+Shift+V. Matched against the whole lower-cased
// wm_class (the Wayland app ID, or the X11 class) or its last dotted part,
// never as a substring: a substring 'st' matched gnome-system-monitor,
// steam and jetbrains-studio, and no entry matched org.gnome.Terminal,
// org.gnome.Ptyxis or org.gnome.Console.
const TERMINAL_APP_IDS = new Set([
    'org.gnome.terminal', 'gnome-terminal-server', 'gnome-terminal',
    'org.gnome.ptyxis', 'org.gnome.ptyxis.devel', 'ptyxis',
    'org.gnome.console', 'org.gnome.console.devel', 'kgx',
    'com.gexperts.tilix', 'tilix', 'kitty', 'alacritty', 'terminator',
    'xterm', 'uxterm', 'org.kde.konsole', 'konsole', 'foot', 'footclient',
    'org.wezfurlong.wezterm', 'wezterm', 'st', 'st-256color', 'sakura',
    'xfce4-terminal', 'mate-terminal', 'lxterminal', 'guake', 'tilda',
    'cool-retro-term', 'com.raggesilver.blackbox', 'com.mitchellh.ghostty',
    'io.elementary.terminal', 'terminology', 'rio',
]);

function _isTerminal(wmClass) {
    const id = (wmClass ?? '').toLowerCase();
    if (!id)
        return false;
    return TERMINAL_APP_IDS.has(id) ||
        TERMINAL_APP_IDS.has(id.slice(id.lastIndexOf('.') + 1));
}

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
        // MetaWindow -> its 'unmanaged' handler id.
        this._hiddenWindows = new Map();
        this._daemonOwner = null;
        this._daemonPid = 0;
        this._deniedSenders = new Set();
        this._virtualKeyboard = null;
        this._clipboardTimeout = null;
        this._readCancellable = null;
        this._readTimeoutId = null;

        this._selection = global.display.get_selection();
        this._ownerChangedId = this._selection.connect(
            'owner-changed',
            this._onOwnerChanged.bind(this)
        );

        // Learn which connection owns the daemon name; only it may call us.
        // Our own bus name is claimed only after that first answer. The
        // daemon pushes SetPaused as soon as the name appears, and a push
        // that arrived while the owner was still unknown was refused and
        // never retried, so incognito silently stopped pausing the
        // extension after every screen unlock (which re-enables us).
        this._busNameId = null;
        this._daemonWatchId = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            DAEMON_BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            (_connection, _name, owner) => {
                this._onDaemonAppeared(owner);
                this._ownBusName();
            },
            () => {
                this._onDaemonVanished();
                this._ownBusName();
            }
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
        this._cancelRead();
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

    _ownBusName() {
        if (this._busNameId || this._destroyed)
            return;
        this._busNameId = Gio.bus_own_name_on_connection(
            Gio.DBus.session,
            OWN_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            null,
            () => console.warn(`clipman: lost the bus name ${OWN_BUS_NAME}`)
        );
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
            // Bounded: a caller that reconnects has a new name each time.
            if (this._deniedSenders.size >= 64)
                this._deniedSenders.clear();
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
        if (this._paused)
            this._cancelRead();
        invocation.return_value(null);
    }

    // ---- Paste -------------------------------------------------------

    _resolveRecipe(mode) {
        if (typeof mode === 'string' && Object.hasOwn(PASTE_RECIPES, mode))
            return PASTE_RECIPES[mode];

        // 'auto': Ctrl+V, or Ctrl+Shift+V when a terminal has focus.
        const focusWin = global.display.get_focus_window();
        return _isTerminal(focusWin?.get_wm_class())
            ? PASTE_RECIPES['ctrl-shift-v'] : PASTE_RECIPES['ctrl-v'];
    }

    _getVirtualKeyboard() {
        if (!this._virtualKeyboard) {
            // Clutter.get_default_backend() was removed in GNOME Shell 51;
            // global.stage.context.get_backend() is its replacement.
            const backend = Clutter.get_default_backend
                ? Clutter.get_default_backend()
                : global.stage.context.get_backend();
            const seat = backend.get_default_seat();
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
        // GTK maps the popup as a new MetaWindow on every show: forget each
        // one when it goes away, instead of holding it until disable().
        if (!this._hiddenWindows.has(metaWin)) {
            this._hiddenWindows.set(metaWin, metaWin.connect('unmanaged',
                () => this._hiddenWindows.delete(metaWin)));
        }
    }

    _showHiddenWindows() {
        for (const [win, handlerId] of this._hiddenWindows) {
            try {
                win.disconnect(handlerId);
                if (win.show_in_window_list)
                    win.show_in_window_list();
            } catch {
                // The window is gone already.
            }
        }
        this._hiddenWindows.clear();
    }

    // ---- Clipboard capture -------------------------------------------

    _onOwnerChanged(_selection, selectionType, selectionSource) {
        if (selectionType !== Meta.SelectionType.SELECTION_CLIPBOARD)
            return;

        // A new copy replaces the one still waiting or being read.
        if (this._clipboardTimeout) {
            GLib.source_remove(this._clipboardTimeout);
            this._clipboardTimeout = null;
        }
        this._cancelRead();
        // Nobody would receive the clip.
        if (this._paused || this._daemonOwner === null)
            return;

        // Wait 150 ms for the new owner to make the content available.
        this._clipboardTimeout = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, 150, () => {
                this._clipboardTimeout = null;
                this._readClipboard(selectionSource);
                return GLib.SOURCE_REMOVE;
            }
        );
    }

    _readClipboard(source) {
        if (!source)
            return;
        const offered = source.get_mimetypes();
        const textTypes = TEXT_MIME_TYPES.filter(t => offered.includes(t));
        if (textTypes.length > 0)
            this._readText(source, textTypes);
        else if (offered.some(t => t.startsWith('image/')))
            this._sendToDaemon('image', '');
    }

    // Read the first offered text type that has content, then send it.
    _readText(source, textTypes) {
        const cancellable = new Gio.Cancellable();
        this._readCancellable = cancellable;
        this._readTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT, READ_TIMEOUT_MS, () => {
                this._readTimeoutId = null;
                this._readCancellable = null;
                cancellable.cancel();
                return GLib.SOURCE_REMOVE;
            }
        );
        const done = data => {
            if (cancellable.is_cancelled() || this._destroyed)
                return;
            this._endRead();
            if (data === null || this._paused)
                return;
            if (data.length === 0) {
                if (textTypes.length > 1)
                    this._readText(source, textTypes.slice(1));
                return;
            }
            // Some X11 apps include a trailing null byte.
            if (data[data.length - 1] === 0)
                data = data.subarray(0, -1);
            const text = new TextDecoder().decode(data);
            if (text)
                this._sendToDaemon('text', text);
        };
        source.read_async(textTypes[0], cancellable, (src, result) => {
            let stream;
            try {
                stream = src.read_finish(result);
            } catch (e) {
                console.debug(`clipman: clipboard read failed: ${e.message}`);
                done(null);
                return;
            }
            this._readChunks(stream, cancellable,
                Gio.MemoryOutputStream.new_resizable(), done);
        });
    }

    // Read the stream in chunks into `into`, then call `done` with the
    // data: null when the read fails, is cancelled or passes the limit (the
    // daemon would drop the clip), so the Shell never holds more than
    // that. The stream is closed at once either way; its pipe must not
    // wait for the garbage collector.
    _readChunks(stream, cancellable, into, done) {
        stream.read_bytes_async(READ_CHUNK_BYTES, GLib.PRIORITY_DEFAULT,
            cancellable, (src, result) => {
                let bytes = null;
                try {
                    bytes = src.read_bytes_finish(result);
                } catch (e) {
                    console.debug(`clipman: clipboard read failed: ${e.message}`);
                }
                const size = bytes ? bytes.get_size() : 0;
                if (bytes !== null && size > 0 &&
                    into.get_data_size() + size <= MAX_TEXT_BYTES) {
                    into.write_bytes(bytes, null);
                    this._readChunks(src, cancellable, into, done);
                    return;
                }
                try {
                    src.close(null);
                } catch (e) {
                    console.debug(`clipman: closing the read failed: ${e.message}`);
                }
                into.close(null);
                done(bytes === null || size > 0
                    ? null : into.steal_as_bytes().get_data() ?? new Uint8Array());
            });
    }

    // Stop the read in progress, if any: its callback then does nothing.
    _cancelRead() {
        const cancellable = this._readCancellable;
        this._endRead();
        cancellable?.cancel();
    }

    _endRead() {
        if (this._readTimeoutId) {
            GLib.source_remove(this._readTimeoutId);
            this._readTimeoutId = null;
        }
        this._readCancellable = null;
    }

    _sendToDaemon(contentType, content) {
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
