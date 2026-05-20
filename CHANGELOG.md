# Changelog

All notable changes to Clipman are documented in this file.

## [Unreleased]

## [1.0.6] - 2026-05-20

### Highlights

A follow-up release that lands everything 1.0.5 was meant to bring
plus the UI polish and packaging breadth the maintainer requested
after seeing the first cut.

**For users**, 1.0.6 supersedes 1.0.5 wherever 1.0.5 actually reached
(Snap Store stable). PyPI and the GitHub Release page reach this
codebase here for the first time — the 1.0.5 publish pipeline failed
mid-way and was retried as 1.0.6.

**New on top of 1.0.5:**

- Three additional release artifacts shipped to the GitHub Release:
  `.deb` (Debian / Ubuntu), `.rpm` (Fedora / RHEL / openSUSE), and an
  AppImage (best-effort, Linux-portable). PyPI wheel + sdist, Snap
  stable, and the GNOME Shell extension zip are unchanged from 1.0.5.
- Settings panel restructured into five clearly-labelled sections
  (**APPEARANCE / HISTORY / SHORTCUTS / UPDATES / DATA**). The Updates
  row no longer crams its switch + status + button onto one line.
- Comprehensive visual overhaul of the popup CSS — accent-coloured
  slider thumbs on slim tracks, refined buttons with bigger touch
  targets, theme as a proper segmented control, larger colour
  swatches, custom switch styling, more breathing room everywhere.
- Chrome font sizes raised across the board so labels, section
  headers, and buttons are legible on standard-DPI displays (the
  earlier overhaul had drifted to 8-11 px; now 10-14 px depending
  on the role).
- A subtle but important fix: clicking certain settings widgets on
  some Wayland compositors used to silently swallow the click. The
  `focus-out-event` handler now distinguishes between losing focus
  to another window (still hides) and losing focus to a child of
  the popup itself (no-op). Affected the Switch, the combo box, and
  the shortcut-capture dialog.

### Compatibility

Unchanged from 1.0.5: GNOME Shell 45 – 48, Python 3.10 – 3.12,
extension `metadata.json` version 5.

### Install / upgrade

| Channel | Command |
|---------|---------|
| **PyPI** | `pip install --upgrade clipman-clipboard` |
| **Snap** | auto-refresh, or `snap refresh clipman` |
| **AUR** | `yay -S clipman` (or `paru -S clipman`) |
| **Source** | `git pull && ./install.sh` |
| **`.deb` (Debian / Ubuntu)** | grab `clipman_1.0.6_all.deb` from the GitHub Release → `sudo apt install ./clipman_1.0.6_all.deb` |
| **`.rpm` (Fedora / RHEL)** | grab `clipman-1.0.6-1.noarch.rpm` from the GitHub Release → `sudo dnf install ./clipman-1.0.6-1.noarch.rpm` |
| **AppImage** | grab `clipman-1.0.6-x86_64.AppImage` → `chmod +x` → run. Still needs system `python3-gi` and `gir1.2-gtk-3.0`. |
| **GNOME Extension** | re-run `install.sh`, or upload the attached `clipman-extension-v1.0.6.zip` at <https://extensions.gnome.org/upload/> |

### Changed
- Release pipeline: `pypa/gh-action-pypi-publish` now pinned to the
  *commit* SHA rather than the annotated-tag-object SHA. The previous
  pin caused the v1.0.5 PyPI publish to fail with "Unable to find
  image" because Docker-based actions resolve the image tag from the
  ref. `snapcore/action-{build,publish}` fixed for consistency.
- `softprops/action-gh-release` no longer fails when the AppImage
  glob doesn't match (`fail_on_unmatched_files: false`). AppImage
  packaging for a Python+GTK app is intentionally best-effort.
- CodeQL workflow: per-SHA concurrency group on `push` events so
  rapid back-to-back merges to `main` no longer drop the queued
  `update-baseline` job. `workflow_dispatch` added as a manual
  escape hatch.

### Internal / CI
- `.github/workflows/release.yml`: new `build-distpkgs` job (fpm-based
  .deb + .rpm) and new `build-appimage` job (python-appimage-based).
  Release body now carries a templated **Assets** table with use
  case + channel + install caveats per artifact.

## [1.0.5] - 2026-05-20

### Highlights

