// Test only: turns on unsafe mode in the throwaway headless Shell of
// tests/e2e, so the tests can use org.gnome.Shell.Eval.
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class E2eProbe extends Extension {
    enable() {
        global.context.unsafe_mode = true;
    }

    disable() {
        global.context.unsafe_mode = false;
    }
}
