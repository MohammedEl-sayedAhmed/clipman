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

Ubuntu 24.04+ is the baseline (libadwaita 1.4); the same scripts know
the Fedora (dnf) and Arch (pacman) package names. One command installs
the system packages, creates `.venv`, installs the dev extras and the
git hooks:

```bash
scripts/dev-setup.sh      # or: make setup
```

The venv is created with `--system-site-packages`, so the distro's
PyGObject and dbus-python bindings are reused and never rebuilt
against a different GIR stack. Re-running the script is safe; it skips
what is already in place. If it cannot `sudo` without a password it
prints the exact package-manager command and carries on.

The venv step needs PyPI; set `CLIPMAN_NO_NETWORK=1` to skip it and
install the extras later. With a distro PyGObject older than 3.46, or
a non-distro interpreter, pip builds PyGObject from source, which also
needs a C compiler and GLib 2.80.


`scripts/deps.sh` is the single source of truth for the system package
lists (`runtime`, `test`, `lint` sets). `install.sh` and CI read it
too, so there is no second copy to keep in sync:

```bash
scripts/deps.sh --runtime --print    # what install.sh installs
scripts/deps.sh --dev --check        # what is missing for development
scripts/deps.sh --dev --install      # install it (sudo when needed)
```

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
scripts/dev.sh test                  # or: make test
scripts/dev.sh test -k database      # or: make test ARGS="-k database"
```

This is the exact command CI runs: pytest under `xvfb-run -a` with
`CLIPMAN_REQUIRE_GTK4=1`, so a missing GTK 4 fails the widget tests
instead of skipping them. When pytest is not importable it falls back
to `unittest discover -s tests`. The interpreter is `$CLIPMAN_PYTHON`,
else `.venv/bin/python`, else `python3`.

The full suite (331 tests) hits the actual SQLite layer, mocks
clipboard subprocesses, and exercises the keybinding parser. The CI
matrix covers Python 3.10–3.12 on `ubuntu-24.04`.

Targeted runs (pytest syntax):

```bash
scripts/dev.sh test tests/test_keybindings.py
scripts/dev.sh test tests/test_database.py::TestClipboardDB::test_add_text_entry
```

## Lint

```bash
scripts/dev.sh lint                  # or: make lint  — ruff + shellcheck
scripts/dev.sh check                 # or: make check — lint, then test
```

`lint` runs `ruff check clipman tests` and
`shellcheck --severity=warning install.sh uninstall.sh launcher.sh scripts/*.sh`,
the same scopes CI uses; `scripts/dev.sh ruff` and
`scripts/dev.sh shellcheck` run either half alone. Ruff is pinned in
the `lint` extra so the local version matches CI.

Configuration lives in `pyproject.toml`. The two per-file ignores for
`E402` in `clipman/app.py` and `clipman/window.py` are intentional —
`gi.require_version()` legitimately must precede `from gi.repository
import ...`.

Headless screenshots of the real window and preferences:

```bash
scripts/dev.sh screenshot --out /tmp/clipman.png
# or: make screenshot ARGS="--out /tmp/clipman.png"
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
