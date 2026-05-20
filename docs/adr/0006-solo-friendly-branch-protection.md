---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 6. Solo-friendly branch protection on `main`

## Context

Standard "best practice" branch protection assumes a team: required
review from a non-author, codeowners, etc. Clipman is currently a
solo-maintainer project. Requiring review-from-another-human would
either:

- block every merge until a reviewer is invited (defeats the
  purpose of CI gating), or
- be self-bypassed by the maintainer (defeats the purpose of the
  policy).

What the project *does* benefit from is **mechanical** gating: a
merge cannot land if the test suite, linters, secret scanner,
dependency-review scanner, or CodeQL ratchet fail. Those checks are
identity-blind and impossible to self-approve.

## Decision

Branch protection on `main` is configured as follows:

- **Required status checks** (must all be green to merge):
  - `Tests (3.10)` / `Tests (3.11)` / `Tests (3.12)` — full pytest
    matrix across supported Python versions.
  - `ruff` — lint gate.
  - `shellcheck` — gates `install.sh`, `uninstall.sh`,
    `launcher.sh`.
  - `gitleaks` — secret scanner.
  - `Dependency review` — flags newly introduced vulnerable
    dependencies.
  - `Analyze (python)` and `Analyze (javascript)` — CodeQL, with
    the baseline-ratchet from ADR 0002 enforced as a step inside
    each.
- **Require branches to be up to date before merging** — yes.
- **Require linear history** — yes. No merge commits on `main`.
  PRs are squashed or rebased.
- **No force-push** to `main`.
- **No deletions** of `main`.
- **Require conversation resolution before merging** — yes.
- **Require pull request reviews before merging** — **NO** (single
  maintainer; would either block everything or be vacuously self-
  approved).
- **Restrict who can push** — administrators only (the maintainer).
  Dependabot uses GitHub-managed permissions for its bump PRs and
  still has to clear all of the above checks.

The `security-baseline` branch has its own protection enforced by the
`baseline-guard.yml` workflow (ADR 0002): any push by a non-bot
actor is auto-reverted and surfaces an issue.

## Consequences

**Positive**

- Every merge to `main` is gated on a non-trivial battery of
  automated checks that the maintainer cannot bypass without
  explicitly disabling protection.
- Linear history keeps `git log` and `git bisect` clean, which
  matters disproportionately for a small project with no dedicated
  release engineer.
- The policy is honest: it doesn't pretend to enforce reviewer
  independence that doesn't exist, so the team isn't trained to
  rubber-stamp.

**Negative / trade-offs**

- **No second pair of eyes** is enforced. The maintainer is
  responsible for self-review discipline (e.g., reading the diff
  in the PR tab before merging, not from local working tree). Once
  a co-maintainer joins, this ADR should be superseded with one
  that flips on `Require pull request reviews` and codeowners.
- **Stale-PR friction.** "Branch up to date" + linear history means
  rebasing PRs after every merge. With Dependabot's weekly cadence
  this is a few rebases per week. Acceptable.
- **No emergency bypass.** If a required check is broken (e.g.,
  CodeQL infra outage), the maintainer must either fix the check
  or temporarily disable the protection rule to merge a hotfix —
  there is no "admin override" toggle on the merge button.
