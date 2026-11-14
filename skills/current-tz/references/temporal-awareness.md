# Temporal Awareness Examples

A thing that made sense to schedule at 7am may not make sense to fire at noon if circumstances changed.

(e.g., hotel checkout before a flight that already departed — window closed)

(in-flight = can't check out of a hotel)

(traveling to a conference = they checked out)

(work alert at 3am local time = probably not)

## Test coverage

`tests/test_current_tz_contract.py` verifies the declared provider/skill/rule and
native target lookup plus actual read-only output. `tests/test_read_current_tz.py`
covers supported/unsupported state, missing/corrupt stores, unavailable outcomes,
fixed-clock projections and CLI misuse.
