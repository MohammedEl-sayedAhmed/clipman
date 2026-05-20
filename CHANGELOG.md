# Changelog

All notable changes to Clipman are documented in this file.

## [Unreleased]

### Added
- Customizable toggle shortcut from the settings panel. Click the
  shortcut button to capture a new key combination; the daemon writes
  it to GNOME's custom keybinding via gsettings. Default unchanged
  (`Super+V`). Closes #4.
- Customizable paste keystroke from the settings panel: `Auto-detect`
  (default — Ctrl+V, switches to Ctrl+Shift+V for terminals),
  `Ctrl+V`, `Ctrl+Shift+V`, or `Shift+Insert`. Closes #7.
- `clipman/keybindings.py` module with gsettings shell-out helpers
  and a 30-test unit suite (`tests/test_keybindings.py`).

### Changed
- GNOME Shell extension D-Bus interface: `SimulatePaste()` now
  accepts an optional `s mode` argument. The daemon falls back to
  the no-arg signature for older extension builds, so the new
  daemon remains compatible with an unupgraded extension.
- `extension/metadata.json`: bumped to version 5.

### Internal / CI

#### Added
- **CI/security baseline** (#8): Dependabot for `pip` and
  `github-actions` (weekly, labeled `dependencies`/`python`/`ci`);
  CodeQL for Python and JavaScript with the `security-and-quality`
  suite (weekly + on PR/push); ruff on `clipman/` and `tests/`;
  shellcheck on `install.sh`/`uninstall.sh`/`launcher.sh`; gitleaks
  secret scan on PR/push; `SECURITY.md` with the private-disclosure
  policy; PR template + issue forms (bug, feature, and a config that
  routes security reports through GitHub Security Advisories).
- **Weekly Snap Store rebuild** (#9): `snap-refresh.yml` rebuilds and
  re-publishes the Snap on a weekly cron so the published artifact
  always carries the latest security patches for its base + python
  layer, even when no code changed in this repo.
- **Tag-triggered release automation** (#16): `release.yml` builds
  and publishes a tagged release end-to-end — pre-flight sanity
  checks (tag matches `pyproject.toml` and `snap/snapcraft.yaml`,
  CHANGELOG has a matching section), full test matrix
  (Python 3.10 / 3.11 / 3.12), PyPI publish via OIDC trusted
  publishing (no long-lived token), Snap publish to the stable
  channel, versioned GNOME extension bundle, and a GitHub Release
  with all artifacts attached and the body extracted from
  `CHANGELOG.md`. See `docs/releases/README.md` and ADR 0004.
- **CodeQL security-baseline ratchet** (#17): a PR fails CodeQL only
  if it introduces fingerprints not already in the on-disk baseline.
  Baseline lives on the `security-baseline` orphan branch, is
  refreshed automatically on `push: main`, and is protected against
  manual tampering by `baseline-guard.yml` (auto-revert + open
  issue). See ADR 0002.

#### Changed
- **Dependabot bumps**: `actions/labeler` 5.0.0 → 6.1.0 (#10),
  pinned to commit SHA per the project's supply-chain policy
  (ADR 0003).

#### Docs
- Added `docs/adr/` with the first six MADR-format ADRs covering
  the decisions behind PRs #8, #15, #16, and #17 plus the project's
  branch-protection posture. See `docs/adr/README.md` for the index.
- Added `docs/releases/README.md` documenting where release notes
  live and how the release pipeline assembles them.

## [1.0.4] - 2026-02-28

### Fixed
- D-Bus mainloop race condition: toggle path created a SessionBus connection before GLib mainloop was set, making the daemon unresponsive when started via Win+V

### Added
- 3 regression tests for D-Bus mainloop initialization order (226 total)

## [1.0.3] - 2026-02-24

### Added
- `wl-paste --watch` fallback for clipboard monitoring when GNOME Shell extension is absent
- Automatic extension detection at startup via D-Bus bus name check
- Crash recovery with auto-restart for the wl-paste watcher subprocess
- 26 new tests covering watcher lifecycle, event dispatch, MIME handling, and crash recovery

### Changed
- Clipman now works as a standalone app on any Wayland compositor (KDE, Sway, Hyprland, etc.)

## [1.0.2] - 2026-02-23

### Security
- Hardened backup import against SQLite URI injection
- Reject imported backups containing triggers or views
- Added image magic bytes validation (PNG, JPEG, GIF, BMP, WebP)
- Extended sensitive data detection (npm tokens, private keys, connection strings, SSH keys)

## [1.0.1] - 2026-02-23

### Fixed
- Unreliable clipboard detection — added 150ms debounce to extension's clipboard change handler
- D-Bus slot name in Snap packaging now matches actual daemon bus name (`com.clipman.Daemon`)

### Changed
- Added AUR and Snap Store badges to README
- Fixed Snap install instructions (strict confinement, not classic)
- Added AUR install commands (`yay`/`paru`)
- Added screenshots and donation URL to AppStream metadata

## [1.0.0] - 2026-02-22

### Added
- Clipboard history with text and image support
- Full-text search across all entries
- Pin/unpin entries to keep them permanently
- GNOME Shell extension for native Wayland clipboard detection
- XWayland clipboard support via MIME type fallback chain (VSCode, Electron apps)
- Super+V keyboard shortcut to toggle the popup
- Dark and light themes (Catppuccin Mocha / Latte)
- Configurable opacity, font size, and font color (6 presets)
- Incognito mode — pause history recording
- Sensitive data detection (tokens, passwords) with 30-second auto-clear
- Preview expansion for long entries
- Inline editing of text entries
- URL detection with one-click open in browser
- Reusable text snippets with dedicated tab
- Database backup and restore from settings
- Terminal-aware paste (Ctrl+Shift+V for terminal emulators)
- Window appears near cursor position
- Autostart on login via systemd user service with auto-restart
- i18n/gettext framework with 70 translatable strings
- CSS theming extracted to separate template file (Catppuccin)
- Snap packaging configuration
- 150 automated tests (database, clipboard monitor, URL detection, time formatting)
