# Changelog

All notable changes to Clipman are documented in this file.

## [Unreleased]

### Added — GNOME Shell 51 support

- The Shell extension (v9) now declares support for GNOME Shell 51. The
  one API the extension used that Shell 51 removed is
  `Clutter.get_default_backend()`; the virtual-keyboard lookup now falls
  back to `global.stage.context.get_backend()`, the replacement the Shell
  itself has used since 48. Everything else the extension touches
  (`Meta.Selection` `owner-changed`, `St.Clipboard`, the virtual-keyboard
  seat API, `Gio.DBusExportedObject`, and `Meta.Window.hide_from_window_list`)
  is unchanged in 51. Update the README/ADR support window to GNOME Shell
  45–51. The v9 zip for e.g.o. is built separately (manual upload).

### Fixed — snippet rows lost their icon on GNOME 48+

- Snippet rows used `emblem-documents-symbolic`, which upstream
  adwaita-icon-theme removed in 48.0 (it existed 42–47). On GNOME 48+
  the row fell back to a broken-image placeholder. Use
  `x-office-document-symbolic`, the same document-with-lines glyph that
  upstream kept, present across the whole 42–51 range.

### Added — developer tooling

- `scripts/deps.sh`: one manifest of system packages (`runtime`, `test`,
  `lint` sets; apt, dnf, pacman). `install.sh` and CI read it; the apt
  list used to be copied by hand into `install.sh`, `test.yml` and
  `release.yml`.
- `scripts/dev-setup.sh`: one-command bootstrap. Installs the system
  packages, creates `.venv` with `--system-site-packages`, installs the
  `dev` extras and the git hooks.
- `scripts/dev.sh`: task runner (`test`, `lint`, `check`, `screenshot`,
  `hooks-test`, …) with an optional `Makefile` wrapper. `dev.sh test` is
  exactly what CI runs.
- `lint`, `test` and `dev` extras in `pyproject.toml` (ruff pinned at
  0.15.13, pytest, PyGObject, dbus-python).

### Fixed — CI ran fewer tests than it reported

- The release workflow's test job installed the GTK 3 typelibs, set no
  `CLIPMAN_REQUIRE_GTK4` and ran without xvfb, so the widget tests were
  skipped on the release-gating run. It now runs the same three steps
  as `test.yml`.
- CI installed `pydbus`, but the app imports `dbus` (dbus-python), so
  `clipman.app` failed to import under the matrix interpreter and
  `test_app.py` skipped (8 tests). The `test` extra installs dbus-python.
- `test_keybindings.py` probed `gi.repository.Gdk` as an attribute,
  which only exists once another module has imported Gdk, so it skipped
  (10 tests) depending on import order. It now imports the submodule.
  Every CI run had reported `OK (skipped=18)`.
- The `toggle` smoke test in `test_entry_point.py` now runs without a
  display and against a dead session bus, so it fails fast instead of
  starting the daemon, and cannot toggle a developer's real one.
- `scripts/install-hooks.sh` no longer blocks on `read` when there is
  no terminal and, without one, only replaces a foreign
  `core.hooksPath` when `--replace` is given.

### Fixed — PyPI and AppImage entry points

- `pip install clipman-clipboard` produced a `clipman` command that failed
  with `ModuleNotFoundError`: the console script pointed at
  `clipman.clipman:main`, which did not exist. The entry point now lives in
  `clipman.cli` (`clipman`, `clipman toggle`, `clipman --version`,
  `python -m clipman`); the checkout script `clipman.py` is a thin shim.
- The wheel and sdist did not include `clipman/style.css`, so a pip install
  would crash on its first window. It is declared as package data, and a
  new CI job builds the wheel, installs it into a clean venv and runs the
  entry point.
- The release pipeline runs the same wheel check before it publishes to
  PyPI, and fails if the wheel does not report the tag's version.
- `scripts/bump-version.sh` now regenerates `aur/.SRCINFO` too. Without
  it, the release pre-flight and two tests failed on every version bump.
- The AppImage job is removed. It passed the wheel by a relative path
  that never resolved, hid the failure behind a warning, and so no
  release ever had an AppImage, though the release notes listed one. Even
  when built, it could not start, because the bundled Python cannot see
  the system's GTK bindings. #319 tracks a real, self-contained AppImage.
- Releases publish the snap to stable, candidate and beta together, and
  the weekly snap refresh refuses to rebuild an older tag onto a store
  channel that already holds a newer version, so a half-finished release
  can no longer roll stable back. Its publishing runs no longer share a
  concurrency group with push builds, which could cancel a pending
  weekly publish.
- `setuptools>=77`: the PEP 639 license string needs it, and builds
  without isolation failed on 68 to 76.

