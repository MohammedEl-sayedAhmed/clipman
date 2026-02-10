import St from 'gi://St';
import Meta from 'gi://Meta';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class ClipmanExtension extends Extension {
    enable() {
        this._selection = global.display.get_selection();
        this._ownerChangedId = this._selection.connect(
            'owner-changed',
            this._onOwnerChanged.bind(this)
        );
    }

    disable() {
        if (this._ownerChangedId) {
            this._selection.disconnect(this._ownerChangedId);
            this._ownerChangedId = null;
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
