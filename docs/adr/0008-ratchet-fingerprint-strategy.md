---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 8. Ratchet fingerprint strategy

## Context

ADR 0002 introduced the CodeQL baseline ratchet: a PR fails CodeQL
only when it introduces a finding whose fingerprint isn't already in
the baseline. The first implementation used `<rule-id>:<file>:<line>`
as the fingerprint format. That worked until PR #15 — the first PR
that added many lines to a file that already had baseline findings.
The line numbers of the existing findings shifted, so the per-rule
fingerprints no longer matched the baseline, and the ratchet
reported every shifted finding as "new".

Worse: the ratchet also ran on push to `main` (with the same step),
so the merge of PR #15 made `main`'s ratchet step fail on its own
line shifts. That kept the `update-baseline` job (which lists
`needs: analyze`) from ever running, freezing the baseline at the
pre-PR-15 line numbers and inheriting the same false positives on
every subsequent PR.

We needed a fingerprint format that's stable across unrelated edits.

## Decision

Use the SARIF `partialFingerprints.primaryLocationLineHash` value
that CodeQL already emits per finding. The fingerprint key becomes
`<rule-id>:<partial-fingerprint-hash>` (file path and line number
drop out entirely). CodeQL's `primaryLocationLineHash` is a hash of
the location's surrounding snippet, so it survives line shifts
within a function.

Two implementation details landed alongside the format change in PR
#20:

- **Ratchet skips on push events**. On push to `main`, the analyze
  job only produces SARIF; `update-baseline` is the consumer.
  Running the ratchet on push, even with stable fingerprints,
  preserves the deadlock risk if a new edge case ever appears.
  Keeping ratchet PR-only makes the failure mode strictly
  PR-side, never main-side.
- **Schema bump**. `.github/security-baseline.json` carries
  `schema_version: 2` to signal the format migration. Loaders accept
  both legacy `rule:file:line` and new `rule:hash` entries
  side-by-side during the transition; the first push to main after
  the migration overwrites the legacy entries.

## Consequences

**Positive**

- PRs that just move code (refactors, top-of-file imports, large
  feature additions) no longer surface "new" findings for the
  shifted lines. The ratchet only flags genuinely-new findings.
- Update-baseline can no longer deadlock on its own line shifts.
- Behavior matches what GitHub's own Code Scanning UI uses to
  deduplicate findings across runs — same source of truth.

**Negative**

- `primaryLocationLineHash` isn't a documented API; it's a CodeQL
  implementation detail that could theoretically change in a future
  release. Mitigated by the fallback to `rule:file:line` if the
  partial fingerprint is missing, and by Dependabot keeping the
  codeql-action SHA pinned + current.
- Human reviewers reading the baseline can't tell from a fingerprint
  where the finding lives — they have to look it up via the
  workflow's annotation. The ratchet step still emits
  `::error file=...,line=...` annotations on new findings, so the
  PR-side workflow output is unchanged.

## References

- ADR 0002 (baseline-ratchet pattern) — the original design.
- PR #20 — the change set.
- CodeQL SARIF docs: <https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning>
