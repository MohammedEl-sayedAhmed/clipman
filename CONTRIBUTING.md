# Contributing to Clipman

Thank you for your interest in contributing to Clipman!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/clipman.git`
3. Install dependencies: `./install.sh`
4. Log out and back in to activate the GNOME Shell extension
5. Start the daemon: `systemctl --user start clipman.service`

## Development

### Project Structure

```
clipman/
├── clipman.py                  # Entry point (start daemon / toggle popup)
├── clipman/
│   ├── __init__.py             # i18n/gettext setup
│   ├── app.py                  # GTK Application lifecycle
│   ├── clipboard_monitor.py    # Event-driven clipboard change handling
│   ├── database.py             # SQLite storage layer
│   ├── dbus_service.py         # D-Bus IPC (toggle, clipboard events)
│   ├── window.py               # GTK3 popup window UI and event handlers
│   └── style.css               # CSS theme template (Catppuccin, $variable syntax)
├── extension/
│   ├── extension.js            # GNOME Shell extension (clipboard detection, paste)
│   └── metadata.json           # Extension metadata
├── data/
│   ├── com.clipman.Clipman.desktop
│   ├── com.clipman.Clipman.svg
│   ├── com.clipman.Clipman.metainfo.xml
│   └── clipman.service         # Systemd user service
├── po/
│   ├── POTFILES.in             # Files with translatable strings
│   └── clipman.pot             # Translation template (70 strings)
├── tests/
│   ├── test_database.py        # Database tests (90 tests)
│   ├── test_clipboard_monitor.py  # Monitor tests (105 tests)
│   ├── test_entry_point.py     # D-Bus mainloop init tests (3 tests)
│   └── test_window_utils.py    # URL detection & time formatting (28 tests)
├── docs/
│   ├── dark-theme.png          # Screenshot (dark theme)
│   └── light-theme.png         # Screenshot (light theme)
├── snap/
│   └── snapcraft.yaml          # Snap packaging
├── launcher.sh                 # Environment wrapper for snap terminals
├── install.sh
└── uninstall.sh
```

### Running Tests

```bash
python3 -m unittest discover -s tests
```

All 303 tests should pass. The suite is stdlib-only — no GTK or D-Bus required at test time. Tests cover the database layer, clipboard monitor, URL detection, and time formatting. See [docs/development.md](docs/development.md) for the fuller dev setup.

### Lint

```bash
ruff check clipman tests
shellcheck --severity=warning install.sh uninstall.sh launcher.sh
```

- Ruff config lives in `pyproject.toml`. The per-file `E402` ignores in `clipman/app.py` and `clipman/window.py` are intentional — `gi.require_version()` legitimately must precede the `from gi.repository import ...` calls.
- Run shellcheck whenever you touch a shell script.
- See [docs/development.md](docs/development.md) for the fuller setup.

### D-Bus debugging

The daemon owns `com.clipman.Daemon` on the session bus; the
GNOME Shell extension owns `org.gnome.Shell.Extensions.clipman`.

Confirm both services are live:

    busctl --user list | grep -E 'com.clipman.Daemon|org.gnome.Shell.Extensions.clipman'

Introspect or call them with `gdbus`:

    gdbus introspect --session --dest com.clipman.Daemon \
        --object-path /com/clipman/Daemon

    gdbus call --session --dest com.clipman.Daemon \
        --object-path /com/clipman/Daemon \
        --method com.clipman.Daemon.Toggle

`docs/development.md` covers the rest.

### Key Constraints

- **Wayland only** — no X11-specific APIs in the daemon
- **GTK3** — the UI uses GTK3 (not GTK4) for Ubuntu 22.04+ compatibility
- **GNOME Shell extension** — runs inside the compositor; changes require logout/login to take effect
- **No polling** — clipboard detection is event-driven via D-Bus
- **Single-threaded** — all code runs on the GLib main loop

### i18n (Translations)

All user-visible strings in `window.py` are wrapped with `_()` for translation support:

```python
from clipman import _

