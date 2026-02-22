<div align="center">

# Clipman

**A clipboard history manager for Ubuntu/GNOME on Wayland**

Like Windows `Win+V` — but for Linux.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/MohammedEl-sayedAhmed/clipman/test.yml?branch=main&label=tests)](https://github.com/MohammedEl-sayedAhmed/clipman/actions)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04+-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com)
[![GNOME](https://img.shields.io/badge/GNOME-46--48-4A86CF?logo=gnome&logoColor=white)](https://gnome.org)
[![Wayland](https://img.shields.io/badge/Wayland-native-yellow)](https://wayland.freedesktop.org)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)

---

Press **Super+V** to view your clipboard history, search entries, pin favorites, and instantly paste previous copies.

<br>

<img src="docs/dark-theme.png" alt="Dark theme" width="320">&nbsp;&nbsp;<img src="docs/light-theme.png" alt="Light theme" width="320">

</div>

---

## Features

| Feature | Description |
|---------|-------------|
| **Text & Image support** | Stores both text and image clipboard entries |
| **Instant paste** | Click or press Enter to paste directly into the focused app |
| **Pin favorites** | Keep important entries permanently — exempt from pruning |
| **Search** | Instantly filter clipboard history by text content |
| **Filter tabs** | Switch between All, Text, Images, and Snippets views |
| **Snippet templates** | Save reusable text snippets for quick pasting |
| **Date grouping** | Entries organized into Today, Yesterday, and Older sections |
| **Keyboard shortcuts** | Arrow keys to navigate, Del to delete, P to pin, Shift+Enter to copy only |
| **Dark & Light themes** | Switch between dark (Catppuccin Mocha) and light (Catppuccin Latte) themes |
| **Font customization** | Adjustable font size and 6 font color presets |
| **Window opacity** | Configurable transparency from 30% to 100% |
| **Configurable history** | Adjust max history size from 50 to 5000 entries |
| **Character count** | Text entries show character count badge |
| **Image preview** | Hover over image entries for a larger preview tooltip |
| **Super+V shortcut** | Toggle the popup with a familiar keyboard shortcut |
| **Incognito mode** | Pause clipboard recording — nothing is saved while active |
| **Sensitive data protection** | Passwords and tokens auto-detected and auto-cleared after 30 seconds |
| **Preview expansion** | Expand long text entries inline to see the full content |
| **Inline edit** | Edit any text entry directly from the clipboard history |
| **URL detection** | URLs are auto-detected with a one-click open button |
| **Backup & Restore** | Export and import your clipboard database from settings |
| **Terminal-aware paste** | Sends Ctrl+Shift+V in terminal emulators, Ctrl+V elsewhere |
| **XWayland support** | Clipboard detection for VSCode, Electron, and other XWayland apps |
| **Autostart** | Runs as a background daemon via systemd, auto-restarts on crash |
| **Wayland native** | Zero polling — uses a GNOME Shell extension for flicker-free monitoring |
| **Lightweight** | Python + GTK3 — no Electron, no heavy frameworks |
| **Deduplication** | SHA256 hashing prevents duplicate entries; re-copying bumps to top |
| **Auto-pruning** | History capped at configurable limit (pinned entries are exempt) |

## Requirements

- Ubuntu 22.04+ with GNOME 46 and Wayland
- Python 3.10+
- GTK 3

> Dependencies are installed automatically by the install script.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/MohammedEl-sayedAhmed/clipman.git
cd clipman

# Install dependencies, extension, keybinding, and autostart
./install.sh

# Log out and back in to activate the GNOME Shell extension

# Start the daemon
python3 clipman.py &
```

After your next login, the daemon starts automatically.

## Usage

| Action | How |
|--------|-----|
| Open clipboard history | <kbd>Super</kbd> + <kbd>V</kbd> |
| Paste an entry | Click on it or navigate with <kbd>Arrow</kbd> keys and press <kbd>Enter</kbd> |
| Copy without pasting | <kbd>Shift</kbd> + <kbd>Enter</kbd> |
| Pin / unpin an entry | Click the star icon or press <kbd>P</kbd> |
| Delete an entry | Click the X icon or press <kbd>Delete</kbd> |
| Filter by type | Click **All**, **Text**, **Images**, or **Snippets** tabs |
| Create a snippet | Switch to **Snippets** tab and click **+ Add** |
| Search history | Type in the search bar |
| Edit a text entry | Click the edit icon (✎) on any text entry |
| Expand long text | Click the expand icon (▼) to see full content |
| Open a URL | Click the arrow icon (↗) on URL entries |
| Toggle incognito | Click the eye icon in the status bar |
| Clear all unpinned | Click **Clear All** |
| Close popup | <kbd>Escape</kbd> or click outside |

### Settings

Click the gear icon to access settings:

| Setting | Description |
|---------|-------------|
| **Opacity** | Window transparency (30%–100%) |
| **Font size** | Text size for entries (8–20px) |
| **Max history** | Number of entries to keep (50–5000) |
| **Theme** | Toggle between Dark and Light themes |
| **Font color** | Choose from Default, Green, Peach, Mauve, Pink, or Teal presets |
| **Data** | Backup or restore your clipboard database |

Settings are saved automatically and persist across sessions.

## Architecture

```
clipman/
├── clipman.py                  # Entry point (start daemon / toggle popup)
├── clipman/
│   ├── app.py                  # GTK Application lifecycle
│   ├── clipboard_monitor.py    # Event-driven clipboard monitor
│   ├── database.py             # SQLite storage with dedup/search/pin/snippets
│   ├── dbus_service.py         # D-Bus IPC for toggle and clipboard events
│   ├── window.py               # GTK3 popup window UI
│   └── style.css               # Theming stylesheet (Catppuccin templates)
├── extension/
│   ├── extension.js            # GNOME Shell extension (clipboard detection + paste)
│   └── metadata.json           # Extension metadata
├── data/
│   ├── com.clipman.Clipman.desktop
│   ├── com.clipman.Clipman.svg           # App icon
│   ├── com.clipman.Clipman.metainfo.xml  # AppStream metadata
│   └── clipman.service                   # Systemd user service
├── po/
│   ├── POTFILES.in             # Files with translatable strings
│   └── clipman.pot             # Translation template (70 strings)
├── tests/
│   ├── test_database.py           # Database unit tests (70 tests)
│   ├── test_clipboard_monitor.py  # Monitor unit tests (58 tests)
│   └── test_window_utils.py       # URL detection & time formatting (22 tests)
├── launcher.sh                 # Environment wrapper for snap terminals
├── install.sh
└── uninstall.sh
```

### How it works

1. A **GNOME Shell extension** detects clipboard changes natively via `Meta.Selection`'s `owner-changed` signal — no polling, no subprocesses, no screen flicker
2. The extension reads the clipboard content and sends it to the **daemon** over **D-Bus**
3. The daemon stores entries in an **SQLite database** at `~/.local/share/clipman/`
4. Duplicates are detected via **SHA256 hashing** — copying the same content updates the timestamp and bumps it to the top
5. Pressing **Super+V** sends a **D-Bus toggle** to the daemon, showing the popup window
6. Clicking an entry copies it via `wl-copy`, hides the popup, and the extension simulates **Ctrl+V** using a Clutter virtual keyboard to paste it into the focused app

## Uninstall

```bash
./uninstall.sh
```

This removes the GNOME Shell extension, keybinding, autostart entry, and optionally your clipboard history data.

## License

Copyright 2025 Mohammed El-sayed Ahmed

Licensed under the **Apache License, Version 2.0**. You may use, modify, and distribute this software, provided you:

- Include the original [LICENSE](LICENSE) and [NOTICE](NOTICE) files
- Give appropriate credit to the original author
- State any changes you made

See the [LICENSE](LICENSE) and [NOTICE](NOTICE) files for full details.
