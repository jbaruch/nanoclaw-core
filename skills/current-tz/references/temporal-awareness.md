# Temporal Awareness

Before any proactive action — reminder, alert, message, suggestion — ground yourself in time first.

When reading this reference from an already invoked skill, continue that skill's steps; do not recursively invoke it.

## The check (before every proactive action)

1. **What time is it?** Know the current UTC time and the owner's local time. The owner's zone comes from `Skill(skill: "current-tz")`; its canonical script contract is below. Never use the container clock or a hand-written SQL read. When traveling, these differ from the server timezone. Don't assume.

2. **What's happening right now?** Use calendar and travel context. Is the owner in-flight? In a meeting? Asleep? Between events? A thing that made sense to schedule at 7am may not make sense to fire at noon if circumstances changed.

3. **Does this action still make sense given #1 and #2?**
   - Is the action window still open? (e.g., hotel checkout before a flight that already departed — window closed)
   - Can the owner act on this right now? (in-flight = can't check out of a hotel)
   - Is it obvious they already know? (traveling to a conference = they checked out)
   - Is the timing appropriate? (work alert at 3am local time = probably not)

## Past vs future — compute it, don't eyeball it

Any determination of *past vs future*, *deadline elapsed*, or *still time to act* MUST be computed against the real current instant via the `now-vs-deadline` helper — never asserted from prose judgment. Resolve the deadline to a timezone-aware instant first (do the offset conversion, e.g. `11:00 EDT` → `15:00 UTC`), then invoke `Skill(skill: "now-vs-deadline")` and act on its verdict rather than your own read of the clock. The comparison is instant-only and location-agnostic.

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

This canonical script contract serves `rules/temporal-awareness.md` and the `current-tz` skill. It covers direct scripted reads from the expected installed `jbaruch/nanoclaw-core` provider only.

```bash
python3 /home/node/.claude/skills/tessl__current-tz/scripts/read-current-tz.py
```

Use that regular target, never a copied reader, caller-selected path or handwritten SQL. Production invocation takes no arguments or input payload. `--now <ISO-8601 instant with offset>` is a fixture seam; never use it operationally.

The target's top-level docstring defines its CLI and diagnostic contract. Stdout is one JSON object:

- `{"available": true, "tz": "<iana>", "local_now": "<ISO-8601 with offset>", "local_date": "YYYY-MM-DD"}` — usable current zone and its local instant/date.
- `{"available": false, "tz": null, "local_now": null, "local_date": null}` — no usable zone; diagnostic on stderr.

Exit codes: `0` means the store was read and `available` is the answer. `1` means the store could not be read (missing file, missing table/column, corruption or permission); stdout still carries the unavailable shape. `2` means CLI misuse and a stderr diagnostic, with no JSON. A missing row, blank zone, unsupported record version or invalid IANA zone is unavailable on exit `0`. Never guess from `home_tz`.

Retain unavailable/error handling required by the calling workflow; `current-tz` Step 3 owns its caller branches. Parsing grants no timezone-write, scheduling, model, owner or delivery authority and no exception to subsequent checks. A failed read never grants a usable zone.

The runtime owner is `jbaruch/nanoclaw`: `src/db-tz.ts` writes the singleton at
`/workspace/store/messages.db`, and
`src/state-migrations/state-010-tz-state.schema.md` is its schema contract.
The authoritative owner migrations are `state-010-tz-state.ts`,
`state-012-tz-state-segments.ts`, `state-013-tz-state-segments-datetime.ts` and
`state-015-tz-state-stale-warning.ts` in that same migrations directory. This
reader selects only `current_tz,schema_version` at `id=1` and accepts exactly
record version 4: a nonblank valid IANA `current_tz` is usable; a missing row,
unsupported version or invalid zone is unavailable. This is the record version,
not the database migration number. The host alone migrates; the reader never
rewrites or upgrades a row.

[Provider contract tests](https://github.com/jbaruch/nanoclaw-core/blob/main/tests/test_current_tz_contract.py) verify the declared provider/skill/rule and
native target lookup plus actual read-only output. [Reader tests](https://github.com/jbaruch/nanoclaw-core/blob/main/tests/test_read_current_tz.py)
cover supported/unsupported state, missing/corrupt stores, unavailable outcomes,
fixed-clock projections and CLI misuse. Source-authoring verification binds the
trusted base manifest to this repository and reads this declared regular rule and its reference;
it does not claim an unmerged contract is installed.
