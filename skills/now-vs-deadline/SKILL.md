---
name: now-vs-deadline
description: Deterministically decide whether a deadline/event is past or future relative to the real current instant. The mandated computation path for `rules/temporal-awareness.md` — call it before any "already passed", "still time to act", or upcoming/just-happened framing instead of eyeballing the clock.
---

# now-vs-deadline Skill

Compares a deadline against the actual current instant and returns past/future plus the signed delta. Use it whenever you would otherwise assert that a deadline has elapsed or that there is still time to act — `rules/temporal-awareness.md` requires the comparison to be computed here, not inferred.

## Step 1 — Resolve the deadline to a timezone-aware instant

Do the offset conversion first (e.g. `11:00 EDT` -> `2026-06-12T15:00:00Z`, or pass `2026-06-12T11:00:00-04:00`). The deadline **must** carry a timezone offset (`Z` or `+HH:MM`); a naive value is rejected at exit 2, because comparing it would silently assume the host timezone — the exact failure this skill exists to prevent.

```bash
python3 /home/node/.claude/skills/tessl__now-vs-deadline/scripts/now-vs-deadline.py --deadline "2026-06-12T15:00:00Z"
```

The comparison is **location-agnostic**: it compares instants only, so the result is independent of the offset you used. No physical location and no `current_tz` lookup happen here. Mapping relative phrasings (`today`/`now`/`сейчас`/`here`) into a local frame stays in the trusted tile.

## Step 2 — Use the JSON result; do not override it

The script prints a single-line JSON payload to stdout:

```json
{
  "now": "2026-06-12T13:10:50Z",
  "deadline": "2026-06-12T15:00:00Z",
  "relation": "future",
  "delta_seconds": 6550,
  "delta_text": "1h 49m from now",
  "deadline_elapsed": false,
  "still_time_to_act": true,
  "error": null
}
```

`relation` is `past` / `future` / `now`; `delta_seconds` is signed (>0 future, <0 past). Read `relation` / `deadline_elapsed` / `still_time_to_act` and act on them directly — do not re-derive past/future from your own read of the clock. Exit 0 on success; exit 2 on a usage error (missing, unparseable, or naive `--deadline`) with the diagnostic on stderr and no JSON.