### Fixed — sensitive-data detection deleted ordinary clips

- The old rule flagged any single word of 8 to 128 characters that mixed
  three character classes. That covered most URLs, file names with
  digits, timestamps and version strings. Those clips were masked and
  then deleted for good after 30 seconds. On a benchmark of 552 everyday
  clips it flagged 229. It also caught no card numbers, although the
  Preferences text promised it would.
- Detection now lives in `clipman/sensitive.py` and only matches known
  secret shapes: vendor tokens with a unique prefix, private and SSH
  keys, JSON Web Tokens, URLs with a password inside, labelled values
  such as `PASSWORD=...`, `Authorization` headers, card numbers that pass
  Luhn, TOTP seeds and a few command lines that take a password inline.
  On the same benchmark it flags 0 of 552 everyday clips and catches 129
  of 165 secrets. A bare password with no label is not detected on
  purpose: it looks the same as a Wi-Fi name or a licence key.
- New Privacy switch "Auto-clear sensitive clips" (on by default). When
  off, detected clips stay masked but are never deleted.
- The benchmark corpus ships as `tests/sensitive_corpus.py` and
  `tests/test_sensitive.py` asserts zero false positives on it.
- Ordinary code was still flagged, and so deleted 30 seconds after the
  copy: a secret-named key followed by code (`token = self.get_token()`,
  `api_key = config.api_key`, `SECRET_KEY = os.environ.get(...)`), CSS
  class names and names such as `sk-prod-cluster-01`, and
  `curl -u "$USER:$TOKEN"`. A labelled value that reads as code (a call,
  an index, a dotted name, an `@name` reference) is no longer a secret,
  and an `sk-` key needs a key-length body.
- SSH public keys and Stripe publishable keys (`pk_live_`) are no longer
  treated as secrets: they are meant to be shared, and flagging one
  deleted it right after the user copied it to paste somewhere.
- Newly caught: `DB_PASS=`-style labels, `sshpass -p`, and Discord
  webhook URLs.
- One large clip could freeze the daemon: 64 KB of `sk-` took about 19 s
  to check, and a long line full of `http`, `curl` or `mysql` 3 to 4 s,
  on the main loop. Every pattern is bounded now, and those clips take
  about 30 ms, the same as plain text.
- A pinned sensitive clip was purged anyway. A pin now keeps it, and its
  row shows no countdown.
- "Purge sensitive entries now" did nothing while auto-clear was off,
  which is exactly when it is needed. It now removes every sensitive
  entry, pinned or not.
- Two different clips copied within 100 ms kept only the first. After a
  busy moment, queued copies arrive back to back, so real clips were
  lost. Only the same content repeated that fast is dropped now.

### Fixed — daemon start-up and incognito on the bus

- A second daemon was never refused the `com.clipman.Daemon` name. It
  waited in the bus queue, and the code that should have logged and
  quit never ran. The name is now requested with `do_not_queue`, so a
  second daemon exits at once. A new test starts two daemons on a
  private bus and checks that the second one is refused.
- When the session bus could not be reached, the error escaped the
  start-up code as a traceback while the window kept the process
  alive. The daemon now logs the error and quits.
- Incognito mode also pauses the GNOME Shell extension (contract v8) so
  clips never cross the bus while it is on. The daemon calls
  `SetPaused` when incognito changes, at start-up, and again whenever
  the extension reappears. Older extensions ignore the call.
- Reading an image from the clipboard ran `wl-paste` on the main loop
  and could freeze the popup for up to five seconds. It now runs on a
  background thread and stores the result on the main loop.
### Fixed — storage and update check

- A `max_entries` setting stored as a float string (for example
  `500.0`) made every copy fail with `ValueError`. The value is now
  parsed the same way the Preferences pane reads it.
- The database file itself was created with the process umask (0644
  on most systems); only the directory and the WAL side files were
  0600. It is now clamped to 0600 on every start, as the FAQ said.
- The update check wrote its result to SQLite from a background
  thread. It now hands the result to the GLib main loop first, so all
  database access stays on one thread.
- Comparing a release tag that is not a valid version (for example
  `1.2.3-hotfix`) against a valid one could raise inside the update
  check. Both sides now fall back to the same simple comparison.
- `update_entry_text` had no caller and could break the unique hash
  constraint; removed. `get_latest_text` returns the newest text clip
  regardless of pins, for the `${clipboard}` snippet token.
- Restoring a backup could lose the whole history. Every restore first
  saved the current history as `clipman.db.bak`, so restoring that `.bak`
  (the rollback the dialog offered) overwrote it before reading it, and
  retrying a failed restore replaced it with the broken history. Safety
  copies now get their own names (`clipman.db.<time>.bak`), are never
  overwritten, and the three newest are kept.
