# Architecture Decision Records

This directory holds the project's architecture decision records (ADRs).
We use the [MADR](https://adr.github.io/madr/) format: Markdown with a
short YAML frontmatter (`status`, `date`, `deciders`) and three sections
(Context, Decision, Consequences).

New ADRs are numbered monotonically and named `NNNN-kebab-case-title.md`.
Once an ADR is `Accepted`, it is not edited in place — supersede it with
a new ADR that links back.

## Index

| #    | Title                                                                                       | Status   | Summary                                                                                                       |
|------|---------------------------------------------------------------------------------------------|----------|---------------------------------------------------------------------------------------------------------------|
| 0001 | [Record architecture decisions](0001-record-architecture-decisions.md)                      | Accepted | Adopt MADR-format ADRs under `docs/adr/` for non-trivial architecture and infra decisions.                    |
| 0002 | [Baseline-ratchet pattern for CodeQL findings](0002-baseline-ratchet-for-codeql.md)         | Accepted | Pre-existing CodeQL findings don't block PRs; new fingerprints do. Baseline lives on a guarded orphan branch. |
| 0003 | [Pin all third-party GitHub Actions to commit SHAs](0003-sha-pin-github-actions.md)         | Accepted | OWASP-aligned supply-chain hardening; Dependabot keeps SHAs current with weekly bumps.                        |
| 0004 | [PyPI publishing via OIDC trusted publishing](0004-pypi-trusted-publishing-oidc.md)         | Accepted | No long-lived PyPI token; the release workflow mints a short-lived OIDC token per job.                        |
| 0005 | [Encode paste keystroke choice as a D-Bus argument](0005-paste-mode-as-dbus-arg.md)         | Accepted | `SimulatePaste(s mode)` with try-with-arg + retry-without-arg fallback for v4 extension compatibility.        |
| 0006 | [Solo-friendly branch protection on `main`](0006-solo-friendly-branch-protection.md)        | Accepted | Required status checks + linear history + no force-push, but no required reviewers (single-maintainer repo). |
| 0007 | [In-app update-availability notifications](0007-in-app-update-notifications.md)             | Accepted | Daemon polls GitHub Releases anonymously once per day; in-app banner + dismissible per-version; default off on snap/flatpak. |
| 0008 | [Ratchet fingerprint strategy](0008-ratchet-fingerprint-strategy.md)                        | Accepted | Switch CodeQL ratchet from `rule:file:line` to SARIF `partialFingerprints`, and skip the ratchet on push to fix the update-baseline deadlock. |
| 0009 | [Weekly snap rebuild cadence](0009-snap-rebuild-cadence.md)                                 | Superseded by [0012](0012-snap-gnome-extension-and-all-channel-refresh.md) | Scheduled weekly rebuild publishes to `edge` automatically so the snap stays patched against Ubuntu archive USNs without coupling to a code release. |
| 0010 | [Versioning policy](0010-versioning-policy.md)                                              | Superseded by [0011](0011-versioning-policy-refresh.md) | SemVer 2.0.0; clipman-specific MAJOR triggers (D-Bus contract, SQLite schema break, dropped Python/GNOME Shell support, settings-key rename, data dir move, GTK3→GTK4). |
| 0011 | [Versioning policy refresh](0011-versioning-policy-refresh.md)                              | Accepted | Restates ADR 0010 on current facts: Ubuntu 24.04+, GTK 4 already shipped, `_version.py` rather than `__init__.py`, and the full four-method extension D-Bus contract. |
| 0012 | [Snap on the GNOME extension, with an all-channel weekly refresh](0012-snap-gnome-extension-and-all-channel-refresh.md) | Accepted | Supersedes ADR 0009: `core24` plus `extensions: [gnome]` moves the GTK stack into Canonical's content snap, and the weekly cron refreshes every channel — edge from `main`, beta/candidate/stable from the latest release tag. |

## Authoring a new ADR

1. Copy the structure of an existing record (e.g.
   `0001-record-architecture-decisions.md`).
2. Pick the next free number and a short kebab-case slug.
3. Open the PR with the ADR alongside the change it documents — that's
   the whole point of keeping them in-repo.
4. Once merged, add a row to the index above.
