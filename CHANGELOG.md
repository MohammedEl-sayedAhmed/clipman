# Changelog

All notable changes to Clipman are documented in this file.

## [Unreleased]

## [1.2.0] - 2026-07-18

### Highlights

The GTK 4 line is now **stable** — this release closes out the
post-rewrite stabilization tracker (#132) and removes the "use v1.0.6"
advisory. Three fronts landed since 1.1.0: true **Win+V behaviour on
GNOME Wayland**, a **~60× faster list**, and a **full redesign to the
project's design mockups**.

### Fixed — Wayland/Win+V parity (#141, #149, #156)

- The popup now takes real input focus on GNOME Wayland: buttons, search
  and keyboard work; clicking outside dismisses it; it stays out of the
  dash/dock and Alt+Tab; Escape closes; paste lands in the previously
  focused app (keystrokes are injected by the Shell extension — `wtype`
  cannot inject on Mutter — and the clipboard is set via `wl-copy`,
  since a background `Gdk.Clipboard.set()` silently fails).
- The installer launches the daemon once (systemd user service only);
  the duplicate XDG autostart that raced for the D-Bus name is gone.
- Incognito is one persistent state across the header toggle, footer
  pill and Privacy switch — "off" survives restarts (previously stale
  state could silently stop recording).

### Performance (#150)

- Opening the popup and switching filters no longer freezes: rows are
  lightweight widgets (~5× cheaper than `Adw.ActionRow`), image
  thumbnails are decoded once and cached, and long histories stream in
  incrementally. Measured on a real 263-entry history: back-to-All
  refresh ~3.4 s → ~51 ms.

### Changed — redesign to the design mockups (#151, #153–#155, #159)

- Colour-coded type icons (text/link/code/image/snippet) with
  conservative code/URL detection; per-type row metadata (domain for
  links, size + dimensions for images, "Code" tag, snippet use-counts).
- Day-grouped history (★ Pinned / Today / Yesterday / Earlier) with a
  gold pinned group; hover-revealed row actions; sensitive entries are
  masked with a lock icon and an auto-clear countdown.
- Segmented filter switcher (All / Text / Images / Snippets) with live
  count badges; search field with a `/` shortcut hint; footer with item
  count, Recording/Paused pill and Clear all.
- Preferences rebuilt with a left sidebar (matches the mockup), an
  accent colour picker with contrast-aware foreground, and a generic
  font colour picker replacing the fixed presets.
- Light mode is the mockups' high-contrast "stone" palette — every
  text/background pair now clears WCAG AA (the muted Catppuccin Latte
  text was failing it); with the Catppuccin toggle off, the popup
  follows the system GNOME light/dark preference.
- All 19 design edge states are implemented and reachable, including
  guided first-run/extension setup, watcher-crashed, clipboard-blocked,
  shortcut-failed and a database-error screen; banners carry a
  description line and a dismiss button.

### Compatibility

Toolchain floors unchanged from 1.1.0 (GTK 4 ≥ 4.10, libadwaita ≥ 1.4,
Python 3.10–3.12, GNOME Shell 45–48). No D-Bus contract changes. SQLite
schema gains an additive `snippets.use_count` column via automatic
migration — downgrades to 1.1.0 remain safe.

## [1.1.0] - 2026-06-25

### Highlights

The full **GTK 3 → GTK 4 + libadwaita** port lands in this release.
The popup, the settings surface, the snippets editor, and every edge
state were rebuilt from the ground up against modern Adwaita widgets,
and the Catppuccin palette is now applied as a `@named-color`
overlay so the entire UI picks up the theme without per-widget CSS.
No D-Bus contracts changed (`com.clipman.Daemon` and
`org.gnome.Shell.Extensions.clipman` are byte-identical), the SQLite
schema is unchanged, and no settings keys were renamed — per
[ADR 0010](docs/adr/0010-versioning-policy.md) this is a MINOR
release, not a MAJOR. Existing users keep their history,
preferences, and snippets.

### Compatibility

- **Toolkit floor:** GTK 4 ≥ 4.10 and libadwaita ≥ 1.4. Ubuntu 22.04
  no longer ships a recent-enough libadwaita; the supported baseline
  is **Ubuntu 24.04+** (or any distro with libadwaita 1.4 in its
  default repos).
- **Python:** 3.10 – 3.12 (unchanged).
- **GNOME Shell:** 45 – 48 (unchanged).
- **Extension `metadata.json` version:** 5 (unchanged — no D-Bus
  signature changes).

### Install / upgrade

| Channel | Command |
|---------|---------|
| **PyPI** | `pip install --upgrade clipman-clipboard` |
| **Snap** | auto-refresh, or `snap refresh clipman` |
| **AUR** | `yay -S clipman-clipboard` (or `paru -S clipman-clipboard`) |
| **Source** | `git pull && ./install.sh` |

### Changed (UI / runtime)

- **GTK 3 → GTK 4 + libadwaita.** Every UI module was reworked:
  - `clipman/window.py` is now an `Adw.ApplicationWindow` with an
    `Adw.HeaderBar` and an `Adw.ActionRow`-driven history list.
  - `clipman/preferences.py` extracts settings out of the popup into
    a dedicated `Adw.PreferencesWindow` with **six panes** —
    Appearance, Privacy, Shortcuts, Storage, Updates, About — replacing
    the cramped inline settings panel from 1.0.x.
  - `clipman/snippets_dialog.py` ships the snippets editor as an
    `Adw.NavigationSplitView` master-detail dialog, with a searchable
    list on the left and an editor form (template variables
    included) on the right.
  - `clipman/edge_states.py` declares **16 `StateSpec` entries** for
    the empty, no-results, incognito, sensitive-cleared, first-run,
    extension-missing, backup-failed, and other edge states, all
    dispatched at render time by `render_edge_state` into one of
    `Adw.StatusPage`, `Adw.Banner`, or `Adw.AlertDialog`. The state
    set matches the design-workspace mockups one-to-one.
- **Catppuccin palette overlay.** `clipman/style.css` now overrides
  libadwaita's `@named-color` tokens (`@accent_color`,
  `@window_bg_color`, `@card_bg_color`, …) with Catppuccin Mocha for
  dark and Catppuccin Latte for light, so every Adwaita surface
  picks up the theme automatically — no per-widget CSS rules
  required. Matches the marketing mockup exactly.
