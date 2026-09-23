---
name: current-tz
description: Read the operator's current IANA timezone from the host-owned `tz_state` singleton. Use when a skill needs the zone the operator is in right now — phrasing "today" / "tomorrow", picking the parse zone for a "remind me at 8am" reminder, deciding whether a local time has passed — instead of the container clock, `home_tz`, or a hand-written SQL read.
---

# current-tz Skill

Process steps in order. Do not skip ahead.

This skill is the single shared reader for the operator's current zone. Call it; do not copy `read-current-tz.py` into another plugin.

## Step 1 — Read the operator's current zone

```bash
python3 /home/node/.claude/skills/tessl__current-tz/scripts/read-current-tz.py
```

Stdout is one line of JSON:

- `{"available": true, "tz": "<iana>", "local_now": "<ISO-8601 with offset>", "local_date": "YYYY-MM-DD"}` — the zone the host resolved for the operator's current position, with the current instant already expressed in it
- `{"available": false, "tz": null, "local_now": null, "local_date": null}` — no usable zone: no `tz_state` row, an empty `current_tz`, a `schema_version` this reader does not accept, or an unparseable zone name. The diagnostic is on stderr.

Exit codes: `0` — the store was read and `available` is the answer. `1` — the store could not be read (missing file, no `tz_state` table, corruption, permission); stdout still carries the unavailable shape. `2` — CLI misuse. `--now <ISO-8601 instant with offset>` pins the instant the local fields derive from; omit it in production. The script never guesses: `home_tz` is not a fallback. Proceed immediately to Step 2.

## Step 2 — Act on the result

- `available: true` → use `local_now` and `local_date` as the operator's wall clock and date.
- `available: true` → pass `tz` to any script that converts another instant.
- `available: false` on exit `0`, phrasing surface → fall back to explicit dates, no relative words and no warning marker.
- `available: false` on exit `0`, scheduling caller that must pick a zone → use the container `$TZ`.
- Exit `1`, scheduling caller → treat it as a hard failure and surface the stderr diagnostic.
- Exit `1`, phrasing surface → degrade as for `available: false`.
- Never read `home_tz` as a stand-in for where the operator is.

Finish here.
