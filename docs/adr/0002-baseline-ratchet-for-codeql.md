---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 2. Baseline-ratchet pattern for CodeQL findings

## Context

CodeQL's `security-and-quality` suite surfaces ~18 informational
findings on `main` (best-effort `except: pass` blocks, cyclic imports,
module-level prints). They are intentional and not defects.

Without intervention these findings appeared as Copilot Autofix
annotations on every PR's *Files changed* tab, including PRs that did
not touch the affected files. This drowned out any *new* finding a PR
might introduce and trained reviewers to ignore the annotations
altogether — exactly the failure mode the scanner is meant to prevent.

Options considered:

1. **Dismiss each finding individually** via the GitHub Security UI.
   Loses provenance, scales poorly, and per-finding dismissals don't
   re-trigger if the rule version changes.
2. **Rule-level suppression** (e.g. ban the rule from the suite).
   Too coarse: a future genuine `py/empty-except` regression would
   also be silenced.
3. **A baseline-ratchet**: persist a fingerprint set of findings that
   exist on `main` and fail a PR only if it adds fingerprints not in
   that set.

## Decision

Implement the baseline-ratchet (option 3) with three pieces:

- **`.github/security-baseline.json`** lives on a dedicated orphan
  branch `security-baseline`. Fingerprint format:
  `<rule-id>:<path>:<startLine>`. Stored as a sorted list for
  deterministic diffs.
- **`.github/workflows/codeql.yml`** — the existing `analyze` job
  gains a `Ratchet` step that parses SARIF, compares against the
  baseline, and fails iff `current - baseline ≠ ∅`. A new
  `update-baseline` job runs on `push: main`, rebuilds fingerprints
  from the fresh SARIF, and commits the refreshed baseline back to
  the `security-baseline` branch as `github-actions[bot]`.
- **`.github/workflows/baseline-guard.yml`** — triggers on
  `push: security-baseline`. If the actor is not
  `github-actions[bot]`, the workflow auto-reverts the push and opens
  a labeled (`type:security`, `priority:high`) issue. Without this,
  anyone with write access could silently zero out the baseline.

Pre-existing findings remain visible in the Security tab. The ratchet
only governs PR pass/fail.

## Consequences

**Positive**

- New CodeQL findings introduced by a PR are flagged in the
  *Files changed* tab and block the merge.
- Pre-existing findings stop generating annotation noise on unrelated
  PRs.
- The baseline cannot be tampered with silently — the guard workflow
  reverts and surfaces the attempt.

**Negative / trade-offs**

- **Line-drift fragility.** Fingerprints encode line numbers, so an
  unrelated edit above an existing finding shifts the line and looks
  like a "new" finding. Mitigation: `update-baseline` refreshes the
  baseline as soon as the line-shifting PR merges, so subsequent PRs
  rebase to pick up the new lines. In practice this means the first
  PR after a refactor may need a rebase, not a code change.
- The fingerprint format is internal to this repo; if CodeQL changes
  its SARIF schema in a way that affects rule IDs or paths, the
  baseline becomes wrong en masse and must be rebuilt by running the
  `update-baseline` job manually.
- Per-matrix runs (Python, JavaScript) each see the *full*
  multi-language baseline, which means a Python ratchet step shows
  "resolved" entries that are JS-only. This is informational and was
  deemed acceptable to keep the workflow simple.

Supersedes nothing; ADR 0003 (SHA-pinning) and 0006 (branch
protection) reinforce the same posture from different angles.
