---
alwaysApply: true
---

# Temporal Awareness

Before any proactive action — reminder, alert, message, suggestion — ground yourself in time first.

## The check (before every proactive action)

1. **What time is it?** Know the current UTC time and the owner's local time (from `current_tz` in the `tz_state` singleton: `SELECT current_tz FROM tz_state WHERE id = 1` in `/workspace/store/messages.db`). When traveling, these differ from the server timezone. Don't assume.

2. **What's happening right now?** Use calendar and travel context. Is the owner in-flight? In a meeting? Asleep? Between events? A thing that made sense to schedule at 7am may not make sense to fire at noon if circumstances changed.

3. **Does this action still make sense given #1 and #2?**
   - Is the action window still open? (e.g., hotel checkout before a flight that already departed — window closed)
   - Can the owner act on this right now? (in-flight = can't check out of a hotel)
   - Is it obvious they already know? (traveling to a conference = they checked out)
   - Is the timing appropriate? (work alert at 3am local time = probably not)

## Past vs future — compute it, don't eyeball it

Any determination of *past vs future*, *deadline elapsed*, or *still time to act* MUST be computed against the real current instant — never asserted from prose judgment. You convert offsets correctly but then skip the comparison and label things "already passed" from vibes.

Resolve the deadline to a timezone-aware instant (do the offset conversion, e.g. `11:00 EDT` → `15:00 UTC`), then call the `now-vs-deadline` helper. It compares against the actual clock and returns `relation` (`past`/`future`/`now`), the signed delta, and `deadline_elapsed`:

```bash
python3 /home/node/.claude/skills/tessl__now-vs-deadline/scripts/now-vs-deadline.py --deadline "2026-06-12T15:00:00Z"
```

Act on its `relation` / `deadline_elapsed` — do not override it with your own read of the clock. The comparison is instant-only and location-agnostic. Reference incident (2026-06-12): a maintenance alert declared the 15:00 UTC Hertz pickup "already passed" at 13:10 UTC — ~2h early — because it converted the offset right but never compared the two instants.

## This is reasoning, not rules

Don't look for a matching rule. Ask: *"If I were a human assistant who knew the owner's full schedule right now, would I reach out about this at this moment?"*

If clearly no — don't. If uncertain — think about what a useful message would look like versus noise.

## Applies to

- Scheduled reminders (before scheduling AND before firing)
- Heartbeat alerts and email flags
- Any proactive message or suggestion
- Framing events as past/present/future ("upcoming", "just happened", "still time to act")

LLMs default to treating all information as equally present-tense. Explicitly compensate: check the clock, check the context, then act.
