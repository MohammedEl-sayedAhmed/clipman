# Customizations (fork of MohammedEl-sayedAhmed/clipman)

Personal fork of [clipman](https://github.com/MohammedEl-sayedAhmed/clipman) (Apache-2.0)
running on **Bluefin-DX (Fedora atomic), GNOME Shell 50, Wayland**.

Tracks **upstream v1.2.0**. As of 1.2 upstream paste is **native**: the GNOME
Shell extension restores focus (`RestorePreviousFocus`) and injects the
keystroke with a Clutter virtual device (`SimulatePaste`) — inside the
compositor, so it works where `wtype` cannot. This makes the old fork
`window.py` ydotool/keycode hacks unnecessary; they were dropped when merging
1.2. `wtype`/`ydotool` remain only as a fallback for non-GNOME compositors.

## Remaining fork deltas

These are **not** committed code edits — `install-bluefin.sh` applies them at
deploy time so the working tree stays clean against upstream:

| Delta | What | Why |
|---|---|---|
| `extension/metadata.json` `shell-version` | `45–48` → `45–50` | Bluefin is GNOME 50; extension API surface (D-Bus + `Meta.Selection`) survives the jump |
| `install.sh` dep step | `sudo dnf/apt install …` neutralized | atomic host — deps ship in the image, no `rpm-ostree` layering |

## Fork-only files

- `install-bluefin.sh` — idempotent atomic-host installer (runtime-patches the
  two deltas above, disables autostart dup, sets up fallback backend).
- `INSTALL-BLUEFIN.md` — setup + verification.
- This file.

## Runtime note (fallback only)

The `ydotool` fallback path still needs **ydotoold running** + user in the
**`input` group** (`/dev/uinput`). On GNOME 50 the native extension path is
primary, so this is belt-and-suspenders. See `INSTALL-BLUEFIN.md`.
