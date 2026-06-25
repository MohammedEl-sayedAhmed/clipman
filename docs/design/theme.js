/* Shared theme persistence for every design-workspace page.
 *
 * Convention: every page in docs/design/* sets <body class="theme-dark"> or
 * "theme-light" and shows two toggle buttons inside .theme-toggle. The
 * marketing page at docs/index.html uses <html data-theme="dark|light"> and
 * the same localStorage key. This file:
 *
 *   1. On load, reads the shared localStorage key ('clipman-theme') and
 *      applies the resulting class to <body>, preserving any other classes
 *      that were on it (e.g. .embed when this page is iframed).
 *   2. Synchronises the .active state of the two .theme-toggle buttons so
 *      the UI reflects the active theme.
 *   3. Listens for clicks on the toggle buttons and writes back to the
 *      same localStorage key so the next navigation (and the iframe host)
 *      picks up the preference.
 *
 * Loading via <script src="theme.js" defer> at the END of the page means
 * none of the page's own inline scripts need to know about persistence —
 * they keep flipping the body class as before, and this file syncs storage
 * after each toggle.
 */
(function () {
    'use strict';
    const KEY = 'clipman-theme';

    function readSaved() {
        try {
            const v = localStorage.getItem(KEY);
            return (v === 'light' || v === 'dark') ? v : null;
        } catch (_) { return null; }
    }
    function writeSaved(v) {
        try { localStorage.setItem(KEY, v); } catch (_) { /* private mode */ }
    }

    function applyToBody(theme) {
        const wantClass = (theme === 'light') ? 'theme-light' : 'theme-dark';
        const oldThemeRegex = /\btheme-(?:dark|light)\b/g;
        const cur = document.body.className;
        const next = cur.replace(oldThemeRegex, '').trim() + ' ' + wantClass;
        document.body.className = next.trim();
        syncTogglesUI(theme);
    }

    function syncTogglesUI(theme) {
        const wantLabel = (theme === 'light') ? 'light' : 'dark';
        document.querySelectorAll('.theme-toggle button').forEach(btn => {
            const isMatch = (btn.textContent || '').trim().toLowerCase() === wantLabel;
            btn.classList.toggle('active', isMatch);
        });
    }

    // 1. Apply persisted theme on load (before anything visible flashes).
    const saved = readSaved();
    if (saved) applyToBody(saved);

    // 2. Intercept toggle clicks so we ALSO write the value back to storage.
    //    Page-specific onclick handlers still run and update the body class —
    //    we just record their decision in the shared key.
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.theme-toggle button');
        if (!btn) return;
        // Defer one tick so the page's own handler runs first, then we read
        // whichever theme class it ended up applying.
        setTimeout(() => {
            const v = document.body.classList.contains('theme-light') ? 'light' : 'dark';
            writeSaved(v);
            syncTogglesUI(v);
        }, 0);
    });

    // 3. Cross-tab sync — if another tab/iframe changes the theme, follow.
    window.addEventListener('storage', (e) => {
        if (e.key === KEY && (e.newValue === 'light' || e.newValue === 'dark')) {
            applyToBody(e.newValue);
        }
    });
})();
