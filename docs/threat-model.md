# Threat model

A lightweight one-pager covering what clipman is trying to protect,
from whom, and what it deliberately doesn't try to defend against.

This is not a formal STRIDE matrix. Vulnerabilities found in code
should still be reported through the private channel in
[SECURITY.md](../SECURITY.md).

## Assets

| Asset                | Sensitivity                                        | Location                                                       |
| -------------------- | -------------------------------------------------- | -------------------------------------------------------------- |
| Clipboard contents   | high (passwords, tokens, recovery codes)           | in-memory + history DB                                         |
| History database     | high (transitive — contains past clipboard)        | `~/.local/share/clipman/clipman.db` (SQLite WAL)               |
| Image files          | medium                                             | `~/.local/share/clipman/images/`                               |
| Daemon D-Bus surface | medium (injection + control vector)                | session bus, `com.clipman.Daemon`                              |
| Extension D-Bus surface | high (keystroke synthesis and window focus inside the compositor) | session bus, `org.gnome.Shell.Extensions.clipman`       |

## Adversaries

- **Local non-clipman processes running as the same UID.** Anything
  on the session bus can call the daemon's `NewEntry` to inject fake
  clipboard content, or `Quit` to terminate the daemon. This is the
  design; the session bus is the trust boundary, not a defence. The
  extension's methods are different: they can type keystrokes and
  move focus, which Wayland denies to normal apps, so they accept
  calls only from the connection that owns `com.clipman.Daemon`.
- **Malicious GNOME Shell extensions.** Extensions run inside the
  Shell's gjs process and can talk to anything on the session bus.
  A malicious extension could read the daemon's D-Bus surface or
  impersonate the clipman extension if our extension isn't loaded.
- **Network attackers on the update-check path.** Relevant only for
  the single daily egress: anonymous
  `GET https://api.github.com/repos/MohammedEl-sayedAhmed/clipman/releases/latest`.
  See [ADR 0007](adr/0007-in-app-update-notifications.md).
- **Co-tenants on the same UID.** Out of scope; same OS-level trust
  boundary as the daemon.

## Mitigations in place

- **Incognito mode** — pauses recording entirely (the eye button in
  the popup's header bar, or Preferences → Privacy).
- **Sensitive-data detection** — matches known secret shapes: vendor
  API tokens (npm, GitHub, AWS and others), private keys, JSON Web
  Tokens, URLs with a password inside (connection strings), labelled
  values such as `PASSWORD=…`, Authorization headers, Luhn-valid card
  numbers and TOTP seeds. Public keys are not flagged. Detected
  entries are masked and removed from the history after a
  configurable delay (default 30 seconds). Not covered: a bare
  password with no label is stored as an ordinary clip
  ([#313](https://github.com/MohammedEl-sayedAhmed/clipman/issues/313)),
  and the system clipboard itself is not cleared
  ([#314](https://github.com/MohammedEl-sayedAhmed/clipman/issues/314)).
- **Restrictive on-disk permissions** — data dir `0o700`, database
  and image files `0o600`. Standard `umask` regressions can't relax these
  because clipman explicitly `chmod`s the paths.
- **Path-traversal validation** on every image path before file
  I/O (`_safe_image_path` resolves and confirms containment under
  `IMAGES_DIR`).
- **Backup-import hardening** — a backup is checked in a private copy
  before it can replace the history: `PRAGMA integrity_check`, the
  required columns, no triggers, views or virtual tables, and
  `trusted_schema=OFF`, because the file is untrusted. Image paths are
  sanitised, SQLite-URI injection is rejected via URL-encoded `file:`
  URIs, and the live database is replaced by a single rename only
  after every check passes.
- **Image signature check** — when an image is copied, it is stored
  only if it starts with a PNG, JPEG, GIF, BMP or WebP signature. The
  BMP and WebP checks look only at the first bytes (`BM`, `RIFF`), so
  they are loose, and a restored backup's images are not checked
  ([#335](https://github.com/MohammedEl-sayedAhmed/clipman/issues/335)).
- **Parameterised SQL** throughout — no string concatenation into
  queries.
- **No `shell=True`** — every subprocess invocation uses an argument
  list.
- **Update endpoint privacy** — single anonymous `GET`, no body,
  params, cookies, or identifiers, 5-second timeout. Default ON for
  source / PyPI / AUR installs, default OFF for snap / flatpak
  (their package manager auto-refreshes). See
  [ADR 0007](adr/0007-in-app-update-notifications.md).
- **Supply-chain posture** — SHA-pinned third-party GitHub Actions
  ([ADR 0003](adr/0003-sha-pin-github-actions.md)), PyPI publish via
  OIDC trusted publishing
  ([ADR 0004](adr/0004-pypi-trusted-publishing-oidc.md)), CodeQL
  with a baseline-ratchet pattern
  ([ADR 0002](adr/0002-baseline-ratchet-for-codeql.md),
  [ADR 0008](adr/0008-ratchet-fingerprint-strategy.md)), Dependabot
  covering `pip` and `github-actions`, gitleaks secret scan, OpenSSF
  Scorecard.

## Out of scope

- **Kernel-level keyloggers / eBPF taps** running as the same UID.
  If the attacker is already in the user's session at that level,
  clipman cannot protect against them.
- **Physical access** to an unlocked machine.
- **Cold-boot / offline disk forensics.** clipman does not assume
  full-disk encryption.
- **D-Bus name-squatting.** The session bus grants well-known names
  on a first-come basis. A process that owns `com.clipman.Daemon`
  before the daemon starts receives every clipboard text the
  extension forwards, and is the caller the extension trusts. The
  daemon refuses to start when the name is already owned; nothing
  else detects a squatter.
- **Sandboxed-app clipboard** under Flatpak/Snap confinement —
  whether the host clipboard is readable inside another app's
  sandbox is a question for that sandbox's policy, not clipman's.

## Reporting

Found something concrete? See [SECURITY.md](../SECURITY.md) —
private GitHub Security Advisories, never a public issue.
