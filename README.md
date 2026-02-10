<div align="center">

# Clipman

**A clipboard history manager for Ubuntu/GNOME on Wayland**

Like Windows `Win+V` — but for Linux.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-22.04+-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com)
[![GNOME](https://img.shields.io/badge/GNOME-46-4A86CF?logo=gnome&logoColor=white)](https://gnome.org)
[![Wayland](https://img.shields.io/badge/Wayland-native-yellow)](https://wayland.freedesktop.org)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)

---

Press **Super+V** to view your clipboard history, search entries, pin favorites, and quickly paste previous copies.

</div>

---

## Features

| Feature | Description |
|---------|-------------|
| **Text & Image support** | Stores both text and image clipboard entries |
| **Pin favorites** | Keep important entries permanently — exempt from pruning |
| **Search** | Instantly filter clipboard history by text content |
| **Super+V shortcut** | Toggle the popup with a familiar keyboard shortcut |
| **Autostart** | Runs as a background daemon, starts on login |
| **Wayland native** | Built on `wl-clipboard` for full Wayland compatibility |
| **Lightweight** | Python + GTK3 — no Electron, no heavy frameworks |
| **Deduplication** | SHA256 hashing prevents duplicate entries |
| **Auto-pruning** | History capped at 500 entries (pinned entries are exempt) |

## Requirements

- Ubuntu 22.04+ with GNOME and Wayland
- Python 3.10+
- GTK 3

> Dependencies are installed automatically by the install script.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/MohammedEl-sayedAhmed/clipman.git
cd clipman

# Install dependencies, keybinding, and autostart
./install.sh

# Start the daemon
python3 clipman.py &
```

After your next login, the daemon starts automatically.

## Usage

| Action | How |
|--------|-----|
| Open clipboard history | <kbd>Super</kbd> + <kbd>V</kbd> |
| Copy an entry | Click on it |
| Pin / unpin an entry | Click the star icon |
| Delete an entry | Click the X icon |
| Search history | Type in the search bar |
| Clear all unpinned | Click **Clear All** |
| Close popup | <kbd>Escape</kbd> |

## Architecture

```
clipman/
├── clipman.py                  # Entry point (start daemon / toggle popup)
├── clipman/
│   ├── app.py                  # GTK Application lifecycle
│   ├── clipboard_monitor.py    # wl-paste --watch clipboard watcher
│   ├── database.py             # SQLite storage with dedup/search/pin
│   ├── dbus_service.py         # D-Bus IPC for Super+V toggle
│   └── window.py               # GTK3 popup window UI
├── data/
│   └── com.clipman.Clipman.desktop
├── install.sh
└── uninstall.sh
```

### How it works

1. A **background daemon** monitors the system clipboard via `wl-paste --watch`
2. New entries (text or images) are stored in an **SQLite database** at `~/.local/share/clipman/`
3. Duplicates are detected via **SHA256 hashing** — copying the same content just updates the timestamp
4. Pressing **Super+V** sends a **D-Bus signal** to the running daemon, toggling the popup window
5. Clicking an entry copies it back to the clipboard via `wl-copy` and closes the popup

## Uninstall

```bash
./uninstall.sh
```

This removes the keybinding, autostart entry, and optionally your clipboard history data.

## License

Copyright 2025 Mohammed El-sayed Ahmed

Licensed under the **Apache License, Version 2.0**. You may use, modify, and distribute this software, provided you:

- Include the original [LICENSE](LICENSE) and [NOTICE](NOTICE) files
- Give appropriate credit to the original author
- State any changes you made

See the [LICENSE](LICENSE) and [NOTICE](NOTICE) files for full details.