The first release with **customizable keyboard shortcuts** and an
**in-app update checker**. Two long-standing community requests
(issues [#4](https://github.com/MohammedEl-sayedAhmed/clipman/issues/4)
and [#7](https://github.com/MohammedEl-sayedAhmed/clipman/issues/7))
are addressed: pick any combo to open Clipman, pick how it sends the
paste keystroke (Auto / Ctrl+V / Ctrl+Shift+V / Shift+Insert).

Under the hood, this release also ships the entire CI/security and
release-automation overhaul — Dependabot, CodeQL with a
hash-stable baseline ratchet, OpenSSF Scorecard, secret scanning,
gitleaks, a tag-triggered release pipeline (PyPI via OIDC, Snap
stable, GitHub Release, extension bundle), weekly snap rebuilds for
Ubuntu security updates, and a documentation sweep covering nine
ADRs, a development guide, and a release runbook. See the full
breakdown below.

### Install / upgrade

| Channel | Command |
|---------|---------|
| **PyPI** | `pip install --upgrade clipman-clipboard` |
| **Snap** | auto-refreshes, or `snap refresh clipman` |
| **AUR** | `yay -S clipman` (or `paru -S clipman`) |
| **Source** | `git pull && ./install.sh` |
| **GNOME Extension** | re-run `install.sh`, or upload the attached `clipman-extension-v1.0.5.zip` at <https://extensions.gnome.org/upload/> |

### Compatibility

- **GNOME Shell** 45, 46, 47, 48 (extension `metadata.json` is at
  version 5 — `SimulatePaste(s mode)`; the daemon retries
  no-arg automatically against an unupgraded v4 extension).
- **Python** 3.10 – 3.12 (tested on `ubuntu-24.04`).

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
- **In-app update notifications.** Daemon polls GitHub Releases
  anonymously once per day; the settings panel gains an "Updates"
  row (status / opt-out switch / "Check now" button) and the popup
  surfaces a dismissible banner when a newer release is detected.
  Default ON for source / PyPI / AUR, OFF for Snap and Flatpak
  (they auto-refresh). New `clipman/updates.py` module with a
  38-test unit suite (`tests/test_updates.py`). `__version__`
  constant added to `clipman/__init__.py` as the runtime source of
  truth; `scripts/bump-version.sh` keeps it in sync with
  `pyproject.toml`. `network` plug added to `snap/snapcraft.yaml`
  for the opt-in path. See [ADR 0007](docs/adr/0007-in-app-update-notifications.md).

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
  `step-security/harden-runner` 2.10.2 → 2.19.3 (#11),
  `github/codeql-action` SHA bump (#12),
  `actions/checkout` 4.2.2 → 6.0.2 (#13),
  `actions/setup-python` 5.3.0 → 6.2.0 (#14), all pinned to commit
  SHA per the project's supply-chain policy (ADR 0003).
- **Ratchet fingerprint strategy** (#20): swapped the CodeQL
  ratchet's `rule:file:line` fingerprints for SARIF
  `partialFingerprints.primaryLocationLineHash` so PRs that just
  shift lines no longer surface as "new findings", and added
  `if: github.event_name == 'pull_request'` on the ratchet step so
  the `update-baseline` job can run on push without being blocked by
  the ratchet on main itself. Baseline schema bumped to `2`. See
  ADR 0008.
- **Scorecard SHA fix** (#22): the previous `ossf/scorecard-action`
  SHA was the annotated-tag object, not the commit it points to.
  Scorecard's webapp rejected it as an imposter commit, failing
  every push to main. Resolved to the real commit SHA.

#### Removed
- **Stray root-level Flathub manifest** (#18): the obsolete
  `com.clipman.Clipman.json` at the repo root used the pre-rename
  app-id and was not referenced anywhere. The current Flathub
  manifest lives at `flathub/io.github.MohammedEl_sayedAhmed.Clipman.json`.

#### Docs
- Added `docs/adr/` with the first six MADR-format ADRs covering
  the decisions behind PRs #8, #15, #16, and #17 plus the project's
  branch-protection posture. See `docs/adr/README.md` for the index.
- Added `docs/releases/README.md` documenting where release notes
  live and how the release pipeline assembles them.
- Added a Mermaid architecture diagram under the **How It Works**
  section of `README.md` (#21).
- Added `CODE_OF_CONDUCT.md` (Contributor Covenant v2.1),
  `docs/development.md` (build/test/debug guide), and
  `docs/release-checklist.md` (release runbook).
- Added ADR 0008 (ratchet fingerprint strategy, documents #20) and
  ADR 0009 (weekly snap rebuild cadence, documents #9).

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
