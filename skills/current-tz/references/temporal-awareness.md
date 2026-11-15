# Temporal Awareness Examples

A thing that made sense to schedule at 7am may not make sense to fire at noon if circumstances changed.

(e.g., hotel checkout before a flight that already departed — window closed)

(in-flight = can't check out of a hotel)

(traveling to a conference = they checked out)

(work alert at 3am local time = probably not)

## Caller handling

- `available: true` → use `local_now` and `local_date` as the operator's wall clock and date.
- `available: true` → pass `tz` to any script that converts another instant.
- `available: false` on exit `0`, phrasing surface → fall back to explicit dates, no relative words and no warning marker.
- `available: false` on exit `0`, scheduling caller that must pick a zone → use the container `$TZ`.
- Exit `1`, scheduling caller → treat it as a hard failure and surface the stderr diagnostic.
- Exit `1`, phrasing surface → degrade as for `available: false`.
- Never read `home_tz` as a stand-in for where the operator is.

## Test coverage

`tests/test_current_tz_contract.py` verifies the declared provider/skill/rule and
native target lookup plus actual read-only output. `tests/test_read_current_tz.py`
covers supported/unsupported state, missing/corrupt stores, unavailable outcomes,
fixed-clock projections and CLI misuse.
