---
name: current-tz
description: Read the operator's current IANA timezone from the host-owned `tz_state` singleton. Use when a skill needs the zone the operator is in right now — phrasing "today" / "tomorrow", picking the parse zone for a "remind me at 8am" reminder, deciding whether a local time has passed — instead of the container clock, `home_tz`, or a hand-written SQL read.
---

# current-tz Skill

Process steps in order. Do not skip ahead.

This skill is the single shared reader for the operator's current zone. Call it; do not copy its reader into another plugin.

## Step 1 — Read the Binding Reference

Read the full reference from the installed `jbaruch/nanoclaw-core` provider:

```text
/home/node/.claude/skills/tessl__current-tz/references/temporal-awareness.md
```

Follow its complete directives. Read explicitly, never through an `@` import. If missing or unreadable, stop until repaired. Proceed immediately to Step 2.

## Step 2 — Read the operator's current zone

Execute the invocation in the binding reference's **Scoped current-zone script contract**, using its input, output and exit contract. See `/home/node/.claude/skills/tessl__current-tz/references/temporal-awareness.md`. Proceed immediately to Step 3.

## Step 3 — Act on the result

- `available: true` → use `local_now` and `local_date` as the operator's wall clock and date.
- `available: true` → pass `tz` to any script that converts another instant.
- `available: false` on exit `0`, phrasing surface → fall back to explicit dates, no relative words and no warning marker.
- `available: false` on exit `0`, scheduling caller that must pick a zone → use the container `$TZ`.
- Exit `1`, scheduling caller → treat it as a hard failure and surface the stderr diagnostic.
- Exit `1`, phrasing surface → degrade as for `available: false`.
- Never read `home_tz` as a stand-in for where the operator is.

Finish here.
