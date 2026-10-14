# Check Unanswered Shadow State

## Owner and location

`check-unanswered` owns `ShadowStateV1` under
`/workspace/state/check-unanswered/`. The cadence precheck is the sole writer. The repository
report script is a read-only consumer. Each group receives its own state mount.

## Files

- `state.json` carries `schema_version`, `run_id`, `group_id`, scan cursor, model/question
  versions, deployment revision, and the explicitly stamped UTC measurement-window start.
- `events.jsonl` is append-only. Each line carries `schema_version`, `event`, `at_utc`, and
  event-specific body-free fields.
- `.lock` serializes cadence ticks and explicit window stamping in one group.

Message bodies and following-message content never enter these files. Private message locators
remain in `candidate_started` events so the operator can inspect a later sample. Public reports
use the accompanying opaque candidate ID instead.

## Event contract

- `candidate_started`: dedupe key, private message locator, candidate timestamp, opaque ID,
  bounded-context counts, and truncation facts. It is appended before the provider call. Its
  presence prevents a retry after restart, including a crash between the marker and the call.
- `decision`: dedupe key, opaque ID, semantic label, probabilities, confidence, latency,
  token counts, model, and question version.
- `error`: optional dedupe key/opaque ID plus a fixed error category. Provider response bodies,
  request content, credentials, and exception text are never recorded.
- `tick`: eligibility and scan-health counters. A completed tick records the highest
  `(timestamp, id)` observed as the scan cursor.
- `window_started`: the externally verified deployment revision and explicit UTC start.

Every candidate has at most one `candidate_started` event. A started candidate has zero or one
terminal `decision`/`error`; zero is an interrupted attempt reported as unresolved.

## Version handling

The owner accepts only schema version 1. Missing state initializes version 1. An older or newer
version is refused with a no-wake error; no reader or writer treats it as empty state. Shape
changes require a new schema version and an owner migration before deployment.

## Privacy and authority

State is a private measurement snapshot, not authority to contact a user or enable enforcement.
The fourteen-day clock starts only from an explicit `window_started` event written after the
deployed revision, cadence row, and live no-effect tick have been independently verified.
