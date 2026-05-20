---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 3. Pin all third-party GitHub Actions to commit SHAs

## Context

GitHub Actions referenced by mutable tags (`@v4`, `@main`) are a known
supply-chain attack vector: a compromised maintainer account or a
force-pushed tag can swap the action's code without changing the
reference in this repo, and the malicious version runs with the same
permissions as the original.

OWASP's *CI/CD Security Cheat Sheet* and GitHub's own hardening guide
both recommend pinning third-party actions to a full 40-character
commit SHA. The trade-off is staleness: SHAs don't move, so security
patches in upstream actions are not picked up automatically.

## Decision

PR #8 ("CI/security baseline") and every workflow added since (PRs #9,
#16, #17) follow this rule:

- **All third-party actions are pinned to a full commit SHA.** First-
  party actions (`actions/checkout`, `actions/setup-python`,
  `actions/upload-artifact`, etc.) are also pinned, even though
  they're maintained by GitHub.
- **Each pin carries a `# v1.2.3` comment** so a human can tell at a
  glance which version is in use. Dependabot uses this comment to
  generate readable PR titles.
- **Dependabot is configured for `github-actions`** with a weekly
  schedule. Bumps come in as PRs (e.g. PR #10: `actions/labeler 5 →
  6.1.0`), get reviewed, run the full CI matrix, and merge only when
  green.
- **`step-security/harden-runner`** is the first step on every job
  (egress-policy: `audit`), so any unexpected outbound call from a
  compromised action would be logged.

## Consequences

**Positive**

- A compromised upstream tag cannot affect this repo until a
  Dependabot PR is reviewed and merged.
- The diff of a Dependabot bump shows exactly the SHA delta, making
  it easy to spot a wildly unexpected change of repository owner or
  scope.
- Hardened-runner audits give a forensic trail if something does
  slip through.

**Negative / trade-offs**

- **Staleness window.** Between an upstream security fix and the
  Dependabot PR merging, this repo is exposed to whatever the fix
  addresses. Mitigated by Dependabot's weekly cadence and by treating
  Dependabot PRs as priority work.
- **Visual noise.** Workflow YAML is uglier than `@v4`. The
  `# v1.2.3` comment is mandatory to keep it scannable.
- **Slightly higher review cost** for Dependabot PRs (must spot-check
  the SHA belongs to the claimed version), but this is a one-time
  check per bump and pays for itself the first time an upstream
  account is compromised.