- **Version literal** moved out of `clipman/__init__.py` into a leaf
  module `clipman/_version.py` to break a cyclic-import path that
  CodeQL was flagging as `py/cyclic-import`. The public
  `clipman.__version__` API is unchanged (`__init__.py` re-exports
  from `_version`) and `scripts/bump-version.sh` patches the literal
  in its new home.

### Internal / packaging

- `install.sh`, `snap/snapcraft.yaml`, and `aur/PKGBUILD` already
  declare GTK 4 + libadwaita dependencies (`gir1.2-gtk-4.0`,
  `gir1.2-adw-1`, `libadwaita-1-0` on Debian/Ubuntu; `gtk4`,
  `libadwaita` on Arch; `gtk4`, `libadwaita` stage-packages on
  snap). The lockstep bump landed in `#83` ahead of the code port.
- `pyproject.toml` `project.description` now reads "A Wayland-native
  clipboard history manager built with GTK 4 and libadwaita".

### Documentation

- `README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`,
  `docs/index.html`, `docs/llms.txt`, and `docs/llms-full.txt`
  refreshed to describe the new UI surface (Adw widgets, six-pane
  preferences, snippets dialog, 16 edge states, Catppuccin overlay)
  and the new toolkit floor (Ubuntu 24.04 / GTK 4 + libadwaita 1.4).
- AppStream metainfo files (`data/com.clipman.Clipman.metainfo.xml`,
  `data/io.github.MohammedEl_sayedAhmed.Clipman.metainfo.xml`) gain
  a `<release version="1.1.0">` entry describing the port.

### Documentation (carried over from the 1.0.6 → 1.1.0 cycle)

A comprehensive nine-PR documentation overhaul (PRs #40 through #48)
landed during the 1.0.6 → 1.1.0 cycle, alongside the toolkit port.
The release pipeline, install channels, and runtime behavior were
not affected by these docs PRs.

- `docs/adr/0010-versioning-policy.md` — codifies SemVer 2.0.0 with
  clipman-specific MAJOR/MINOR/PATCH triggers (D-Bus contracts on
  `com.clipman.Daemon` and `org.gnome.Shell.Extensions.clipman`,
  SQLite schema breaks, supported Python and GNOME Shell ranges,
  settings-key renames, the `~/.local/share/clipman/` data-dir
  layout, and the GTK3→GTK4 toolkit choice).
- `docs/maintaining.md` — the maintainer playbook: release flow,
  branch hygiene, Dependabot triage, GHAS handling, AUR/Snap channel
  notes.
- `ARCHITECTURE.md` — top-level walkthrough of the daemon ↔ extension
  split, the D-Bus surface, the SQLite store, and the popup window.
- `GOVERNANCE.md` — project governance, decision-making, and the role
  of ADRs.
- `docs/translating.md` — how to add a new locale and run the
  translation toolchain.
- `docs/dbus-api.md` — full reference for both D-Bus interfaces with
  signatures, semantics, and worked `gdbus call` examples.
- `docs/threat-model.md` — STRIDE-style threat model covering the
  clipboard surface, IPC, on-disk storage, and the update checker
  from ADR 0007.
- `docs/ci-cd.md` — workflow-by-workflow inventory of
  `.github/workflows/`, the release-pipeline DAG, the secrets matrix,
  and the SHA-pinning policy reference.
- `CONTRIBUTING.md` — refreshed contributor entry point that links
  the new docs together and points first-timers at the right place.

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
- **Stray root-level packaging manifest** (#18): the obsolete
  `com.clipman.Clipman.json` at the repo root used the pre-rename
  app-id and was not referenced anywhere.

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