label.set_text(_("Search..."))
status.set_text(_("{count} items").format(count=total))
```

- Import `_` from `clipman` (set up in `__init__.py`)
- Wrap every user-visible string with `_()`
- Use `.format()` for strings with variables — keep placeholders inside the translatable string
- Translation template: `po/clipman.pot`
- Source file list: `po/POTFILES.in`
- Adding a new translation: see [docs/translating.md](docs/translating.md).

### CSS Theming

The UI stylesheet lives in `clipman/style.css` as a `string.Template` file:

```css
.entry-row {
    background-color: $bg_surface0;
    font-size: ${font_size}px;
}
```

- Theme colors use `$variable` syntax (e.g., `$bg_crust`, `$text_primary`, `$accent`)
- Use `${variable}` when followed by letters/digits (e.g., `${font_size}px`)
- Variables are substituted at runtime from the theme dictionary in `window.py`
- Do **not** use CSS custom properties (`var(--name)`) — GTK3's CSS engine does not support them
- Never commit `clipman/style.css` with `$variable` placeholders substituted — the runtime template substitution would then double-substitute and the daemon would fail to load the CSS.

## Submitting Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Run the test suite: `python3 -m unittest discover -s tests`
4. Commit with a clear message describing what and why
5. Push and open a Pull Request

## How a PR gets reviewed

- **Timeline.** A single maintainer reviews PRs (see GOVERNANCE.md). Typical first response within a week.
- **What reviewers check.**
  - Tests pass: `python3 -m unittest discover -s tests`.
  - `ruff check clipman tests` clean.
  - `shellcheck --severity=warning install.sh uninstall.sh launcher.sh` clean if any shell script was touched.
  - User-visible change → `CHANGELOG.md` `[Unreleased]` entry.
  - Substantive architectural decision → ADR added under `docs/adr/` per ADR 0001.
  - D-Bus contract change (signature, new method, new arg) → `extension/metadata.json` `version` integer bumped per [ADR 0005](docs/adr/0005-paste-mode-as-dbus-arg.md).
- **Auto-labeling.** Path-based `area:*` and `distribution:*` labels are applied automatically by `.github/workflows/labeler.yml`; type / priority / status labels are set manually.
- **Dependabot PRs.** PRs labeled `dependencies` by Dependabot for `pip` and `github-actions` are still reviewed but typically merge quickly once CI is green.
- **GitHub Advanced Security threads.** Resolve every `github-advanced-security` finding before merge — reply on the thread, resolve, and dismiss the alert if it's a false positive.

## Reporting Issues

When filing a bug report, please include:

- Ubuntu version and GNOME Shell version (`gnome-shell --version`)
- Wayland or X11 session (`echo $XDG_SESSION_TYPE`)
- Steps to reproduce
- Expected vs actual behavior
- GNOME Shell logs if relevant: `journalctl --user -b -g clipman`

## Code Style

- Python: follow existing patterns in the codebase
- JavaScript (extension): ES module syntax, GNOME Shell conventions
- No unnecessary abstractions — keep it simple
- Prefer specific exception types over bare `except`

## Definition of Done

- [ ] `python3 -m unittest discover -s tests` passes locally (303 tests)
- [ ] `ruff check clipman tests` is clean
- [ ] `shellcheck --severity=warning install.sh uninstall.sh launcher.sh` is clean if any shell script was touched
- [ ] `CHANGELOG.md` `[Unreleased]` updated for user-visible changes
- [ ] ADR added under `docs/adr/` for substantive architectural decisions
- [ ] `extension/metadata.json` `version` integer bumped if the D-Bus contract changed (per [ADR 0005](docs/adr/0005-paste-mode-as-dbus-arg.md))
- [ ] PR description fills the template (`.github/pull_request_template.md`)

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
