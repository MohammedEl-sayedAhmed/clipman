<div align="center">

<img src="docs/logo.svg" alt="Clipman logo" width="128" height="128">

# Clipman

**A clipboard history manager for Ubuntu/GNOME on Wayland**

Like Windows `Win+V` — but for Linux.

[![Get it from the Snap Store](https://snapcraft.io/en/dark/install.svg)](https://snapcraft.io/clipman)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/MohammedEl-sayedAhmed/clipman/test.yml?branch=main&label=tests)](https://github.com/MohammedEl-sayedAhmed/clipman/actions)
[![GitHub Stars](https://img.shields.io/github/stars/MohammedEl-sayedAhmed/clipman?style=flat&logo=github&label=Stars)](https://github.com/MohammedEl-sayedAhmed/clipman/stargazers)
[![GitHub Downloads](https://img.shields.io/github/downloads/MohammedEl-sayedAhmed/clipman/total?logo=github&label=Downloads)](https://github.com/MohammedEl-sayedAhmed/clipman/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04+-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com)
[![GNOME](https://img.shields.io/badge/GNOME-46--48-4A86CF?logo=gnome&logoColor=white)](https://gnome.org)
[![Wayland](https://img.shields.io/badge/Wayland-native-yellow)](https://wayland.freedesktop.org)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyPI](https://img.shields.io/pypi/v/clipman-clipboard?label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/clipman-clipboard/)
[![PyPI Downloads](https://img.shields.io/pepy/dt/clipman-clipboard?label=PyPI%20Downloads&logo=pypi&logoColor=white)](https://pepy.tech/project/clipman-clipboard)
[![GNOME Extensions](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fextensions.gnome.org%2Fextension-info%2F%3Fpk%3D9407&query=%24.downloads&label=EGO%20Downloads&logo=gnome&logoColor=white&color=4A86CF)](https://extensions.gnome.org/extension/9407/clipman-clipboard-monitor/)
[![AUR](https://img.shields.io/aur/version/clipman-clipboard?label=AUR&logo=archlinux&logoColor=white)](https://aur.archlinux.org/packages/clipman-clipboard)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/MohammedEl-sayedAhmed?label=Sponsors&logo=github)](https://github.com/sponsors/MohammedEl-sayedAhmed)
[![Donate](https://img.shields.io/badge/Donate-PayPal-0070BA?logo=paypal&logoColor=white)](https://www.paypal.com/paypalme/mohammedelsayedammar)
[![GitHub Discussions](https://img.shields.io/github/discussions/MohammedEl-sayedAhmed/clipman?label=Discussions&logo=github)](https://github.com/MohammedEl-sayedAhmed/clipman/discussions)
[![Project Page](https://img.shields.io/badge/Project_Page-clipman-cba6f7?logo=googlechrome&logoColor=white)](https://mohammedel-sayedahmed.github.io/clipman/)

---

Press **Super+V** to view your clipboard history, search entries, pin favorites, and instantly paste previous copies.

<br>

<img src="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/dark-theme.png" alt="Dark theme" width="320">&nbsp;&nbsp;<img src="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/light-theme.png" alt="Light theme" width="320">

<br>

<sub><i>Above: the shipped GTK 4 + libadwaita popup. The full settings surface is a sidebar <code>Adw.Dialog</code>, the snippets editor is an <code>Adw.NavigationSplitView</code> dialog, and the 19 edge states (empty, no-results, incognito, sensitive-cleared, first-run, errors…) render as Adwaita <code>StatusPage</code> / <code>Banner</code> / <code>AlertDialog</code> with a shared Catppuccin overlay. <a href="https://mohammedel-sayedahmed.github.io/clipman/#design">Browse the mockups</a> · <a href="https://mohammedel-sayedahmed.github.io/clipman/">project page</a>.</i></sub>

</div>

---

Clipman is a **Wayland-native** clipboard manager built on a GNOME Shell extension — no polling, no subprocesses, no screen flicker. It detects clipboard changes through `Meta.Selection` signals and communicates over D-Bus, making it fundamentally different from tools that rely on `wl-paste --watch` or timer-based polling. Privacy is built in: incognito mode, automatic sensitive data detection with 30-second auto-clear, and restrictive file permissions. The entire app is Python + GTK 4 + libadwaita — no Electron, no heavy frameworks.

---

## Features

### Clipboard

- **Text and image support** — stores both content types with SHA256 deduplication
- **Full-text search** — instantly filter history by content
- **Pin favorites** — keep important entries permanently, exempt from pruning
- **Filter tabs** — switch between All, Text, Images, and Snippets views
- **Snippet templates** — save reusable text blocks for quick pasting
- **Date grouping** — entries organized into Today, Yesterday, and Older sections
- **Inline editing** — edit any text entry directly from the history
- **Preview expansion** — expand long entries inline to see full content
- **URL detection** — auto-detected with a one-click open button
- **Character count** — text entries show a character count badge
- **Image preview** — hover for a larger tooltip preview
- **Auto-pruning** — history capped at a configurable limit (pinned entries exempt)

### Keyboard

| Key | Action |
|-----|--------|
| <kbd>Super</kbd> + <kbd>V</kbd> | Toggle the popup |
| <kbd>Arrow</kbd> keys | Navigate entries |
| <kbd>Enter</kbd> | Paste selected entry |
| <kbd>Shift</kbd> + <kbd>Enter</kbd> | Copy without pasting |
| <kbd>P</kbd> | Pin / unpin selected entry |
| <kbd>Delete</kbd> | Delete selected entry |
| <kbd>Escape</kbd> | Close popup |

### Appearance

- **Dark and light themes** — Catppuccin Mocha and Catppuccin Latte
- **Font customization** — adjustable size (8–20px) and 6 color presets (Default, Green, Peach, Mauve, Pink, Teal)
- **Window opacity** — configurable transparency from 30% to 100%

### Privacy and Security

- **Incognito mode** — pause clipboard recording entirely
- **Sensitive data detection** — tokens and passwords auto-detected and cleared after 30 seconds
- **Restrictive permissions** — data directory `0o700`, image files `0o600`
- **Path traversal protection** — all image paths validated before file operations
- **Backup validation** — imported databases checked for schema integrity and sanitized
- **Parameterized SQL** — no injection vectors
- **No shell execution** — all subprocesses use argument lists, never `shell=True`
- **Update notifications without telemetry** — when enabled, the daemon does a single anonymous `GET` to `api.github.com/repos/.../releases/latest` once per day (no body, no params, no cookies, no identifiers). Default ON for source / PyPI / AUR installs, OFF for Snap and Flatpak (they auto-refresh). Settings → Updates to toggle. See [ADR 0007](docs/adr/0007-in-app-update-notifications.md).

### Integration

- **Terminal-aware paste** — sends <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd> in terminal emulators, <kbd>Ctrl</kbd>+<kbd>V</kbd> elsewhere
- **XWayland support** — clipboard detection for VSCode, Electron, and other XWayland apps via MIME type fallback
- **Systemd autostart** — runs as a background daemon, auto-restarts on crash
- **Backup and restore** — export and import your clipboard database from settings
- **GNOME Shell extension** — native clipboard monitoring with zero overhead

### Performance

- **Zero polling** — event-driven via `Meta.Selection` signals and D-Bus
- **SHA256 deduplication** — copying the same content bumps it to the top without creating duplicates
- **Configurable history** — 50 to 5,000 entries
- **Lightweight** — Python + GTK 4 + libadwaita, no Electron or heavy frameworks

## Requirements

- Ubuntu 24.04+ with GNOME 46–48 and Wayland
- Python 3.10+
- GTK 4 + libadwaita 1.4+

> Dependencies are installed automatically by the install script.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/MohammedEl-sayedAhmed/clipman.git
cd clipman

# Install dependencies, extension, keybinding, systemd service, and autostart
./install.sh

# Log out and back in to activate the GNOME Shell extension

# Start the daemon (runs automatically on next login)
systemctl --user start clipman.service
```

The systemd service auto-restarts on crash and starts automatically on login.

> If you cloned the repo and Clipman is useful to you, please [star it on GitHub](https://github.com/MohammedEl-sayedAhmed/clipman/stargazers) — source installs aren't counted anywhere else, and stars are how the project gets visibility.

### Alternative Installation

<details>
<summary><strong>Snap</strong> (Ubuntu, auto-refreshes)</summary>

```bash
sudo snap install clipman
```

Snap users still need the [GNOME Shell extension](https://extensions.gnome.org/extension/9407/clipman-clipboard-monitor/) installed in the host session for clipboard detection — snap confinement blocks both the extension path and the `wl-paste --watch` fallback inside the sandbox.

</details>

<details>
<summary><strong>PyPI</strong></summary>

```bash
# System dependencies (pip can't install these)
sudo apt install python3-gi python3-dbus \
    gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0 \
    wl-clipboard

pip install clipman-clipboard
```

After installing, set up the Super+V shortcut (the install script does this automatically, but pip doesn't):

```bash
# Remove GNOME's default Super+V binding (notification tray)
gsettings set org.gnome.shell.keybindings toggle-message-tray "['<Super>m']"

# Register Clipman toggle on Super+V
CUSTOM_KEYS_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['$CUSTOM_KEYS_PATH/clipman/']"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CUSTOM_KEYS_PATH/clipman/" name "Clipman Toggle"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CUSTOM_KEYS_PATH/clipman/" command "clipman toggle"
gsettings set "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$CUSTOM_KEYS_PATH/clipman/" binding "<Super>v"
```

For clipboard detection, install the [GNOME Shell extension](https://extensions.gnome.org/extension/9407/clipman-clipboard-monitor/) or Clipman will fall back to `wl-paste --watch`.

</details>

<details>
<summary><strong>.deb (Debian/Ubuntu)</strong></summary>

Download `clipman_<version>_all.deb` from the [latest release](https://github.com/MohammedEl-sayedAhmed/clipman/releases/latest) and install:

```bash
sudo apt install ./clipman_*_all.deb
```

The package installs `/usr/bin/clipman`, the Python module, `.desktop` file, and icon. The per-user GNOME Shell extension and the Super+V keybinding are **not** registered by the package — after install, run `./install.sh` from a source checkout to enable them.

</details>

<details>
<summary><strong>.rpm (Fedora/RHEL)</strong></summary>

Download `clipman-<version>-1.noarch.rpm` from the [latest release](https://github.com/MohammedEl-sayedAhmed/clipman/releases/latest) and install:

```bash
sudo dnf install ./clipman-*-1.noarch.rpm
```

Same caveat as the `.deb`: the per-user extension + keybinding are not registered by the package; run `./install.sh` from a source checkout for the full setup.

</details>

<details>
<summary><strong>GNOME Shell Extension</strong> (installed automatically by install.sh)</summary>

The companion extension is required for clipboard detection. It is installed automatically by the install script, but can also be installed manually from [GNOME Extensions](https://extensions.gnome.org/extension/9407/clipman-clipboard-monitor/):

```bash
gnome-extensions install clipman-extension.zip
```

</details>

<details>
<summary><strong>AUR (Arch Linux)</strong></summary>

```bash
yay -S clipman-clipboard
```

Or with paru: `paru -S clipman-clipboard`

</details>

## Usage

| Action | How |
|--------|-----|
| Open clipboard history | <kbd>Super</kbd> + <kbd>V</kbd> |
| Paste an entry | Click on it or press <kbd>Enter</kbd> |
| Copy without pasting | <kbd>Shift</kbd> + <kbd>Enter</kbd> |
| Pin / unpin an entry | Click the star icon or press <kbd>P</kbd> |
| Delete an entry | Click the X icon or press <kbd>Delete</kbd> |
| Filter by type | Click **All**, **Text**, **Images**, or **Snippets** tabs |
| Create a snippet | Switch to **Snippets** tab and click **+ Add** |
| Search history | Type in the search bar |
| Edit a text entry | Click the edit icon on any text entry |
| Expand long text | Click the expand icon to see full content |
| Open a URL | Click the arrow icon on URL entries |
| Toggle incognito | Click the eye icon in the status bar |
| Clear all unpinned | Click **Clear All** |
| Close popup | <kbd>Escape</kbd> or click outside |

### Settings

Click the gear icon to open the `Adw.PreferencesWindow`. It carries six panes:

| Pane | Setting | Description |
|------|---------|-------------|
| **Appearance** | Theme | Segmented control: Dark (Catppuccin Mocha) / Light (Catppuccin Latte) |
| | Font size | Text size for entries (8–20px) |
| | Font color | Default, Green, Peach, Mauve, Pink, or Teal |
| | Opacity | Window transparency (30%–100%) |
| **Privacy** | Start in incognito mode | Launch with clipboard recording paused |
| | Auto-clear delay | Seconds before detected sensitive entries are purged (default 30) |
| | Purge sensitive entries now | One-tap removal of all stored sensitive entries |
| **Shortcuts** | Toggle shortcut | Customize the popup-toggle keybinding (default Super+V) via an in-app capture dialog |
| | Paste mode | How Clipman pastes after copy: **Auto-detect** (default — Ctrl+Shift+V in terminals, Ctrl+V elsewhere), **Ctrl+V**, **Ctrl+Shift+V**, or **Shift+Insert** |
| **Storage** | Max entries | Number of entries to keep (50–5,000) |
| | Database location | Path to the SQLite database |
| | Backup / Restore | Export and import your clipboard database |
| **Updates** | Check for updates | Toggle the daily anonymous check against GitHub Releases. Default: ON for source / PyPI / AUR, OFF for Snap and Flatpak (they auto-refresh). See [ADR 0007](docs/adr/0007-in-app-update-notifications.md) |
| | Check now | Manual check button — bypasses the 24h cooldown |
| **About** | Version + links | Version string (sourced from `clipman/_version.py`), license, homepage, and acknowledgements |

Settings are saved automatically and persist across sessions.

Snippets get their own surface: clicking **Edit snippets** opens an
`Adw.NavigationSplitView` master-detail dialog (`clipman/snippets_dialog.py`)
with a searchable list on the left and an editor form on the right —
template variables (`${date}`, `${time}`, `${clipboard}`) included.

## How It Works

1. A **GNOME Shell extension** detects clipboard changes natively via `Meta.Selection`'s `owner-changed` signal — no polling, no subprocesses, no screen flicker
2. The extension reads the content using a **MIME type fallback chain** (`text/plain;charset=utf-8` → `UTF8_STRING` → `text/plain` → `STRING`) and sends it to the daemon over **D-Bus**
3. The daemon stores entries in an **SQLite database** (WAL mode) at `~/.local/share/clipman/`
4. Duplicates are detected via **SHA256 hashing** — copying the same content updates the timestamp and bumps it to the top
5. Pressing **Super+V** sends a **D-Bus toggle** to the daemon, which shows the popup window near the cursor
6. Clicking an entry copies it via `wl-copy`, hides the popup, and the extension simulates a **paste keystroke** using a Clutter virtual keyboard

### Architecture

Clipman is split into a GNOME Shell extension that detects clipboard
changes natively and a Python + GTK 4 + libadwaita daemon that stores
history in a local SQLite database. The two halves talk over D-Bus on
the session bus; there is no polling, no telemetry, and only one
network call (the daily anonymous update check, opt-out — see
[ADR 0007](docs/adr/0007-in-app-update-notifications.md)).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full process model,
data model, D-Bus contract, trust boundaries, and decision-record
backlinks.

<details>
<summary><strong>Project structure</strong></summary>

```
clipman/
├── clipman.py                     # Entry point (start daemon / toggle popup)
├── clipman/
│   ├── __init__.py                # i18n/gettext setup; re-exports __version__
│   ├── _version.py                # Single source of truth for __version__
│   ├── app.py                     # Adw.Application lifecycle
│   ├── clipboard_monitor.py       # Event-driven clipboard monitor
│   ├── database.py                # SQLite storage with dedup/search/pin/snippets
│   ├── dbus_service.py            # D-Bus IPC for toggle and clipboard events
│   ├── edge_states.py             # 16 declarative StateSpec entries +
│   │                              #   render_edge_state dispatch (StatusPage /
│   │                              #   Banner / AlertDialog) for empty,
│   │                              #   no-results, incognito, sensitive-cleared,
│   │                              #   first-run, errors, …
│   ├── keybindings.py             # gsettings helpers for Super+V customization
│   ├── preferences.py             # Adw.PreferencesWindow (Appearance, Privacy,
│   │                              #   Shortcuts, Storage, Updates, About)
│   ├── snippets_dialog.py         # Adw.NavigationSplitView master-detail editor
│   ├── updates.py                 # Anonymous update-check against GitHub Releases
│   ├── window.py                  # Adw.ApplicationWindow + Adw.HeaderBar +
│   │                              #   Adw.ActionRow history list
│   └── style.css                  # libadwaita @-token overrides + Catppuccin
│                                  #   palette overlay (Mocha / Latte)
├── extension/
│   ├── extension.js               # GNOME Shell extension (clipboard detection + paste)
│   └── metadata.json              # Extension metadata
├── data/
│   ├── com.clipman.Clipman.desktop
│   ├── com.clipman.Clipman.svg    # App icon
│   ├── com.clipman.Clipman.metainfo.xml         # AppStream metadata
│   ├── io.github.MohammedEl_sayedAhmed.Clipman.desktop      # Flatpak-namespaced
│   ├── io.github.MohammedEl_sayedAhmed.Clipman.metainfo.xml # Flatpak AppStream
│   └── clipman.service            # Systemd user service
├── po/
│   ├── POTFILES.in                # Files with translatable strings
│   └── clipman.pot                # Translation template (70 strings)
├── tests/
│   ├── test_database.py           # Database unit tests (93 tests)
│   ├── test_clipboard_monitor.py  # Monitor unit tests (105 tests)
│   ├── test_keybindings.py        # Keybinding-customization tests (32 tests)
│   ├── test_updates.py            # Update-check tests (38 tests)
│   ├── test_entry_point.py        # D-Bus mainloop init tests (7 tests)
│   └── test_window_utils.py       # URL detection & time formatting (28 tests)
├── docs/
│   ├── adr/                       # Architecture Decision Records
│   ├── releases/                  # Per-release notes (mirrors GH Releases)
│   ├── dark-theme.png             # Screenshot (dark theme)
│   └── light-theme.png            # Screenshot (light theme)
├── snap/
│   └── snapcraft.yaml             # Snap packaging
├── aur/
│   └── PKGBUILD                   # AUR packaging
├── scripts/
│   └── bump-version.sh            # Single command to bump version everywhere
├── .github/
│   └── workflows/                 # CI: tests, lint, CodeQL, Scorecard, secret-scan,
│                                  #     release, snap-refresh, dependency-review, …
├── launcher.sh                    # Environment wrapper for snap terminals
├── install.sh
├── uninstall.sh
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
└── LICENSE / NOTICE
```

</details>

## Troubleshooting

**Extension not loading after install**
Log out and back in. GNOME Shell extensions require a session restart to activate.

**Super+V doesn't open Clipman**
The install script reassigns Super+V from GNOME's message tray. Check for conflicts:
```bash
gsettings get org.gnome.shell.keybindings toggle-message-tray
```
If it still shows `<Super>v`, the keybinding wasn't reassigned. Re-run `./install.sh`.

**XWayland apps (VSCode, Electron) not detected**
Verify the extension is enabled:
```bash
gnome-extensions list --enabled | grep clipman
```
If missing, enable it with `gnome-extensions enable clipman@clipman.com` and log out/in.

**Pasting shows `^V` in VSCode/Electron integrated terminals**
Clipman auto-pastes with Ctrl+V, which standalone terminals interpret correctly. However, integrated terminals inside editors (VSCode, Cursor) expect Ctrl+Shift+V. Use **Shift+Enter** in Clipman to copy without auto-pasting, then manually Ctrl+Shift+V in the terminal.

**Daemon not starting**
Check the service status:
```bash
systemctl --user status clipman.service
journalctl --user -u clipman.service -n 20
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, project structure, coding guidelines, and how to run the test suite (303 tests, no GTK or D-Bus required).

## Uninstall

```bash
./uninstall.sh
```

This stops the systemd service and removes the GNOME Shell extension, keybinding, systemd service, app icon, and optionally your clipboard history data.

## License

Copyright 2025–2026 Mohammed El-sayed Ahmed

Licensed under the **Apache License, Version 2.0**. You may use, modify, and distribute this software, provided you:

- Include the original [LICENSE](LICENSE) and [NOTICE](NOTICE) files
- Give appropriate credit to the original author
- State any changes you made

See the [LICENSE](LICENSE) and [NOTICE](NOTICE) files for full details.

## Star History

<a href="https://star-history.com/#MohammedEl-sayedAhmed/clipman&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=MohammedEl-sayedAhmed/clipman&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=MohammedEl-sayedAhmed/clipman&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=MohammedEl-sayedAhmed/clipman&type=Date" />
  </picture>
</a>

## Acknowledgements

- Theme palette by [Catppuccin](https://github.com/catppuccin/catppuccin)
- CI powered by [GitHub Actions](https://github.com/features/actions)
