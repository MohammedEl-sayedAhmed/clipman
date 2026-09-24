/* Shared theme handling for every design-workspace page.
 *
 * Convention: every page in docs/design/* sets <body class="theme-dark">
 * (the default, as on the marketing page) and shows two toggle buttons
 * inside .theme-toggle. The marketing page at docs/index.html uses
 * <html data-theme="dark|light"> and the same localStorage key. This file:
 *
 *   1. On load, picks the theme: ?theme= when the URL has it (the
 *      marketing page passes it to the popup mockup it embeds), else the
 *      shared localStorage key ('clipman-theme'), else the page's own
 *      class. It always applies it, preserving any other classes on
 *      <body> (e.g. .embed when this page is iframed), and always marks
 *      the matching toggle button active. Before, it did both only when
 *      a theme was saved, so a first visit showed the light page with
 *      "Dark" marked active.
 *   2. Listens for clicks on the toggle buttons and writes back to the
 *      same localStorage key so the next navigation (and the iframe host)
 *      picks up the preference.
 *   3. Follows the theme of the page that embeds this one, and of other
 *      tabs.
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

    // The page's theme toggle, and any mockup control marked
    // data-mirrors-theme (the Preferences "Color scheme" row), select the
    // button named after the theme.
    function syncTogglesUI(theme) {
        const wantLabel = (theme === 'light') ? 'light' : 'dark';
        document.querySelectorAll(
            '.theme-toggle button, [data-mirrors-theme] button'
        ).forEach(btn => {
            const isMatch = (btn.textContent || '').trim().toLowerCase() === wantLabel;
            btn.classList.toggle('active', isMatch);
        });
    }

    // 1. Apply the theme on load, and mark its button.
    const param = new URLSearchParams(location.search).get('theme');
    const pageTheme = document.body.classList.contains('theme-light')
        ? 'light' : 'dark';
    applyToBody((param === 'light' || param === 'dark')
        ? param : (readSaved() || pageTheme));

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

    // The embedding page posts its theme when it changes. Only messages
    // from this origin count (and the file:// case used during local
    // preview), which also satisfies CodeQL's js/missing-origin-check.
    window.addEventListener('message', (e) => {
        if (!e || !e.data) return;
        const sameOrigin = (e.origin === window.location.origin) || (e.origin === 'null');
        if (!sameOrigin || e.data.type !== 'clipman-theme') return;
        const v = e.data.value;
        if (v === 'light' || v === 'dark') applyToBody(v);
    });
})();
