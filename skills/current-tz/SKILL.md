---
name: current-tz
description: Read the operator's current IANA timezone from the host-owned `tz_state` singleton, resolved from their live location, with no home-zone guessing. Use when a skill needs the zone the operator is in right now — phrasing "today" / "tomorrow", picking the parse zone for a "remind me at 8am" reminder, deciding whether a local time has passed — instead of the container clock, `home_tz`, or a hand-written SQL read. The single shared reader; do not copy the script into another plugin.
---

# current-tz Skill

Process steps in order. Do not skip ahead.

## Step 1 — Read the operator's current zone

```bash
python3 /home/node/.claude/skills/tessl__current-tz/scripts/read-current-tz.py
```

Stdout is one line of JSON:

- `{"available": true, "tz": "<iana>"}` — the zone the host resolved for the operator's current position
- `{"available": false, "tz": null}` — no usable zone: no `tz_state` row, an empty `current_tz`, a `schema_version` this reader does not accept, an unparseable zone name, or an unreadable store. The diagnostic is on stderr.

Exit `0` in both cases; exit `2` only on CLI misuse (the script takes no arguments). The script never guesses: `home_tz` is not a fallback. Proceed immediately to Step 2.

## Step 2 — Act on the result

- `available: true` → use `tz` for every local-date or local-time derivation: `datetime.now(timezone.utc).astimezone(ZoneInfo(tz))`.
- `available: false` → a phrasing surface falls back to explicit dates (no relative words, no warning marker); a scheduling caller that must pick a zone uses the container `$TZ`, which is the operator's zone at spawn per `jbaruch/nanoclaw#954`. Never read `home_tz` as a stand-in for where the operator is.

Finish here.
