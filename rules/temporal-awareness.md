---
alwaysApply: true
---

# Temporal Awareness

Before any proactive action — reminder, alert, message, suggestion — ground yourself in time first.

## The check (before every proactive action)

1. **What time is it?** Know the current UTC time and the owner's local time. The owner's zone comes from the `current-tz` skill's script (`skills/current-tz/scripts/read-current-tz.py`), which reads the host-resolved `tz_state.current_tz`; never from the container clock or a hand-written SQL read. When traveling, these differ from the server timezone. Don't assume.

2. **What's happening right now?** Use calendar and travel context. Is the owner in-flight? In a meeting? Asleep? Between events? A thing that made sense to schedule at 7am may not make sense to fire at noon if circumstances changed.

3. **Does this action still make sense given #1 and #2?**
   - Is the action window still open? (e.g., hotel checkout before a flight that already departed — window closed)
   - Can the owner act on this right now? (in-flight = can't check out of a hotel)
   - Is it obvious they already know? (traveling to a conference = they checked out)
   - Is the timing appropriate? (work alert at 3am local time = probably not)

## Past vs future — compute it, don't eyeball it

Any determination of *past vs future*, *deadline elapsed*, or *still time to act* MUST be computed against the real current instant via the `now-vs-deadline` helper — never asserted from prose judgment. Resolve the deadline to a timezone-aware instant first (do the offset conversion, e.g. `11:00 EDT` → `15:00 UTC`), then run the `now-vs-deadline` skill and act on its verdict rather than your own read of the clock. The comparison is instant-only and location-agnostic.

## This is reasoning, not rules

Don't look for a matching rule. Ask: *"If I were a human assistant who knew the owner's full schedule right now, would I reach out about this at this moment?"*

If clearly no — don't. If uncertain — think about what a useful message would look like versus noise.

## Applies to

- Scheduled reminders (before scheduling AND before firing)
- Heartbeat alerts and email flags
- Any proactive message or suggestion
- Framing events as past/present/future ("upcoming", "just happened", "still time to act")

LLMs default to treating all information as equally present-tense. Explicitly compensate: check the clock, check the context, then act.


## Scoped current-zone script contract

This named provider rule covers direct scripted reads of the operator's current
zone through this plugin's co-shipped `skills/current-tz/scripts/read-current-tz.py`.
The native lookup is
`/home/node/.claude/skills/tessl__current-tz/scripts/read-current-tz.py`; use that
regular target from the expected `jbaruch/nanoclaw-core` provider, not a copied
reader, caller-selected path or handwritten SQL. Production invocation has no
arguments or input payload. The script's `--now` fixture seam is not permission
to substitute a clock in an operational run.

Stdout is one JSON object with `available`, `tz`, `local_now` and `local_date`.
A usable result has `available:true`, an IANA `tz` and its local instant/date;
an unavailable result has `available:false` and null projection fields. Consumers
retain unavailable/error handling required by their own workflow; parsing a
result grants no timezone-write, scheduling, model, owner or delivery authority.
The target's docstring owns exit/diagnostic details; a failed read never grants a
usable zone. This contract grants no exception to checks after lookup.

The runtime owner is `jbaruch/nanoclaw`: `src/db-tz.ts` writes the singleton at
`/workspace/store/messages.db`, and
`src/state-migrations/state-010-tz-state.schema.md` is its schema contract.
The authoritative owner migrations are `state-010-tz-state.ts`,
`state-012-tz-state-segments.ts`, `state-013-tz-state-segments-datetime.ts` and
`state-015-tz-state-stale-warning.ts` in that same migrations directory. This
reader selects only `current_tz,schema_version` at `id=1` and accepts exactly
record version4: a nonblank valid IANA `current_tz` is usable; a missing row,
unsupported version or invalid zone is unavailable. This is the record version,
not the database migration number. The host alone migrates; the reader never
rewrites or upgrades a row.

`tests/test_current_tz_contract.py` verifies the declared provider/skill/rule and
native target lookup plus actual read-only output. `tests/test_read_current_tz.py`
covers supported/unsupported state, missing/corrupt stores, unavailable outcomes,
fixed-clock projections and CLI misuse. Source-authoring verification binds the
trusted base manifest to this repository and reads this declared regular rule;
it does not claim an unmerged contract is installed.
