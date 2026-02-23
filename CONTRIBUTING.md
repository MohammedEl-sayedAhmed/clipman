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
│   ├── test_database.py        # Database tests (70 tests)
│   ├── test_clipboard_monitor.py  # Monitor tests (58 tests)
│   └── test_window_utils.py    # URL detection & time formatting (22 tests)
├── docs/
│   ├── dark-theme.png          # Screenshot (dark theme)
│   └── light-theme.png         # Screenshot (light theme)
├── com.clipman.Clipman.json    # Flatpak manifest
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

All 180 tests should pass. Tests cover the database layer, clipboard monitor, URL detection, and time formatting — no GTK or D-Bus required.

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

## Submitting Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Run the test suite: `python3 -m unittest discover -s tests`
4. Commit with a clear message describing what and why
5. Push and open a Pull Request

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

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
