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

## Adversaries

- **Local non-clipman processes running as the same UID.** Anything
  on the session bus can call `NewEntry` to inject fake clipboard
  content, or `Quit` to terminate the daemon. This is the design;
  the session bus is the trust boundary, not a defence.
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

- **Incognito mode** — pauses recording entirely (toggle from the
  popup status bar).
- **Sensitive-data detection** — regex heuristics for passwords,
  tokens, npm tokens, private keys, connection strings, SSH keys.
  Detected entries auto-clear from clipboard 30 seconds after copy.
- **Restrictive on-disk permissions** — data dir `0o700`, image
  files `0o600`. Standard `umask` regressions can't relax these
  because clipman explicitly `chmod`s the paths.
- **Path-traversal validation** on every image path before file
  I/O (`_safe_image_path` resolves and confirms containment under
  `IMAGES_DIR`).
- **Backup-import hardening** — schema integrity check, SQLite-URI
  injection rejected via URL-encoded `file:` URIs, triggers and
  views rejected, image magic-byte validation (PNG, JPEG, GIF, BMP,
  WebP).
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
- **D-Bus name-squatting by a malicious GNOME extension.** The
  session bus grants well-known names on a first-come basis;
  clipman does not attempt to detect impersonation beyond its own
  `NewEntry` payload validation.
- **Sandboxed-app clipboard** under Flatpak/Snap confinement —
  whether the host clipboard is readable inside another app's
  sandbox is a question for that sandbox's policy, not clipman's.

## Reporting

Found something concrete? See [SECURITY.md](../SECURITY.md) —
private GitHub Security Advisories, never a public issue.
