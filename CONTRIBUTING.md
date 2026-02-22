# Contributing to Clipman

Thank you for your interest in contributing to Clipman!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/clipman.git`
3. Install dependencies: `./install.sh`
4. Log out and back in to activate the GNOME Shell extension
5. Run the daemon: `python3 clipman.py`

## Development

### Project Structure

```
clipman/
  clipman.py            # Entry point
  clipman/
    app.py              # GTK Application
    window.py           # UI (GTK3 window, CSS, event handlers)
    database.py         # SQLite storage layer
    clipboard_monitor.py# Clipboard change handling
    dbus_service.py     # D-Bus IPC
  extension/
    extension.js        # GNOME Shell extension (clipboard detection, paste simulation)
    metadata.json       # Extension metadata
  tests/
    test_database.py    # Database tests
    test_clipboard_monitor.py  # Monitor tests
```

### Running Tests

```bash
python3 -m unittest discover -s tests
```

### Key Constraints

- **Wayland only** — no X11-specific APIs in the daemon
- **GTK3** — the UI uses GTK3 (not GTK4) for Ubuntu 22.04+ compatibility
- **GNOME Shell extension** — runs inside the compositor; changes require logout/login to take effect
- **No polling** — clipboard detection is event-driven via D-Bus
- **Single-threaded** — all code runs on the GLib main loop

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
