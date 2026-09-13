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
│   ├── __init__.py             # i18n/gettext setup; re-exports __version__
│   ├── _version.py             # Single source of truth for __version__
│   ├── app.py                  # Adw.Application lifecycle
│   ├── clipboard_monitor.py    # Event-driven clipboard change handling
│   ├── database.py             # SQLite storage layer
│   ├── dbus_service.py         # D-Bus IPC (toggle, clipboard events)
│   ├── edge_states.py          # 20 declarative StateSpec entries dispatched
│   │                           #   into Adw.StatusPage / Adw.Banner / Adw.AlertDialog
│   ├── keybindings.py          # gsettings helpers for Super+V customization
│   ├── preferences.py          # Adw.Dialog + sidebar (6 panes)
│   ├── snippets_dialog.py      # Adw.NavigationSplitView master-detail snippet editor
│   ├── updates.py              # Anonymous update-check against GitHub Releases
│   ├── window.py               # Adw.ApplicationWindow + Adw.HeaderBar history popup
│   └── style.css               # libadwaita @-token overrides + Catppuccin palette
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
│   └── clipman.pot             # Translation template (226 strings)
├── tests/
│   ├── test_clipboard_monitor.py  # Monitor tests (110 tests)
│   ├── test_database.py        # Database tests (96 tests)
│   ├── test_window.py          # Window, classify & render tests (60 tests)
│   ├── test_updates.py         # Update-check tests (40 tests)
│   ├── test_keybindings.py     # Keybinding-customization tests (32 tests)
│   ├── test_app.py             # Application lifecycle tests (10 tests)
│   ├── test_sensitive.py       # Sensitive-data heuristics (10 tests)
│   ├── test_entry_point.py     # D-Bus mainloop init tests (9 tests)
│   ├── test_shell_bridge.py    # Shell-extension bridge tests (4 tests)
│   ├── test_release_metadata.py  # Packaging-metadata tests (3 tests)
│   └── test_dbus_service.py    # D-Bus service tests (1 test)
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

One-command setup, then the suite exactly as CI runs it:

```bash
scripts/dev-setup.sh      # or: make setup
scripts/dev.sh test       # or: make test
```

`dev-setup.sh` installs the system packages, creates `.venv` and installs the `dev` extras. The venv uses `--system-site-packages`, so the distro's PyGObject and dbus-python bindings are reused and never rebuilt. `dev.sh test` runs pytest under `xvfb-run` with `CLIPMAN_REQUIRE_GTK4=1` (falling back to `unittest` when pytest is not importable); pytest arguments pass through, e.g. `scripts/dev.sh test -k database`.

All 375 tests should pass. GTK 4 is required at test time; a session bus is not. Tests cover the database layer, clipboard monitor, window/classification logic, app lifecycle, keybindings, and the update check. See [docs/development.md](docs/development.md) for the fuller dev setup.

### Lint

```bash
scripts/dev.sh lint       # or: make lint  — ruff + shellcheck
scripts/dev.sh check      # or: make check — lint, then test
```

`lint` runs `ruff check clipman tests scripts clipman.py` and `shellcheck --severity=warning` over `install.sh`, `uninstall.sh`, `launcher.sh`, `scripts/*.sh` and the `.githooks/` scripts, the same scopes as CI; `scripts/dev.sh ruff` and `scripts/dev.sh shellcheck` run either half alone. Ruff is pinned in the `lint` extra so the local version matches CI.

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
- **GTK 4 + libadwaita 1.4+** — the UI is built on `Adw.ApplicationWindow`,
  `Adw.Dialog`, `Adw.NavigationSplitView`, `Adw.ActionRow`,
  `Adw.StatusPage`, `Adw.Banner`, and `Adw.AlertDialog`. Ubuntu 22.04 is no
  longer the floor; 24.04+ is the supported baseline.
- **GNOME Shell extension** — runs inside the compositor; changes require logout/login to take effect
- **No polling** — clipboard detection is event-driven via D-Bus
- **Single-threaded** — all code runs on the GLib main loop

### Dev system packages

`scripts/deps.sh` is the single manifest (apt, dnf, pacman); `scripts/dev-setup.sh` installs from it. To use it by hand:

```bash
scripts/deps.sh --dev --print      # the list for this host's package manager
scripts/deps.sh --dev --install    # install what is missing (sudo when needed)
```

