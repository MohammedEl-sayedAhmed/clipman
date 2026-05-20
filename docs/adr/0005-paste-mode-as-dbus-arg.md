---
status: Accepted
date: 2026-05-20
deciders: MohammedEl-sayedAhmed
---

# 5. Encode paste keystroke choice as a D-Bus argument, not separate methods

## Context

PR #15 adds a user-facing setting for which keystroke the GNOME Shell
extension should synthesize when pasting:

| Mode | Behavior |
|------|----------|
| `auto` | Ctrl+V on most apps, Ctrl+Shift+V on terminals (existing behavior) |
| `ctrl-v` | Force Ctrl+V regardless of focus |
| `ctrl-shift-v` | Force Ctrl+Shift+V regardless of focus |
| `shift-insert` | Shift+Insert (X11/terminal convention — issue #7) |

Two interface designs were on the table:

1. **One method per mode**: `SimulatePaste()`, `SimulatePasteShiftInsert()`,
   `SimulatePasteCtrlV()`, ...
2. **One method, one argument**: `SimulatePaste(s mode)`.

Option 1 keeps each method's body trivial but multiplies the D-Bus
surface every time a new keystroke recipe is added. Option 2 keeps the
surface stable but introduces a backward-compatibility question: the
shipped extension (v4) exposes `SimulatePaste()` with no arguments, so
a new daemon calling `SimulatePaste('auto')` on an unupgraded
extension would raise `DBusException`.

## Decision

Use **one method with a string argument** (option 2).

- The D-Bus interface becomes `SimulatePaste(s mode)`. Valid values:
  `auto` / `ctrl-v` / `ctrl-shift-v` / `shift-insert`. Unknown
  strings fall back to `auto`.
- The extension's `extension.js` is refactored into a pure
  `_resolveRecipe(mode) → recipe` function plus a
  `_dispatchKeystroke(recipe)` action. This keeps mode→keystroke
  mapping branch-free and unit-testable.
- The extension's `metadata.json` bumps `version` from 4 to 5 to
  reflect the breaking interface change for downstream consumers.
- **Backward compatibility**: the daemon's `_simulate_paste` wraps
  the call in `try / except DBusException` and, on failure, retries
  with the old no-argument signature. A new daemon paired with an
  unupgraded v4 extension therefore still pastes via the legacy
  behavior (which is `auto` by definition).

## Consequences

**Positive**

- **Future modes cost one string constant**, not a new D-Bus method
  + GVariant signature + extension export.
- **The compatibility fallback is local to the daemon**, so the
  extension's v4 → v5 upgrade is not blocking. Users who installed
  the daemon via PyPI but haven't refreshed the extension on
  extensions.gnome.org keep working.
- The `_resolveRecipe` split makes the extension testable without a
  live GNOME Shell — a future test runner only has to assert that
  mode strings map to the right recipes.

**Negative / trade-offs**

- **D-Bus introspection** now requires a string argument; quick
  manual smoke tests via `gdbus call` get slightly more verbose
  (`gdbus call ... SimulatePaste 'auto'`).
- The **try-with-arg + retry-without-arg** fallback only handles
  the v4 → v5 transition. If a future v6 changes the signature
  again, the daemon will need a second fallback layer or a version
  probe. Acceptable: rare event, and the version-probe option is
  cleaner than chained fallbacks.
- **Validation is loose**: the extension treats any unknown mode as
  `auto` rather than raising. This is intentional (forward
  compatibility — newer daemons shipping a mode the extension
  doesn't know about don't crash), but means typos in the daemon
  go silently to `auto` instead of surfacing.
