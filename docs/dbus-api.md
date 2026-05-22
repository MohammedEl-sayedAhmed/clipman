# D-Bus API reference

Reference for third-party integrators driving or observing clipman
over D-Bus. Two interfaces are exported on the **session bus**:

1. The daemon's `com.clipman.Daemon` — used by anything that wants
   to drive clipman (toggle the popup, inject a clipboard entry).
2. The extension's `org.gnome.Shell.Extensions.clipman` — used by
   the daemon itself to ask the GNOME Shell extension to synthesize
   paste keystrokes or reposition the popup. Most third-party
   integrators will not need this surface; it's documented for
   transparency.

All methods are synchronous (no out arguments, no signals). The
surface is intentionally small.

## Stability tiers

- **stable** — signature is part of the project's public contract;
  removal or rename triggers a MAJOR version bump (see
  [ADR 0010](adr/0010-versioning-policy.md)). Argument *addition*
  with a daemon-side try-with-arg / retry-without-arg fallback is
  a MINOR (precedent: [ADR 0005](adr/0005-paste-mode-as-dbus-arg.md)).
- **experimental** — reserved; no current methods are experimental.

## com.clipman.Daemon (the daemon)

| Field            | Value                          |
|------------------|--------------------------------|
| Bus name         | `com.clipman.Daemon`           |
| Object path      | `/com/clipman/Daemon`          |
| Interface        | `com.clipman.Daemon`           |

### Toggle

| Field        | Value          |
|--------------|----------------|
| Signature    | `()` → `()`    |
| Introduced   | 1.0.0          |
| Stability    | stable         |

Toggles popup visibility. If the popup is hidden, shows it (refreshed
+ presented). If it is visible, hides it. This is the method bound to
the user's global hotkey by default.

```bash
gdbus call --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon \
    --method com.clipman.Daemon.Toggle
```

### Show

| Field        | Value          |
|--------------|----------------|
| Signature    | `()` → `()`    |
| Introduced   | 1.0.0          |
| Stability    | stable         |

Refreshes the entry list from disk, shows the popup, focuses the
search entry, and presents the window. Calling `Show` on an
already-visible popup is idempotent: it re-refreshes and re-presents.

```bash
gdbus call --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon \
    --method com.clipman.Daemon.Show
```

### Hide

| Field        | Value          |
|--------------|----------------|
| Signature    | `()` → `()`    |
| Introduced   | 1.0.0          |
| Stability    | stable         |

Hides the popup. No-op if it is already hidden.

```bash
gdbus call --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon \
    --method com.clipman.Daemon.Hide
```

### Quit

| Field        | Value          |
|--------------|----------------|
| Signature    | `()` → `()`    |
| Introduced   | 1.0.0          |
| Stability    | stable         |

Quits the GTK application. The daemon process exits and the bus
name is released. Re-launching `clipman` (or letting the user's
session autostart respawn it) brings the service back.

```bash
gdbus call --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon \
    --method com.clipman.Daemon.Quit
```

### NewEntry

| Field        | Value                                                                       |
|--------------|-----------------------------------------------------------------------------|
| Signature    | `(ss)` → `()` — `content_type`, `content`                                   |
| Introduced   | 1.0.0                                                                       |
| Stability    | stable                                                                      |

Called by the GNOME Shell extension when the clipboard owner
changes. `content_type` selects the dispatch path:

- `'text'` — `content` is the UTF-8 body; the daemon calls
  `monitor.handle_new_text(content)`. An empty `content` string is
  a no-op (the daemon ignores empty text events).
- `'image'` — `content` is ignored; the daemon calls
  `monitor.handle_new_image()`, which reads the image off
  `wl-clipboard` itself.

Any other `content_type` is silently ignored. The method is
idempotent at the storage layer (the monitor deduplicates against
the last entry's fingerprint).

```bash
gdbus call --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon \
    --method com.clipman.Daemon.NewEntry 'text' 'hello from gdbus'
```

## org.gnome.Shell.Extensions.clipman (the extension)

| Field            | Value                                           |
|------------------|-------------------------------------------------|
| Bus name         | `org.gnome.Shell.Extensions.clipman`            |
| Object path      | `/org/gnome/Shell/Extensions/clipman`           |
| Interface        | `org.gnome.Shell.Extensions.clipman`            |

Note: the extension's `metadata.json` `version` integer (currently 5)
is the **extension D-Bus contract version**, not the product SemVer.
See [ADR 0005](adr/0005-paste-mode-as-dbus-arg.md) for the rationale
behind bumping it on contract changes.

### SimulatePaste

| Field        | Value                                                                                 |
|--------------|---------------------------------------------------------------------------------------|
| Signature    | `(s)` → `()` — `mode` ∈ `auto` / `ctrl-v` / `ctrl-shift-v` / `shift-insert`           |
| Introduced   | 1.0.5 (extension metadata.json v5)                                                    |
| Stability    | stable                                                                                |

Synthesizes a paste keystroke via Clutter's virtual keyboard. Mode
strings the extension doesn't recognise fall back to `auto`
(forward-compat: a newer daemon can ship a new mode without crashing
older extensions).

In **`auto`** mode the extension inspects the focused window's
`wm_class` and emits Ctrl+Shift+V for known terminal emulators
(gnome-terminal-server, tilix, kitty, alacritty, terminator, xterm,
konsole, foot, wezterm, st, sakura, xfce4-terminal, mate-terminal,
lxterminal, guake, tilda, cool-retro-term) and Ctrl+V everywhere
else.

```bash
gdbus call --session --dest org.gnome.Shell.Extensions.clipman \
    --object-path /org/gnome/Shell/Extensions/clipman \
    --method org.gnome.Shell.Extensions.clipman.SimulatePaste 'ctrl-shift-v'
```

The previous extension `metadata.json` v4 exposed
`SimulatePaste()` with no arguments. New daemons paired with an
unupgraded v4 extension still paste correctly: the daemon catches
the `DBusException` and retries `SimulatePaste()` with no
arguments. See [ADR 0005](adr/0005-paste-mode-as-dbus-arg.md).

### MoveWindowToCursor

| Field        | Value                                                       |
|--------------|-------------------------------------------------------------|
| Signature    | `(s)` → `()` — `title` matches the GTK window title         |
| Introduced   | 1.0.0                                                       |
| Stability    | stable                                                      |

Finds the window with the given title and moves it to the cursor
position, clamped so the window stays inside the active workspace's
work area. The match is exact (full string equality on
`meta_window.get_title()`); if no window matches, the call is a
silent no-op.

```bash
gdbus call --session --dest org.gnome.Shell.Extensions.clipman \
    --object-path /org/gnome/Shell/Extensions/clipman \
    --method org.gnome.Shell.Extensions.clipman.MoveWindowToCursor 'Clipman'
```

## Smoke-testing

Confirm both services are alive:

```bash
busctl --user list | grep -E 'com.clipman.Daemon|org.gnome.Shell.Extensions.clipman'
gdbus introspect --session --dest com.clipman.Daemon \
    --object-path /com/clipman/Daemon
gdbus introspect --session --dest org.gnome.Shell.Extensions.clipman \
    --object-path /org/gnome/Shell/Extensions/clipman
```

If the extension surface is missing, the extension isn't loaded — log
out / back in (Wayland requires a Shell restart to load extensions).

## See also

- [ARCHITECTURE.md](../ARCHITECTURE.md) — full process model
- [ADR 0005](adr/0005-paste-mode-as-dbus-arg.md) — D-Bus arg vs method choice
- [ADR 0010](adr/0010-versioning-policy.md) — when D-Bus changes trigger which SemVer bump
