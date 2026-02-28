# Changelog

All notable changes to Clipman are documented in this file.

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