- A restore that failed had already replaced the history. The backup was
  checked only for an `entries` table, then copied over the live file,
  and the steps that could fail ran afterwards: a backup with missing
  columns, a virtual table or damaged pages left a history the app could
  not use, and recording stopped. Restores now check, migrate and clean
  a copy first (integrity check, required columns, no triggers, views or
  virtual tables, the backup's own SQL functions switched off), and swap
  it in with one rename. A failure changes nothing.
- Choosing the live database as the restore source closed the database
  connection until the next restart. It is refused now, and so is
  exporting over the live database or its `-wal`/`-shm` files.
- A restore deletes the image files of the history it replaced.
- An exported backup was readable by other users while it was being
  written. It is created private before any data lands in it.
- A `max_entries` of 0 or -1 (from a restored backup, say) deleted every
  new clip, and `inf` made every copy fail. The value is kept inside the
  range Preferences offers, 50 to 5000.

### Fixed — popup window

- The Images tab could show "no images" while its badge counted some:
  the list loaded the 200 newest clips of any type and filtered them in
  Python. The Text and Images tabs now ask the database for that type.
- The `${clipboard}` snippet token expanded to the top *pinned* clip,
  not the newest one. It now uses the newest text clip.
- The "Snap notes" button opened a page that did not exist. It now
  opens the install section of the README.
- After the popup copied a clip, the monitor skipped the next clipboard
  change with no time limit, so it could swallow a real copy made
  later. The skip now expires after two seconds.
- Links from the popup go through the same http(s)-only opener as the
  Preferences window. The "Reveal folder" button uses its own helper
  that only opens folders that exist.
- Paste through the GNOME Shell extension: a failed focus restore no
  longer aborts the paste; an old extension that rejects the mode
  argument gets the no-argument call that ADR 0005 promised; and when
  the extension refuses both calls the popup comes back with a
  "Couldn't auto-paste" dialog instead of falling back to wtype, which
  cannot inject keys on Mutter.
- Masked rows say only "Sensitive" when "Auto-clear sensitive clips"
  is off, instead of counting down to a purge that will not happen.
- After the first open, the daemon kept one CPU core at 100 % until
  logout (since 1.2.0). The popup deferred the search-box focus with an
  idle callback that returned True, so it ran again forever, and every
  show added another one. The loop also kept pulling focus back into the
  search box, which broke the keyboard: Enter did nothing. The focus now
  runs once, and hiding the popup cancels a pending one.
- Down from the search box now moves into the list. While typing, the
  focus sits on the entry's inner text field, so the old check never saw
  the search box as focused.
- Delete and P with nothing selected no longer act on the first row,
  which could delete a pinned clip without asking. Only Enter falls back
  to the first row.

### Fixed — packaging and release scripts

- `scripts/update-aur.sh` wrote a hard-coded `.SRCINFO` that listed
  `gtk3` and no `libadwaita`, so every release pushed a GTK 3 dependency
  list for a GTK 4 app to AUR. It now builds `.SRCINFO` from `PKGBUILD`
  and also refreshes the tarball hash in the Flatpak manifest.
  `--print-srcinfo` prints the result for the tests.
- `aur/PKGBUILD` and `aur/.SRCINFO` still carried the 1.0.6 tarball hash
  (and `.SRCINFO` said 1.1.0). Regenerated for 1.2.1.
- `aur/PKGBUILD` installed the systemd unit with the literal
  `CLIPMAN_PATH_PLACEHOLDER` in `ExecStart`. It now gets the same path
  substitution as the desktop file.
- `scripts/bump-version.sh` adds an empty `<release>` entry to both
  metainfo files and prints the release steps from AGENTS.md (release
  PR, tag through the GitHub API, then `update-aur.sh`) instead of
  `git push --tags`, which the pre-push hook rejects.
- The Flatpak manifest lacked `--own-name` for `com.clipman.Daemon` and
  `com.clipman.Clipman`, so the daemon could not take its bus names
  inside the sandbox.
- The snap no longer copies the whole checkout (docs, tests, CI files)
  into the package; only the runtime files, the licence and the notice
  ship.
- New `tests/test_release_metadata.py`: the version must be the same in
  every packaging file, `.SRCINFO` must match `PKGBUILD`, and AUR and
  Flatpak must pin the same tarball hash.

### Fixed — release workflow and CI

- The GitHub Release was marked Latest even when the PyPI or Snap
  publish job had failed; the AUR push then followed. The release job
  now needs every publish job to succeed. A dispatch re-run skips wheels
  that are already on PyPI instead of failing.
- The `.deb` and `.rpm` declared GTK 3 dependencies (`gir1.2-gtk-3.0`,
  `gtk3`) for a GTK 4 app. They now depend on GTK 4 and libadwaita.
- The pre-flight check compared the tag with `pyproject.toml` and the
  snap only. It now checks every file that carries the version
  (`_version.py`, `CITATION.cff`, `PKGBUILD`, `.SRCINFO`, the Flatpak
  manifest, both metainfo files) and requires a matching CHANGELOG
  section.
- The AUR job checked out the default branch on a manual dispatch, so it
  could publish main's files under a release tag. It checks out the tag.
- The dispatch input `tag` was expanded straight into a shell script; it
  is now read through the environment and must look like `vX.Y.Z`. The
  same env pass-through is used in the baseline guard's issue body and
  the branch-cleanup job.
- The apt steps in the release, lint and extension-bundle jobs now have a
  step timeout and retries, like the test job.
- The security-baseline update raced when two merges landed close
  together: the loser's push was rejected and the baseline went stale.
  It now rebases and retries, and keeps the remote baseline when that
  one comes from a newer commit.
- `snap-refresh` fails clearly when the latest release tag cannot be
  resolved, instead of risking a build of main on the stable channel.
- ruff also lints `scripts/` and the root `clipman.py`. Two jobs moved
  from `ubuntu-latest` to the pinned `ubuntu-24.04`. Issue templates use
  the `type:bug` and `type:feature` labels that `labels.yml` defines.
- The release logic moved out of the workflow files into scripts that
  the test suite runs:
  - `scripts/snap-plan.sh` decides what the snap refresh builds and
    where it publishes. Ten scenario tests cover it, including a store
    that is ahead of the latest release and a failed release lookup.
  - `scripts/release-preflight.sh` is the version check. The tests run
    it on a freshly bumped copy, so a release PR that would fail the
    pre-flight fails CI first.
  - `scripts/wheel-smoke.sh` is now shared by the pull-request
    `package` check and the release. The release step piped `tar` into
    `grep -q`, which can fail under `pipefail`; the script lists to a
    file first.

### Fixed — install and uninstall scripts

- `install.sh` replaced GNOME's whole "toggle message tray" shortcut
  list with `['<Super>m']` to free Super+V. It now removes only
  `<Super>v` and keeps the user's other keys. The original list is saved
  so `uninstall.sh` can put it back; before, uninstall reset the key to
  GNOME's default.
- `install.sh` installed the icon but no desktop entry, so the Clipman
  window had no name or icon in the dash and in Alt+Tab. It now installs
  `com.clipman.Clipman.desktop` (with the install path filled in) into
  `~/.local/share/applications`; `uninstall.sh` removes it.
- A fresh `install.sh` never turned the extension on (#1). While the
  Shell runs, `gnome-extensions enable` refuses an extension that the
  Shell did not find at login, and the error was hidden. So the extension
  stayed off after the next login too, and nothing was recorded. When the
  Shell refuses, the installer now writes `enabled-extensions` (and takes
  the extension out of `disabled-extensions`), so it starts at the next
  login. It also warns when extensions are turned off in GNOME, or when
  the extension does not list the running Shell version.
- Running `install.sh` again reset a shortcut the user had changed back
  to Super+V. It now keeps it, and frees Super+V from the message tray
  only when Clipman uses Super+V.
- A checkout path with a space, `&` or `|` broke the service, the desktop
  entry and the shortcut, or stopped the install at `sed`, and the
  installer still reported success. The path is now quoted for each file.
  A path that systemd or a desktop entry cannot hold (quotes, a
  backslash, `$`, `%`, a backtick or a control character) stops the
  install with a clear message, before any of Clipman's files or
  settings are written.
- On a desktop without GNOME, `install.sh` stopped at the first GNOME
  setting, before the service step. It now skips the GNOME steps, says
  so, and still installs the service.
- `uninstall.sh` left a daemon started by hand running, and it kept
  writing into the files that had just been removed. It now asks the
  daemon to quit over D-Bus.
- `uninstall.sh` failed without a terminal: the question about the data
  hit end of input under `set -e`. It now keeps the data then, and says
  where it is.

### Fixed — git hooks

- The trailer-identity check never ran. It read the output of
  `git interpret-trailers --parse` as a tab-separated pair, but that
  command prints `Key: value`, so every trailer was skipped and the
  function always reported success. AI co-author trailers were still
  blocked, by the footprint scanner. The parser now splits on the first
  colon.
- With the check live, its old policy rejected every raw personal or
  work domain, which would have blocked outside contributors'
  `Signed-off-by` and `Reviewed-by` trailers. The repo's own test corpus
  requires those to pass. The policy now rejects only two things: an
  AI-assistant vendor domain, and a trailer whose display name borrows
  the maintainer's handle on an address that does not back it up.
- The push-URL check matched the allowlist as a substring of the whole
  URL, so a repo such as `attacker/<owner>-mirror.git` passed. It now
  compares the owner segment of the URL exactly, and falls back to the
  old check for remotes with no host, such as local paths.
- `.githooks/_test.sh` is clean under shellcheck, and `scripts/dev.sh
  shellcheck` now covers the hooks as well. The suite went from one
  failing case out of 43 to 51 of 51, with new cases for impersonation,
  an AI vendor domain and the push-URL owner match.
- The hooks blocked every outside contributor. `scripts/dev-setup.sh`
  installs them in every clone, and they allowed only the maintainer's
  identity. The account checks now run only in maintainer mode
  (`git config clipman.hooks.maintainer`, which `install-hooks.sh` sets
  from the clone's identity). A contributor's clone keeps just the
  AI-footprint checks.
- A new `Footprints` check runs on every pull request. It blocks AI-tool
  attribution in the commits (trailers, messages, added lines), the
  title and the description, with the same checks as the hooks, so the
  rule holds for contributors who never installed them.
- The pre-commit error told people to set their email to the
  maintainer's personal address, which the check then rejected as well.
  It now suggests the GitHub noreply form, and tells a contributor how to
  turn the account checks off.
- The push-URL check failed every push when the global git config had a
  URL rewrite rule for any other host, such as a work GitLab. It now
  checks only where the push really goes, after rewrites.
- In maintainer mode, a `gh` CLI logged in to an account outside the
  allowlist is now an error, not a warning, because gh may be the one
  doing the push.
- The test suite skipped the six corpus cases that describe a clone, and
  four of them disagreed with the hooks. Those cases now run through the
  real pre-commit and pre-push hooks in throwaway repos, next to twelve
  new cases: URL rewrites, the mode setting, trailer checks, and a commit
  made outside the hooks. CI runs the suite in the Lint workflow; 70 of
  70 pass.

### Fixed — translations and the snippets editor

- Translation extraction covered one file. `po/POTFILES.in` listed only
  `window.py`, so 155 of the 226 translatable strings never reached the
  template: the whole Preferences pane, every edge state and the
  snippets editor. All four modules are listed now and the template
  holds every string.
- New `scripts/dev.sh i18n` rebuilds the template through
  `scripts/gen-pot.py` and compiles any `po/*.po` into `locale/`. It
  extracts with `pygettext`, which ships with CPython, so regenerating
  needs no extra package; compiling needs `msgfmt`, which is now part
  of the `dev` dependency set. `install.sh` compiles catalogues too, so
  a source install picks up a language once one is contributed.
- `CONTRIBUTING.md` and `docs/translating.md` told contributors to
  write `from clipman import _`, which is the cyclic import the CodeQL
  gate rejects. Both now say `from gettext import gettext as _`, and
  the string counts and the `.mo` status they quoted are current.
- The snippets editor wrote an empty "New snippet" row as soon as
  "New" was pressed, so cancelling left it behind. "New" now opens an
  unsaved draft and nothing is written until Save, which stays
  insensitive until the name is filled in.
- Deleting a snippet asked nothing. It now confirms first, like
  clearing the history does.

### Fixed — test suite side effects

- Running the tests opened a file manager on the developer's desktop.
  An edge-state action reached the real `xdg-open` with a temp
  directory the test had already deleted, and another asked systemd to
  restart the real daemon. The widget tests now share a fixture that
  stubs the functions reaching outside the process, and two leaked
  child processes are gone with it.
- Every widget test built its window on an application that had not
  emitted `startup`, so each one logged a `Gtk-CRITICAL`. The shared
  fixture registers the application first. The suite is silent now.
- `test_sentinel_line_triggers_event` began with a dead block that read
  file descriptor 42 for real, so the test could hang or fail depending
  on what the runner had open. The block is gone.
- The last eight CodeQL alerts on `main` are fixed: seven `except …: pass`
  blocks became `contextlib.suppress` (a missing image file is fine) or
  a debug log, and one stray `pass` went with the dead test block.
- The suite could open and migrate the real
  `~/.local/share/clipman/clipman.db`. With `wl-paste` installed, the
  `toggle` smoke test fell through to a daemon start under the real
  `HOME`. `tests/__init__.py` now gives every run a scratch `HOME` and
  XDG folders before any test imports clipman, plus the in-memory
  GSettings backend, so no test can touch the user's history or GNOME
  settings. The smoke test also passes its own scratch `HOME`.
- Without `xvfb-run`, `scripts/dev.sh test` only warned, then ran the
  GTK tests on the desktop: windows stayed mapped on the live session,
  and one test wrote its clipboard. It now stops with an install hint.
  The tests never use Wayland, and use X11 only on a private server
  (`xvfb-run`, or `CLIPMAN_TEST_PRIVATE_DISPLAY=1`). Broadway also
  works.
- With no display at all, the suite crashed: `Adw.init()` succeeds
  without one, and the first widget segfaulted. The widget tests now
  skip, or fail with a clear message under `CLIPMAN_REQUIRE_GTK4=1`.

### Fixed — documentation that did not match the code

A sweep of every claim in the docs against the code. The corrections that
change what a reader would do:

- README documented a "Shift+Enter — copy without pasting" shortcut in
  two tables and sent people to it from the troubleshooting section. No
  such shortcut exists: Enter is handled with no modifier check.
  Troubleshooting now points at the Paste behaviour setting, which is
  the real answer for editor terminals.
- README told people to click a "+ Add" button to create a snippet and
  an "Edit snippets" button to open the editor. Neither label exists;
  the control is the "+" button in the header bar, shown only on the
  Snippets tab. README also listed a "Check now" button in the Updates
  pane that is not there.
- `docs/development.md` documented a `CLIPMAN_DATA_DIR` environment
  variable. Nothing reads it; the data directory is fixed.
- The site and the two LLM summaries told people to run
  `pipx install clipman-clipboard`. That produces a launcher which
  cannot start, because the GTK4 bindings are distro packages a plain
  virtualenv cannot see. They now use `--system-site-packages` and say
  why.
- Three release documents said to publish with `git push --tags`. The
  identity pre-push hook rejects a tag that points at one of GitHub's
  squash commits, so the tag has to be created through the GitHub API.
  The release checklist now walks through the release PR and the API
  call, and its rollback advice does the same.
- The release documents also listed the wrong files for
  `scripts/bump-version.sh` (naming `clipman/__init__.py`, which it has
  never touched, and omitting four it does), described the AUR push as
  a manual step that the pipeline has automated, pointed at two ADR
  filenames that do not exist, and named the wrong AUR remote.
- `docs/llms-full.txt` claimed FTS5 search, image storage under
  `blobs/`, and a daemon that refuses to start on loose permissions.
  Search is SQL `LIKE`, images live under `images/`, and the daemon
  repairs permissions rather than refusing.
- The AppImage instructions asked for `gir1.2-gtk-3.0` for a GTK 4 app.
- `CODE_OF_CONDUCT.md` opened with raw TOML that rendered as body text,
  and its reporting address was still the template's
  `[INSERT CONTACT METHOD]`, while `GOVERNANCE.md` said a channel
  existed. It now names the private advisory channel that
  `SECURITY.md` uses.
- The two AppStream metainfo files had drifted: one was missing the
  1.0.5 and 1.0.6 releases, and they disagreed on the date and summary
  of 1.0.4. Both now match the CHANGELOG.
- Counts and names that had gone stale: the test total and per-file
  breakdown, the edge-state count, the translation-template size, the
  light palette (warm stone, not Catppuccin Latte), the preferences
  widget (`Adw.Dialog`, not `Adw.PreferencesWindow`), the GNOME Shell
  range, the site's version strings, the sitemap dates, and the
  versions shown in the design mockups.
- `SECURITY.md` now states the support window, which the contributor
  guide requires it to carry. `docs/ci-cd.md` claimed a complete
  workflow inventory while missing two workflows and one secret.
- `pyproject.toml` gained per-version classifiers so the tested range
  is visible on PyPI. `requires-python` stays open at the top end, so a
  newer interpreter is still allowed to install.
- The README (also the PyPI page), both metainfo files, the snap, AUR,
  PyPI and citation descriptions, `llms*.txt`, the website and the
  threat model now describe only what the app does:
  - Features the GTK 4 port dropped are gone from the lists: inline
    edit, expand, one-click link open and the image hover preview
    (#310–#312). So are KDE, Sway and Hyprland support (#318), search
    over images and "fuzzy" search (#315, #317), accent presets (#316),
    and passwords or the clipboard being cleared (#313, #314). The
    README lists them under "Planned", with their issues.
  - Package installs were told to run `install.sh` from a git checkout,
    which set up the checkout instead of the package, and the PyPI
    steps used `pip install` (refused on Ubuntu 24.04+) and shortcut
    commands that wiped the user's other shortcuts. A new "Finish the
    setup" section gives tested steps for each package (#323 tracks a
    single command), and PyPI uses pipx.
  - The README's logo and links are absolute, so they work on PyPI (11
    were broken there).
  - libadwaita 1.5 is the stated floor, as the code needs, and the
    start-up check now enforces it (it accepted 1.4).
  - The GitHub Sponsors links led nowhere (there is no Sponsors
    listing) and are gone. The About page's PayPal link pointed at an
    unrelated profile; it now opens the maintainer's page.

### Added — two superseding ADRs

- **ADR 0011** supersedes ADR 0010. The versioning policy is unchanged,
  but four of its premises were stale: the Ubuntu baseline, the toolkit
  (GTK 4 shipped in 1.1.0), the file the bump script patches, and a
  D-Bus contract list missing two of the extension's four methods.
- **ADR 0012** supersedes ADR 0009. The snap moved to `core24` with the
  GNOME extension, so the GTK stack comes from Canonical's content snap
  instead of being restaged from the archive, and the weekly job now
  refreshes every channel rather than only edge.

### Security — GNOME Shell extension (metadata version 8)

- The extension's D-Bus methods (`SimulatePaste`, `MoveWindowToCursor`,
  `RestorePreviousFocus`) could be called by any process on the session
  bus, including through the Shell's own bus name. They could type a
  paste keystroke into the focused window or focus any window by title.
  Every method now accepts calls only from the connection that owns
  `com.clipman.Daemon`; other callers get `AccessDenied`.
- `MoveWindowToCursor` matched windows by title alone. It now requires
  the popup's `wm_class`, the daemon's pid and the title. Windows it
  hides from Alt+Tab on GNOME 49+ are shown again when the extension is
  disabled.
- New `SetPaused(b)` method: while paused the extension does not read
  the clipboard, so incognito can stop clips before they cross the bus.
- Lifecycle fixes: null-prototype recipe tables (a `__proto__` mode no
  longer throws), one virtual keyboard instead of one per paste,
  modifiers are always released, `disable()` clears every reference and
  cancels in-flight work, and the Alt+Tab/dash patches are installed
  only on GNOME 45 to 48 where the real API is missing.
- Clips longer than the daemon's 10 MB limit are no longer sent over the
  bus; delivery failures are logged.
- `scripts/extension-smoke.sh` checks the access rule on a real session.
- Docs: `docs/dbus-api.md` lists all four methods and version 8,
  `docs/threat-model.md` covers the extension surface.

### Fixed — paste and incognito in the GNOME Shell extension

- In the default `auto` paste mode, picking a clip into the default GNOME
  terminals typed Ctrl+V, so nothing was pasted. The terminal check
  matched part of the app ID, so `org.gnome.Terminal` (Ubuntu 24.04),
  `org.gnome.Ptyxis` (Ubuntu 26.04, Fedora) and `org.gnome.Console` were
  missed, while `st` matched System Monitor, Steam and JetBrains IDEs,
  which got Ctrl+Shift+V. Terminals are now matched by their whole app ID
  or its last dotted part.
- Incognito stopped pausing the extension after a screen unlock. The
  extension is re-enabled on every unlock, and it claimed its bus name
  before it knew who owned the daemon's name. So the daemon's `SetPaused`
  push was refused as coming from a stranger, and never retried. The
  extension now claims its name only once it knows the owner.
- Starting in incognito logged a false "denied SetPaused" security
  warning: the daemon pushed the pause before it owned its own bus name.
  It now pushes only after registering.
- The extension kept a reference to every popup window ever shown, until
  it was disabled, and its record of refused callers had no size limit.
  Both are bounded now.
- `scripts/extension-smoke.sh` stops before sending any keystroke when
  the installed extension is older than the access-controlled one, which
  would have typed real Ctrl+V into the focused window.
- `docs/dbus-api.md` and `ARCHITECTURE.md` described a `wtype` fallback
  that the daemon no longer uses, and the wrong deduplication rule.

### Changed — Snap packaging (#237, #238)

- The snap now uses the `gnome` extension: the GTK4/libadwaita runtime
  (GTK 4.18 / libadwaita 1.7) comes from Canonical's `gnome-46-2404`
  content snap instead of being staged from the Ubuntu archive. This
  removes the `libadwaita → libappstream → libcurl` dependency tail
  that made every curl security update trip the Snap Store's daily
  scan (three "outdated Ubuntu packages" emails in five weeks), shrinks
  the snap to ~13 MB, and hands GTK-stack security rebuilds to
  Canonical. Only `wtype` and the from-source `wl-clipboard` remain
  first-party payload.
- The weekly snap rebuild now refreshes every published channel —
  stable/candidate/beta are rebuilt from the latest release tag, edge
  from main — so store security notices self-resolve within a week
  with no manual action.

### Changed — CI

- `test.yml`, `lint.yml` and the release test job install system
  packages via `scripts/deps.sh` and run the suite via
  `scripts/dev.sh test`, so a local run and CI are the same command.
  The apt step is capped at four minutes; apt retries with a 30 s fetch
  timeout so a stalled mirror fails inside the cap. The last red run on
  `main` was an apt stall that consumed the whole job budget.
- The daily numbers refresh no longer opens a pull request. It used a
  personal access token to open and auto-merge one PR a day under the
  maintainer's name, which moved `main` every day, put every open pull
  request behind, and would stall when the token expired. It now commits
  the counters, the star chart and the downloads history to a separate
  `numbers` branch with the built-in token. The website and the README
  read them from there, and `NUMBERS_TOKEN` is no longer used.
- A new `Validate` lint job runs actionlint on the workflows (with
  shellcheck on every `run:` block), `appstreamcli validate` on both
  metainfo files, and `desktop-file-validate` on the desktop entry.
  `scripts/dev.sh validate` runs the same checks. It found two problems,
  both fixed here:
  - `com.clipman.Clipman.metainfo.xml`, which the AUR package installs,
    failed validation: its developer id had capital letters;
  - two file names in `release.yml` were unquoted.
- A new `e2e (headless GNOME Shell)` job runs Clipman the way a user
  meets it, in a headless GNOME Shell 46 with its own bus and home:
  - `install.sh` during a live session, then a new login;
  - the extension must be on, and a copy must reach the history;
  - `scripts/extension-smoke.sh` must pass;
  - the open and the hidden popup must stay idle;
  - `uninstall.sh`, without a terminal, must stop a daemon started by
    hand.

  Before, CI had no test of the extension or the installer, and the
  bugs fixed in #307 and #328 reached users. Against the old code, the
  job fails on each of them. `scripts/dev.sh e2e` runs it locally.

## [1.2.1] - 2026-08-22

A polish release driven by a full four-dimension audit (docs, code, UI,
repo meta): every public claim re-aligned with the shipped product, the
two GTK deprecations removed, the update banner made dismissable, and
the UI brought to full parity with the design mockups. Rebuilding the
snap also pulls the patched libcurl from USN-8651-1.

### Added — GNOME Shell 49 & 50 support (#186)

- The Shell extension (v7) now declares support for GNOME Shell 49 and
  50, covering Ubuntu 26.04 LTS. No code changes were needed: every API
  the extension touches was verified unchanged against the Shell 49
  headers and Mutter 50.0 (the 49/50 porting guides confirm none of the
  removals — Meta.Rectangle constructors, Clutter.ClickAction, the X11
  backend — intersect the extension's Wayland-native surface). On 49+
  the popup is additionally hidden from the dash and Alt+Tab via the
  supported `Meta.Window.hide_from_window_list()` API, which the code
  already feature-detected.

### Fixed

- **The update banner can now be dismissed** (#231). `updates.dismiss()`
  existed but nothing called it — the bare `Adw.Banner` has no dismiss
  control, so once a release was out the banner reappeared on every
  launch. The notice is now a custom banner row (icon · title/desc ·
  action · dismiss X) and the X persists the dismissal per version.
- Backup/restore use `Gtk.FileDialog` instead of the deprecated
  `Gtk.FileChooserNative`; thumbnails use `Gdk.MemoryTexture` instead of
  the deprecated `Gdk.Texture.new_for_pixbuf` (#229). Zero deprecation
  warnings in the test suite.

### Changed — UI parity with the design mockups (#231)

- Header and footer sit on the raised mantle surface; status-page icons
  are tinted per tone; privacy states (paused pill, incognito banner)
  use the mockup's lavender instead of warning amber; the search field
  rests recessed and raises on focus; image thumbnails get rounded
  corners; filter tabs left-aligned; Preferences gains an "In-popup
  shortcuts" reference group. README screenshots retaken from this
  build (`scripts/screenshot.py --theme/--incognito`).

### Documentation (#226, #230)

- Truth sweep: marketing-site install commands fixed (they referenced
  nonexistent v1.1.0 asset names), the privacy FAQ now accurately
  describes the optional once-daily update check, README/llms.txt
  describe the shipped preferences dialog/palettes/list implementation,
  test counts and support tables refreshed, `CITATION.cff` auto-bumped
  by `bump-version.sh`.
- New `AGENTS.md`: tool-agnostic working guide (workflow, verification
  recipes, platform gotchas, release chain) for AI-assisted development.

### CI (#227)

- Bot workflows use job-scoped token permissions, commit-SHA-pinned
  actions and the harden-runner first step (OpenSSF Scorecard
  Token-Permissions fix).

### Compatibility

Unchanged from 1.2.0 otherwise: Python 3.10–3.12, GNOME Shell 45–50,
Wayland. No D-Bus contract changes; no database migrations. The GNOME
Shell extension remains at v7 (no upload needed).

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
