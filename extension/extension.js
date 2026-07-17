import St from 'gi://St';
import Meta from 'gi://Meta';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// The popup's Wayland app_id / wm_class (clipman/app.py application_id).
// Used to keep our ephemeral popup out of alt-tab and the dash, like Win+V.
const CLIPMAN_WM_CLASS = 'com.clipman.Clipman';

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

        // Win+V parity: keep the ephemeral popup out of alt-tab and the
        // dash. There is no writable skip-taskbar API before GNOME 49, so
        // we monkey-patch the two JS entry points that build those lists
        // and filter our window out. On 49+ the daemon-side move loop uses
        // the real Meta.Window.hide_from_window_list() instead (see below).
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

        // The dash/dock (incl. Ubuntu Dock / Dash-to-Dock) lists running
        // apps from AppSystem.get_running(). Our popup has no installed
        // .desktop, so the Shell tracks it as a window-backed app that
        // shows up there. Filter that app out of the running list so the
        // ephemeral popup never appears in the dock — Win+V parity. We use
        // the ORIGINAL get_windows here (the patched one above hides
        // clipman windows, which would make this app look window-less).
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

    disable() {
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
                // Remember who had focus BEFORE we steal it below, so paste
                // can hand focus back to the real target (see
                // RestorePreviousFocus). Capture now: activate() has not run
                // yet, so the focus window is still the user's app.
                const focused = global.display.get_focus_window();
                if (focused && !_isClipmanWindow(focused))
                    this._prevFocus = focused;
                // GNOME 49+: the supported way to drop the popup from the
                // dash AND alt-tab in one call (no-op / undefined before 49,
                // where the enable() list overrides handle it instead).
                if (metaWin.hide_from_window_list)
                    metaWin.hide_from_window_list();
                // Give the popup real input focus. A background D-Bus
                // daemon's window is mapped WITHOUT focus by Mutter's
                // focus-stealing prevention, so its buttons/keys are inert
                // until focused. The Shell has the privilege to focus it;
                // GTK's present() does not. This is what makes Win+V-style
                // click/type/dismiss work. On hide, focus returns to the
                // previously-active window, so wtype paste still lands there.
                metaWin.activate(global.get_current_time());
                break;
            }
        }
    }

    RestorePreviousFocus() {
        // The popup held input focus (so its buttons/keys worked); before
        // the daemon fires the paste keystroke it must hand focus back to
        // the window the user came from, otherwise Ctrl+V lands on nothing.
        // Only the Shell can refocus another window on Wayland, so the
        // daemon calls this after hiding the popup and just before wtype.
        const prev = this._prevFocus;
        this._prevFocus = null;
        if (prev && !_isClipmanWindow(prev)) {
            try {
                prev.activate(global.get_current_time());
            } catch {
                // The target window may have closed meanwhile; the paste
                // keystroke then goes to whatever is now focused.
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
