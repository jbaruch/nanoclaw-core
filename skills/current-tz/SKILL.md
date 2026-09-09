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

- `{"available": true, "tz": "<iana>", "local_now": "<ISO-8601 with offset>", "local_date": "YYYY-MM-DD"}` — the zone the host resolved for the operator's current position, with the current instant already expressed in it
- `{"available": false, "tz": null, "local_now": null, "local_date": null}` — no usable zone: no `tz_state` row, an empty `current_tz`, a `schema_version` this reader does not accept, or an unparseable zone name. The diagnostic is on stderr.

Exit codes: `0` — the store was read and `available` is the answer. `1` — the store could not be read (missing file, no `tz_state` table, corruption, permission); stdout still carries the unavailable shape. `2` — CLI misuse. `--now <ISO-8601 instant with offset>` pins the instant the local fields derive from; omit it in production. The script never guesses: `home_tz` is not a fallback. Proceed immediately to Step 2.

## Step 2 — Act on the result

- `available: true` → use `local_now` and `local_date` as the operator's wall clock and date; pass `tz` to any script that converts another instant.
- `available: false` on exit `0` → a phrasing surface falls back to explicit dates (no relative words, no warning marker); a scheduling caller that must pick a zone uses the container `$TZ`. Never read `home_tz` as a stand-in for where the operator is.
- Exit `1` → a scheduling caller treats it as a hard failure and surfaces the stderr diagnostic; a phrasing surface degrades as for `available: false`.

Finish here.
