# Development guide

A walkthrough for hacking on Clipman locally — building from source,
running the test suite, debugging the daemon and the GNOME Shell
extension.

## Source layout

See the **Project structure** block at the bottom of `README.md` for
the canonical map. Two halves matter for development:

- **Python daemon** under `clipman/` (entry point: `clipman.py`).
- **GNOME Shell extension** under `extension/` — JavaScript, runs
  inside GNOME Shell's gjs process.

## Prerequisites

System packages (Ubuntu/Debian — Ubuntu 24.04+ recommended for
libadwaita 1.4):

```bash
sudo apt-get install -y \
    python3 python3-gi python3-dbus \
    gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0 \
    wl-clipboard libcairo2-dev libgirepository-2.0-dev \
    gnome-shell-extensions
```

Fedora equivalents:

```bash
sudo dnf install -y \
    python3-gobject python3-dbus gtk4 libadwaita \
    wl-clipboard cairo-devel gobject-introspection-devel \
    gnome-extensions-app
```

A virtualenv is optional but recommended for lint/test tooling:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install ruff
```

PyGObject is imported through the system path — don't `pip install
PyGObject` inside the venv, it'll diverge from the system GIR
typelibs.

## Running from source

```bash
git clone git@github.com:MohammedEl-sayedAhmed/clipman.git
cd clipman
./install.sh          # registers the keybinding + autostart + extension
python3 clipman.py    # daemon foreground; Ctrl+C to stop
```

Pop the popup any time with `Super+V` (or run
`python3 clipman.py toggle` from another terminal).

`install.sh` is idempotent — re-run it after changing the extension
to refresh `~/.local/share/gnome-shell/extensions/clipman@clipman.com`.

## Running tests

```bash
python3 -m unittest discover -s tests
```

The full suite (~265 tests) hits the actual SQLite layer, mocks
clipboard subprocesses, and exercises the keybinding parser. Tests
require the system `python3-gi` package (the project's CI matrix
covers Python 3.10–3.12 on `ubuntu-24.04`).

Targeted runs:

```bash
python3 -m unittest tests.test_keybindings
python3 -m unittest tests.test_database.TestClipboardDB.test_add_text_entry
```

## Lint

```bash
ruff check clipman tests
```

Configuration lives in `pyproject.toml`. The two per-file ignores for
`E402` in `clipman/app.py` and `clipman/window.py` are intentional —
`gi.require_version()` legitimately must precede `from gi.repository
import ...`.

Shell scripts use `shellcheck --severity=warning`:

```bash
shellcheck --severity=warning install.sh uninstall.sh launcher.sh
```

## Debugging

### Daemon

Run it in the foreground to see `print()` output and Python tracebacks:

```bash
python3 clipman.py
```

Once installed as a systemd user service:

```bash
journalctl --user -u clipman -f
```

The database lives at `~/.local/share/clipman/clipman.db` — open it
with `sqlite3` if you need to inspect history or settings:

```bash
sqlite3 ~/.local/share/clipman/clipman.db
sqlite> SELECT key, value FROM settings;
```

### Extension

GNOME Shell logs every extension exception to the systemd journal:

```bash
journalctl /usr/bin/gnome-shell -f
```

To reload the extension without logging out:

- Wayland: log out and back in (Shell restart isn't supported under
  Wayland).
- X11: `Alt+F2`, type `r`, Enter.

When iterating on `extension/extension.js`, copy it into
`~/.local/share/gnome-shell/extensions/clipman@clipman.com/extension.js`
and reload the Shell. `install.sh` does the copy step too.

## D-Bus surfaces

The daemon owns `com.clipman.Daemon` on the session bus; the extension
owns `org.gnome.Shell.Extensions.clipman`. Inspect them with:

```bash
gdbus introspect --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon
gdbus introspect --session --dest org.gnome.Shell.Extensions.clipman \
    --object-path /org/gnome/Shell/Extensions/clipman
```

Manually trigger the popup:

```bash
gdbus call --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon \
    --method com.clipman.Daemon.Toggle
```

## Useful environment variables

- `CLIPMAN_DATA_DIR` — override the default `~/.local/share/clipman/`.
- `SNAP` (set by the snap runtime) — turns on the snap-aware code
  paths in `clipman/app.py` and skips `wl-paste --watch` (it can't
  see the host clipboard under strict confinement).
- `FLATPAK_ID` — flatpak install kind detection.

## Where to read next

- `docs/adr/` — design decisions (CodeQL ratchet, OIDC publishing,
  D-Bus mode arg, branch-protection posture).
- `docs/releases/README.md` — how a release is cut.
- `CONTRIBUTING.md` — PR workflow, commit style, and the issue
  templates this repo expects.
