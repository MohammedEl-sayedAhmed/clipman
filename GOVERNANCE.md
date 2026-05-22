# Governance

Clipman is a single-maintainer open-source project. This document
describes how decisions get made, where to raise concerns, and the
bar for joining the maintainer team.

## Maintainer

The project is currently maintained by a single individual:

- [MohammedEl-sayedAhmed](https://github.com/MohammedEl-sayedAhmed)

The maintainer holds the commit bit, owns the release process, and
is the final decision-maker on architecture, scope, and dependencies.

## Decision-making

- **Routine pull requests** (bug fixes, refactors, dependency bumps,
  small features): merged by the maintainer at their discretion, on
  the strength of green CI and code review. Lazy consensus — silence
  is approval.
- **Substantive architectural decisions** (the D-Bus contract,
  data-on-disk layout, supported platforms, supply-chain posture,
  release pipeline shape, third-party network calls): captured as an
  ADR in `docs/adr/` before or alongside the change that implements
  them. See `docs/adr/README.md` for the existing 10.
- **Versioning** follows the policy recorded in
  [ADR 0010](docs/adr/0010-versioning-policy.md): SemVer 2.0.0 with
  clipman-specific MAJOR triggers.

## Where to raise concerns

| Concern | Channel |
|---------|---------|
| Bug / feature / question / design idea | [GitHub Issues](https://github.com/MohammedEl-sayedAhmed/clipman/issues) (templates: bug, feature) |
| Open-ended discussion or RFC | [GitHub Discussions](https://github.com/MohammedEl-sayedAhmed/clipman/discussions) |
| Security vulnerability | Private channel per [SECURITY.md](SECURITY.md) — GitHub private advisory; never public issue |
| Code of Conduct violation | Same private channel as security reports |

## Escalation

If you feel a decision was made in error or a thread has stalled:

1. Re-raise in [GitHub Discussions](https://github.com/MohammedEl-sayedAhmed/clipman/discussions) with the context and proposed alternative.
2. If the concern involves the maintainer's conduct or a security
   issue, use the private channel in [SECURITY.md](SECURITY.md).

## Joining the maintainer team

The project is open to growing beyond a single maintainer. The bar:

- **Sustained contribution** over at least **6 months** — landing
  non-trivial PRs across more than one area of the codebase
  (`area:daemon`, `area:ui`, `area:extension`, `area:packaging`,
  `area:workflows`).
- **Quality bar** — PRs that ship green CI on first push are the
  norm, not the exception. Reviewing others' PRs counts.
- **Written sign-off** by the current maintainer.

There is no path that bypasses the current maintainer's written
sign-off. There is also no path that requires a specific number of
PRs — sustained quality matters more than count.

## Code of Conduct

This project follows the [Contributor Covenant v2.1](CODE_OF_CONDUCT.md).
The reporting channel listed there is the same private channel as
SECURITY.md.

## Changes to this document

Material changes (anything beyond a typo fix or link update) go
through a PR and are merged by the maintainer after the same
lazy-consensus window as any other PR.
