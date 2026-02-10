# Clipman

A clipboard history manager for Ubuntu/GNOME on Wayland — like Windows `Win+V`.

Press **Super+V** to view your clipboard history, search entries, pin favorites, and quickly paste previous copies.

## Features

- **Text & Image support** — stores both text and image clipboard entries
- **Pin favorites** — keep important entries from being pruned
- **Search** — filter clipboard history by text content
- **Keyboard shortcut** — Super+V to toggle the popup
- **Autostart** — runs as a background daemon on login
- **Wayland native** — uses `wl-clipboard` for full Wayland compatibility
- **Lightweight** — Python + GTK3, no heavy frameworks

## Requirements

- Ubuntu 22.04+ with GNOME and Wayland
- Python 3
- GTK 3

## Installation

```bash
git clone <your-repo-url> clipman
cd clipman
./install.sh
```

The installer will:
1. Install system dependencies (`wl-clipboard`, `python3-gi`, `python3-dbus`)
2. Register the **Super+V** keyboard shortcut
3. Set up autostart on login

Then start the daemon:

```bash
python3 clipman.py &
```

After your next login, it starts automatically.

## Usage

| Action | How |
|--------|-----|
| Open clipboard history | **Super+V** |
| Copy an entry | Click on it |
| Pin/unpin an entry | Click the star icon |
| Delete an entry | Click the X icon |
| Search | Type in the search bar |
| Clear all unpinned | Click "Clear All" |
| Close popup | **Escape** |

## Uninstall

```bash
./uninstall.sh
```

## How It Works

- A background daemon monitors the clipboard via `wl-paste --watch`
- Entries are stored in an SQLite database at `~/.local/share/clipman/`
- The Super+V shortcut sends a D-Bus signal to toggle the popup window
- Duplicate entries are detected via SHA256 hashing
- History is capped at 500 entries (pinned entries are exempt)

## License

MIT