See [docs/development.md](docs/development.md) for the full setup.

### i18n (Translations)

User-visible strings are wrapped with `_()` for translation support:

```python
from gettext import gettext as _

label.set_text(_("Search..."))
status.set_text(_("{count} items").format(count=total))
```

- Import `_` from the standard library, not from `clipman`. The package
  root already binds the text domain, and `from clipman import _` inside
  a submodule is a cycle that CodeQL reports as `py/cyclic-import`.
- Wrap every user-visible string with `_()`
- Use `.format()` for strings with variables — keep placeholders inside the translatable string
- Translation template: `po/clipman.pot`; regenerate it with `scripts/dev.sh i18n`
- Source file list: `po/POTFILES.in` — add a file when it grows its first `_()`
- Adding a new translation: see [docs/translating.md](docs/translating.md).

### CSS Theming

The UI stylesheet lives in `clipman/style.css`. With the move to
GTK 4 + libadwaita, theming is layered:

1. **libadwaita `@named-color` tokens** (e.g. `@accent_color`,
   `@window_bg_color`, `@card_bg_color`) carry the bulk of the
   palette. The stylesheet redefines these tokens so every Adw
   widget — `Adw.ActionRow`, `Adw.Dialog`,
   `Adw.HeaderBar`, `Adw.Banner`, etc. — picks up the Catppuccin
   Mocha (dark) or warm-stone (light) palette automatically without
   per-widget rules.
2. **Catppuccin palette overlay**: light- and dark-variant
   selectors (`window.dark @define-color …` / `window.light …`)
   write the chosen palette into the `@named-color` slots at theme
   switch time.
3. **`string.Template` substitution** is still used for the
   runtime-tunable knobs (font size, opacity) — variables like
   `${font_size}px` are substituted before the CSS is handed to
   `Gtk.CssProvider.load_from_string()`.

- Prefer overriding `@named-color` tokens over writing per-widget
  CSS — the Adw widgets honour the tokens consistently.
- Use `${variable}` when followed by letters/digits (e.g.,
  `${font_size}px`) for runtime substitution.
- Never commit `clipman/style.css` with `$variable` placeholders
  substituted — the runtime template substitution would then
  double-substitute and the daemon would fail to load the CSS.

## Submitting Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Run the checks: `scripts/dev.sh check` (lint, then the test suite)
4. Commit with a clear message describing what and why
5. Push and open a Pull Request

### Optional: local git hooks (maintainers)

The repo ships opt-in local hooks under [`.githooks/`](.githooks/) that
guard against AI-tool footprints and wrong-account commits. They are
**not required** to contribute; CI does not run them.
`scripts/dev-setup.sh` installs them when nothing else owns
`core.hooksPath`. To install (or re-install) them by hand:

```sh
scripts/install-hooks.sh
```

If `core.hooksPath` already points elsewhere the script asks before
replacing it; pass `--replace` to skip the prompt. Without a terminal it
never blocks on stdin — it exits 1 with that hint instead.
`scripts/dev.sh hooks-test` runs the hooks' own test corpus. See
[docs/hooks.md](docs/hooks.md) for what each hook checks and how to opt
out.

## How a PR gets reviewed

- **Timeline.** A single maintainer reviews PRs (see GOVERNANCE.md). Typical first response within a week.
- **What reviewers check.**
  - Tests pass: `scripts/dev.sh test` (the same command CI runs).
  - `scripts/dev.sh ruff` clean (`ruff check clipman tests scripts clipman.py`).
  - `scripts/dev.sh shellcheck` clean if any shell script was touched (`--severity=warning` over `install.sh`, `uninstall.sh`, `launcher.sh`, `scripts/*.sh` and the `.githooks/` scripts).
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

- [ ] `scripts/dev.sh test` passes locally (375 tests)
- [ ] `scripts/dev.sh ruff` is clean
- [ ] `scripts/dev.sh shellcheck` is clean if any shell script was touched
- [ ] `CHANGELOG.md` `[Unreleased]` updated for user-visible changes
- [ ] ADR added under `docs/adr/` for substantive architectural decisions
- [ ] `extension/metadata.json` `version` integer bumped if the D-Bus contract changed (per [ADR 0005](docs/adr/0005-paste-mode-as-dbus-arg.md))
- [ ] PR description fills the template (`.github/pull_request_template.md`)

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
