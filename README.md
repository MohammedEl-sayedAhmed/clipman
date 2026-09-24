<div align="center">

<img src="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/logo.svg" alt="Clipman logo" width="128" height="128">

# Clipman

**A clipboard history manager for Ubuntu/GNOME on Wayland**

Like Windows `Win+V` — but for Linux.

[![Get it from the Snap Store](https://snapcraft.io/en/dark/install.svg)](https://snapcraft.io/clipman)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/MohammedEl-sayedAhmed/clipman/test.yml?branch=main&label=tests)](https://github.com/MohammedEl-sayedAhmed/clipman/actions)
[![GitHub Stars](https://img.shields.io/github/stars/MohammedEl-sayedAhmed/clipman?style=flat&logo=github&label=Stars)](https://github.com/MohammedEl-sayedAhmed/clipman/stargazers)
[![GitHub Downloads](https://img.shields.io/github/downloads/MohammedEl-sayedAhmed/clipman/total?logo=github&label=Downloads)](https://github.com/MohammedEl-sayedAhmed/clipman/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04+-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com)
[![GNOME](https://img.shields.io/badge/GNOME-46--51-4A86CF?logo=gnome&logoColor=white)](https://gnome.org)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/MohammedEl-sayedAhmed/clipman/badge)](https://scorecard.dev/viewer/?uri=github.com/MohammedEl-sayedAhmed/clipman)
[![Wayland](https://img.shields.io/badge/Wayland-native-yellow)](https://wayland.freedesktop.org)
[![Python](https://img.shields.io/badge/Python-3.10--3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyPI](https://img.shields.io/pypi/v/clipman-clipboard?label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/clipman-clipboard/)
[![PyPI Downloads](https://img.shields.io/pepy/dt/clipman-clipboard?label=PyPI%20Downloads&logo=pypi&logoColor=white)](https://pepy.tech/project/clipman-clipboard)
[![GNOME Extensions](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fextensions.gnome.org%2Fextension-info%2F%3Fpk%3D9407&query=%24.downloads&label=EGO%20Downloads&logo=gnome&logoColor=white&color=4A86CF)](https://extensions.gnome.org/extension/9407/clipman-clipboard-monitor/)
[![AUR](https://img.shields.io/aur/version/clipman-clipboard?label=AUR&logo=archlinux&logoColor=white)](https://aur.archlinux.org/packages/clipman-clipboard)
[![Donate](https://img.shields.io/badge/Donate-PayPal-0070BA?logo=paypal&logoColor=white)](https://www.paypal.com/paypalme/mohammedelsayedammar)
[![GitHub Discussions](https://img.shields.io/github/discussions/MohammedEl-sayedAhmed/clipman?label=Discussions&logo=github)](https://github.com/MohammedEl-sayedAhmed/clipman/discussions)
[![Project Page](https://img.shields.io/badge/Project_Page-clipman-cba6f7?logo=googlechrome&logoColor=white)](https://mohammedel-sayedahmed.github.io/clipman/)

---

Press **Super+V** to view your clipboard history, search entries, pin favorites, and instantly paste previous copies.

<br>

<a href="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/demo/clipman-demo.mp4"><img src="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/demo/clipman-demo.gif" alt="Clipman — search your clipboard history and paste with one keystroke" width="720"></a>

<sub><i>▶ <a href="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/demo/clipman-demo.mp4">Watch the full-quality video</a></i></sub>

<br>

<img src="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/dark-theme.png" alt="Dark theme" width="320">&nbsp;&nbsp;<img src="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/main/docs/light-theme.png" alt="Light theme" width="320">

<br>

<sub><i>Above: the shipped GTK 4 + libadwaita popup. The full settings surface is a sidebar <code>Adw.Dialog</code>, the snippets editor is an <code>Adw.NavigationSplitView</code> dialog, and the edge states (empty, no results, sensitive clips cleared, first run, errors…) render as Adwaita <code>StatusPage</code> / <code>Banner</code> / <code>AlertDialog</code> with a shared Catppuccin overlay. <a href="https://mohammedel-sayedahmed.github.io/clipman/#design">Browse the mockups</a> · <a href="https://mohammedel-sayedahmed.github.io/clipman/">project page</a>.</i></sub>

</div>

---

Clipman is a **Wayland-native** clipboard manager for GNOME. A GNOME Shell extension reports every copy to the daemon over D-Bus, from `Meta.Selection` signals: no polling and no screen flicker. (Tools built on `wl-paste --watch` cannot do this on GNOME, which lacks the data-control protocol they need.) Privacy is built in: incognito mode, detection of labelled passwords, tokens, keys and card numbers (masked, and removed from the history after 30 seconds), and private file permissions. The whole app is Python + GTK 4 + libadwaita — no Electron, no heavy frameworks.

---

## Features

### Clipboard

- **Text and image support** — stores both content types with SHA256 deduplication
- **Search** — type to filter your text clips by content
- **Pin favorites** — keep important entries permanently, exempt from pruning
- **Filter tabs** — switch between All, Text, Images, and Snippets views
- **Snippet templates** — save reusable text blocks for quick pasting, with `${date}`, `${time}` and `${clipboard}`
- **Date grouping** — entries organized into ★ Pinned, Today, Yesterday, Earlier this week, and Older sections
- **Link and code recognition** — link clips show their domain, and code clips are marked as code
- **Length at a glance** — text rows show their length in characters
- **Auto-pruning** — history capped at a configurable limit (pinned entries exempt)

### Keyboard

| Key | Action |
|-----|--------|
| <kbd>Super</kbd> + <kbd>V</kbd> | Toggle the popup |
| <kbd>Arrow</kbd> keys | Navigate entries |
| <kbd>Enter</kbd> | Paste selected entry |
| <kbd>P</kbd> | Pin / unpin selected entry |
| <kbd>Delete</kbd> | Delete selected entry |
| <kbd>Escape</kbd> | Close popup |

### Appearance

- **Dark and light themes** — Catppuccin Mocha (dark), a warm-stone light palette, or follow the system scheme
- **Font customization** — adjustable size (8–20px) plus free-form font and accent color pickers
- **Window opacity** — configurable transparency from 30% to 100%

### Privacy and Security

- **Incognito mode** — pause clipboard recording entirely
- **Sensitive data detection** — labelled passwords, API tokens and keys, credential URLs and card numbers are detected, masked, and removed from the history after a configurable delay (default 30 s). The auto-clear can be switched off, and pinned clips are kept. A bare password with no label is not detected ([#313](https://github.com/MohammedEl-sayedAhmed/clipman/issues/313)), and the system clipboard itself is not cleared ([#314](https://github.com/MohammedEl-sayedAhmed/clipman/issues/314)).
- **Restrictive permissions** — data directory `0o700`, database and image files `0o600`
- **Path traversal protection** — all image paths validated before file operations
- **Safe restore** — a backup is checked (integrity, schema, no triggers or views) in a copy before it replaces your history, and your current history is kept as a safety copy
- **Parameterized SQL** — no injection vectors
- **No shell execution** — all subprocesses use argument lists, never `shell=True`
- **Update notifications without telemetry** — when enabled, the daemon does a single anonymous `GET` to `api.github.com/repos/.../releases/latest` once per day (no body, no params, no cookies, no identifiers). Default ON for source / PyPI / AUR installs, OFF for Snap and Flatpak (they auto-refresh). Settings → Updates to toggle. See [ADR 0007](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/docs/adr/0007-in-app-update-notifications.md).

### Integration

- **Terminal-aware paste** — sends <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd> to terminal apps (GNOME Console, Ptyxis, GNOME Terminal and many others), <kbd>Ctrl</kbd>+<kbd>V</kbd> elsewhere
- **XWayland support** — clipboard detection for VSCode, Electron, and other XWayland apps via MIME type fallback
- **Autostart** — `install.sh` sets up a systemd user service that starts the daemon at login and restarts it if it crashes
- **Backup and restore** — export and import your clipboard database from settings
- **GNOME Shell extension** — sees each copy from inside GNOME Shell, and types the paste keystroke

### Performance

- **Zero polling** — event-driven via `Meta.Selection` signals and D-Bus
- **SHA256 deduplication** — copying the same content bumps it to the top without creating duplicates
- **Configurable history** — 50 to 5,000 entries (the popup lists the newest 200 for now: [#322](https://github.com/MohammedEl-sayedAhmed/clipman/issues/322))
- **Lightweight** — Python + GTK 4 + libadwaita, no Electron or heavy frameworks

### Planned

These are wanted but not built yet. Each issue says what "done" means, and help is welcome.

- Open a link clip in the browser from its row — [#310](https://github.com/MohammedEl-sayedAhmed/clipman/issues/310)
- Read a long clip or a large image in full — [#311](https://github.com/MohammedEl-sayedAhmed/clipman/issues/311)
- Edit a clip before pasting it — [#312](https://github.com/MohammedEl-sayedAhmed/clipman/issues/312)
- Treat what password managers mark as secret as sensitive — [#313](https://github.com/MohammedEl-sayedAhmed/clipman/issues/313)
- Clear the system clipboard when a sensitive clip times out — [#314](https://github.com/MohammedEl-sayedAhmed/clipman/issues/314)
- Typo-tolerant search — [#315](https://github.com/MohammedEl-sayedAhmed/clipman/issues/315)
- Accent colour presets — [#316](https://github.com/MohammedEl-sayedAhmed/clipman/issues/316)
- Search the text inside images — [#317](https://github.com/MohammedEl-sayedAhmed/clipman/issues/317)
- KDE Plasma, Sway and Hyprland — [#318](https://github.com/MohammedEl-sayedAhmed/clipman/issues/318)
- A working AppImage — [#319](https://github.com/MohammedEl-sayedAhmed/clipman/issues/319)
- Show the remaining designed banner states (paused, incognito on, update check failed…) — [#320](https://github.com/MohammedEl-sayedAhmed/clipman/issues/320)
- Translations — [#321](https://github.com/MohammedEl-sayedAhmed/clipman/issues/321)
- The whole history in the popup, not just the newest 200 clips — [#322](https://github.com/MohammedEl-sayedAhmed/clipman/issues/322)
- One `clipman setup` command for package installs — [#323](https://github.com/MohammedEl-sayedAhmed/clipman/issues/323)
- The Super+V shortcut bound by the GNOME Shell extension, for every install — [#334](https://github.com/MohammedEl-sayedAhmed/clipman/issues/334)
- Stricter image checks, also on restore — [#335](https://github.com/MohammedEl-sayedAhmed/clipman/issues/335)
- Keep sensitive clips out of search results — [#336](https://github.com/MohammedEl-sayedAhmed/clipman/issues/336)

## Requirements

- Ubuntu 24.04+ with GNOME 46–51 and Wayland
- Python 3.10–3.12 (newer versions are not blocked, but CI does not test them)
- GTK 4 + libadwaita 1.5+

> Dependencies are installed automatically by the install script.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/MohammedEl-sayedAhmed/clipman.git
cd clipman

# Install the packages, the extension, the Super+V shortcut and the service
./install.sh

# Log out and back in: the extension and the daemon start at your next login
```

The systemd service auto-restarts on crash and starts automatically on login.

> If you cloned the repo and Clipman is useful to you, please [star it on GitHub](https://github.com/MohammedEl-sayedAhmed/clipman/stargazers) — source installs aren't counted anywhere else, and stars are how the project gets visibility.

### Alternative Installation

The packages below install the app. Unlike `install.sh`, they do not yet set up the GNOME Shell extension, the shortcut or the autostart: after installing, follow [Finish the setup](https://github.com/MohammedEl-sayedAhmed/clipman#finish-the-setup). [#323](https://github.com/MohammedEl-sayedAhmed/clipman/issues/323) tracks a single command for this.

<details>
<summary><strong>Snap</strong> (Ubuntu, auto-refreshes)</summary>

```bash
sudo snap install clipman
```

Then [finish the setup](https://github.com/MohammedEl-sayedAhmed/clipman#finish-the-setup). Known snap problems: [#283](https://github.com/MohammedEl-sayedAhmed/clipman/issues/283) (the shortcut) and [#284](https://github.com/MohammedEl-sayedAhmed/clipman/issues/284) (removing the snap can leave its daemon running).

</details>

<details>
<summary><strong>PyPI</strong></summary>

```bash
# System packages (pip can't install these)
sudo apt install python3-gi python3-dbus \
    gir1.2-gtk-4.0 gir1.2-adw-1 libadwaita-1-0 \
    wl-clipboard pipx

pipx install --system-site-packages clipman-clipboard
```

`--system-site-packages` lets pipx's environment see the GTK bindings from your distribution. Plain `pip install` is refused on Ubuntu 24.04 and later ([PEP 668](https://peps.python.org/pep-0668/)). Then [finish the setup](https://github.com/MohammedEl-sayedAhmed/clipman#finish-the-setup).

</details>

<details>
<summary><strong>.deb (Debian/Ubuntu)</strong></summary>

Download `clipman_<version>_all.deb` from the [latest release](https://github.com/MohammedEl-sayedAhmed/clipman/releases/latest) and install:

```bash
sudo apt install ./clipman_*_all.deb
```

The package installs `/usr/bin/clipman`, the Python module, the `.desktop` file, the icon, and a copy of the extension in `/usr/lib/clipman/extension/`. Then [finish the setup](https://github.com/MohammedEl-sayedAhmed/clipman#finish-the-setup).

</details>

<details>
<summary><strong>.rpm (Fedora/RHEL)</strong></summary>

Download `clipman-<version>-1.noarch.rpm` from the [latest release](https://github.com/MohammedEl-sayedAhmed/clipman/releases/latest) and install:

```bash
sudo dnf install ./clipman-*-1.noarch.rpm
```

It installs the same files as the `.deb`. Then [finish the setup](https://github.com/MohammedEl-sayedAhmed/clipman#finish-the-setup).

</details>

<details>
<summary><strong>AUR (Arch Linux)</strong></summary>

```bash
yay -S clipman-clipboard
```

Or with paru: `paru -S clipman-clipboard`. The package installs the app in `/opt/clipman`, the extension in `/usr/share/gnome-shell/extensions/`, and a systemd user service. Then [finish the setup](https://github.com/MohammedEl-sayedAhmed/clipman#finish-the-setup).

</details>

<details>
<summary><strong>GNOME Shell Extension</strong> (installed automatically by install.sh)</summary>

The companion extension lets Clipman see what you copy on GNOME, and types the paste for it. It does not bind the Super+V shortcut yet ([#334](https://github.com/MohammedEl-sayedAhmed/clipman/issues/334)). Clipman needs it: GNOME offers no other way to watch the clipboard, so `wl-paste --watch` does not work there. `install.sh` sets it up. Otherwise, get it from [GNOME Extensions](https://extensions.gnome.org/extension/9407/clipman-clipboard-monitor/), or install the zip attached to each release:

```bash
gnome-extensions install clipman-extension-vX.Y.Z.zip
```

</details>

### Finish the setup

For the packages above. `install.sh` does all of this for you.

**1. The GNOME Shell extension.** Log out and back in after the step for your package, so GNOME finds the extension, then turn it on.

| Package | Step |
|---------|------|
| .deb, .rpm | Copy the packaged extension: `mkdir -p ~/.local/share/gnome-shell/extensions/clipman@clipman.com && cp /usr/lib/clipman/extension/* ~/.local/share/gnome-shell/extensions/clipman@clipman.com/` |
| AUR | Nothing to copy: the package installed it. |
| Snap, PyPI | Install it from [GNOME Extensions](https://extensions.gnome.org/extension/9407/clipman-clipboard-monitor/). |

```bash
# After logging back in:
gnome-extensions enable clipman@clipman.com
```

**2. Start Clipman at every login.**

```bash
# AUR: the package ships a user service
systemctl --user enable --now clipman.service

# Snap, PyPI, .deb, .rpm: an autostart entry
mkdir -p ~/.config/autostart
printf '[Desktop Entry]\nType=Application\nName=Clipman\nExec=%s\n' "$(command -v clipman)" \
    > ~/.config/autostart/clipman.desktop
```

**3. The shortcut.** GNOME uses Super+V for its notification list, so free it first. In Settings → Keyboard → View and Customize Shortcuts:
1. Under **System**, change **Show the notification list** to another key.
2. Under **Custom Shortcuts**, add one named Clipman, with the command `clipman toggle` (AUR: `/opt/clipman/launcher.sh toggle`) and the shortcut Super+V.

## Usage

| Action | How |
|--------|-----|
| Open clipboard history | <kbd>Super</kbd> + <kbd>V</kbd> |
| Paste an entry | Click on it or press <kbd>Enter</kbd> |
| Pin / unpin an entry | Click the star icon or press <kbd>P</kbd> |
| Delete an entry | Click the trash icon or press <kbd>Delete</kbd> |
| Jump to search | <kbd>/</kbd> or <kbd>Ctrl</kbd> + <kbd>F</kbd> |
| Navigate entries | <kbd>↑</kbd> / <kbd>↓</kbd> |
| Filter by type | Click **All**, **Text**, **Images**, or **Snippets** tabs |
| Create a snippet | Switch to the **Snippets** tab, then click the **+** button in the header bar or press <kbd>Ctrl</kbd> + <kbd>N</kbd> |
| Search history | Type in the search bar |
| Toggle incognito | Click the eye icon in the header bar |
| Clear all unpinned | Click **Clear all** |
| Close popup | <kbd>Escape</kbd> or click outside |

### Settings

Click the gear icon to open the preferences dialog (an `Adw.Dialog` with a
left sidebar). It carries six panes:

| Pane | Setting | Description |
|------|---------|-------------|
| **Appearance** | Color scheme | Follow system / Dark (Catppuccin Mocha) / Light (warm stone) |
| | Catppuccin theme | On: the Catppuccin Mocha and warm-stone palettes. Off: follow your system GNOME theme and accent color |
| | Font size | Text size for entries (8–20px) |
| | Accent color & font color | Free-form color pickers with one-tap reset to theme defaults |
| | Window opacity | Window transparency (30%–100%) |
| | Show count badges on filter tabs | Show the per-filter item count on the All / Text / Images / Snippets tabs |
| **Privacy** | Incognito mode | Pause recording now and on every launch |
| | Auto-clear sensitive clips | Delete detected secrets after the delay below; when off they stay masked (on by default) |
| | Auto-clear delay | Seconds before detected sensitive entries are purged (default 30) |
| | Purge sensitive entries now | Remove every stored sensitive entry, even when auto-clear is off |
| **Shortcuts** | Toggle clipboard popup | Change the popup shortcut (default Super+V) with an in-app capture dialog. This changes the shortcut `install.sh` set up; [#283](https://github.com/MohammedEl-sayedAhmed/clipman/issues/283) tracks the other installs |
| | When I select a clip | How Clipman pastes: **Auto-paste (best effort)** (the default: Ctrl+Shift+V in terminal apps, Ctrl+V elsewhere), **Simulate Ctrl+V**, **Simulate Ctrl+Shift+V**, or **Simulate Shift+Insert** |
| **Storage** | Maximum entries to keep | Number of entries to keep (50–5,000) |
| | Database location | Path to the SQLite database |
| | Export backup / Restore from backup | Export and import your clipboard database |
| **Updates** | Check for updates automatically | Toggle the daily anonymous check against GitHub Releases. Default: ON for source / PyPI / AUR, OFF for Snap and Flatpak (they auto-refresh). See [ADR 0007](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/docs/adr/0007-in-app-update-notifications.md) |
| | Last checked / Latest known version | When the last check ran and the newest version seen, with a link to its release notes |
| **About** | Version + links | Version string (sourced from `clipman/_version.py`), license, homepage, and acknowledgements |

Settings are saved automatically and persist across sessions.

Snippets get their own surface: the **+** button in the header bar,
shown only on the Snippets tab, opens an
`Adw.NavigationSplitView` master-detail dialog (`clipman/snippets_dialog.py`)
with a searchable list on the left and an editor form on the right —
template variables (`${date}`, `${time}`, `${clipboard}`) included.

## How It Works

1. A **GNOME Shell extension** detects clipboard changes natively via `Meta.Selection`'s `owner-changed` signal — no polling and no screen flicker
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
[ADR 0007](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/docs/adr/0007-in-app-update-notifications.md)).

See [ARCHITECTURE.md](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/ARCHITECTURE.md) for the full process model,
data model, D-Bus contract, trust boundaries, and decision-record
backlinks.

<details>
<summary><strong>Project structure</strong></summary>

```
clipman/
├── clipman.py                     # Entry point (start daemon / toggle popup)
├── clipman/
│   ├── __init__.py                # i18n/gettext setup; re-exports __version__
│   ├── __main__.py                # `python -m clipman`
│   ├── _version.py                # Single source of truth for __version__
│   ├── cli.py                     # Command line: dependency check, daemon, toggle
│   ├── app.py                     # Adw.Application lifecycle
│   ├── clipboard_monitor.py       # Receives clips from the extension, stores them
│   ├── database.py                # SQLite storage with dedup/search/pin/snippets
│   ├── dbus_service.py            # D-Bus IPC for toggle and clipboard events
│   ├── edge_states.py             # Declared edge states (empty, no results,
│   │                              #   sensitive clips cleared, first run, errors…)
│   ├── keybindings.py             # gsettings helpers for Super+V customization
│   ├── preferences.py             # Sidebar Adw.Dialog (Appearance, Privacy,
│   │                              #   Shortcuts, Storage, Updates, About)
│   ├── sensitive.py               # Sensitive-data detection
│   ├── shell_bridge.py            # Calls into the GNOME Shell extension
│   ├── snippets_dialog.py         # Adw.NavigationSplitView master-detail editor
│   ├── updates.py                 # Anonymous update-check against GitHub Releases
│   ├── window.py                  # Adw.ApplicationWindow + Adw.HeaderBar +
│   │                              #   virtualized Gtk.ListView history list
│   └── style.css                  # libadwaita @-token overrides + palette
│                                  #   overlay (Catppuccin Mocha / warm stone)
├── extension/
│   ├── extension.js               # GNOME Shell extension (clipboard detection + paste)
│   └── metadata.json              # Extension metadata
├── data/                          # Desktop entries, icon, AppStream metadata,
│                                  #   systemd user service
├── po/                            # Translation template (po/clipman.pot)
├── tests/                         # Unit tests, and tests/e2e: a headless GNOME
│                                  #   Shell run of install, copy and uninstall
├── docs/                          # ADRs, design mockups, the project page
├── snap/                          # Snap packaging
├── aur/                           # AUR packaging
├── scripts/                       # dev.sh task runner, release and install helpers
├── .github/workflows/             # CI: tests, lint, CodeQL, Scorecard, secret scan,
│                                  #   release, snap refresh, dependency review, …
├── launcher.sh                    # Environment wrapper for snap terminals
├── install.sh
└── uninstall.sh
```

</details>

## Troubleshooting

**Extension not loading after install**
Log out and back in: GNOME Shell only loads a new extension at login. If it is still off, run `gnome-extensions enable clipman@clipman.com`.

**Super+V doesn't open Clipman**
The install script reassigns Super+V from GNOME's message tray. Check for conflicts:
```bash
gsettings get org.gnome.shell.keybindings toggle-message-tray
```
If it still shows `<Super>v`, the keybinding wasn't reassigned. Re-run `./install.sh`, which keeps a shortcut you chose yourself. For package installs, see [Finish the setup](https://github.com/MohammedEl-sayedAhmed/clipman#finish-the-setup).

**XWayland apps (VSCode, Electron) not detected**
Verify the extension is enabled:
```bash
gnome-extensions list --enabled | grep clipman
```
If missing, enable it with `gnome-extensions enable clipman@clipman.com`.

**Pasting shows `^V` in a terminal inside an editor**
Auto-paste sends Ctrl+Shift+V only to terminal apps. A terminal inside an editor (VS Code, Cursor) is part of the editor's window, so it gets Ctrl+V. For those, open Preferences → Shortcuts and set **When I select a clip** to **Simulate Ctrl+Shift+V**.

**Daemon not starting**
Check the service status:
```bash
systemctl --user status clipman.service
journalctl --user -u clipman.service -n 20
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/CONTRIBUTING.md) for setup instructions, project structure, coding guidelines, and how to run the test suite.

## Uninstall

```bash
./uninstall.sh
```

This stops the service and a running daemon, and removes the GNOME Shell extension, the shortcut, the service and the app icon. It asks before removing your clipboard history, and keeps it when there is no terminal to ask in.

## License

Copyright 2025–2026 Mohammed El-sayed Ahmed

Licensed under the **Apache License, Version 2.0**. You may use, modify, and distribute this software, provided you:

- Include the original [LICENSE](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/LICENSE) and [NOTICE](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/NOTICE) files
- Give appropriate credit to the original author
- State any changes you made

See the [LICENSE](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/LICENSE) and [NOTICE](https://github.com/MohammedEl-sayedAhmed/clipman/blob/main/NOTICE) files for full details.

## Star History

<a href="https://github.com/MohammedEl-sayedAhmed/clipman/stargazers">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/numbers/star-history-dark.svg" />
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/numbers/star-history-light.svg" />
    <img alt="Star history chart" src="https://raw.githubusercontent.com/MohammedEl-sayedAhmed/clipman/numbers/star-history-light.svg" />
  </picture>
</a>

<sub>Chart and <a href="https://github.com/MohammedEl-sayedAhmed/clipman/blob/numbers/stats_history.json">download history</a> are regenerated daily from the GitHub API by the numbers workflow, onto the <a href="https://github.com/MohammedEl-sayedAhmed/clipman/tree/numbers"><code>numbers</code> branch</a> — no third-party chart service.</sub>

## Acknowledgements

- Theme palette by [Catppuccin](https://github.com/catppuccin/catppuccin)
- CI powered by [GitHub Actions](https://github.com/features/actions)
