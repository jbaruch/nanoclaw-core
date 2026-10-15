# Check Unanswered Shadow State

## Owner and location

`check-unanswered` owns `ShadowStateV1` under
`/workspace/state/check-unanswered/`. The cadence precheck is the sole writer. The repository
report script is a read-only consumer. Each group receives its own state mount.

## Files

- `state.json` carries `schema_version`, `run_id`, `group_id`, scan cursor, model/question
  versions, deployment revision, lifecycle, and the explicitly stamped UTC
  measurement-window start.
- `events.jsonl` is append-only and capped at 64 MiB. Each line carries `schema_version`,
  `event`, `at_utc`, and event-specific body-free fields. Reaching the cap writes a terminal
  `capacity_exhausted` lifecycle record, stops provider work, and prevents completion rather
  than discarding required candidates.
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
- `tick`: eligibility, scan-health counters, page-full backlog evidence, lifecycle, scan cutoff,
  and the highest `(timestamp, id)` cursor. Candidate queries reconcile the rolling historical
  lookback with older cursor backlog, excluding durable `candidate_started` locators before the
  query limit. They consume deterministic pages of at most 50 unstarted rows, so late-ingested
  rows remain visible without started rows starving the bounded page.
- `window_started`: the externally verified exact deployment revision, explicit UTC start, and
  eligible proof-tick timestamp. The start must equal that tick and cannot be in the future. The
  event is written before active state; either side of an interrupted transition is reconciled
  idempotently on retry.
- `lifecycle`: terminal `capacity_exhausted` evidence. No later provider request is allowed.

Every candidate has at most one `candidate_started` event. A started candidate has zero or one
terminal `decision`/`error`; zero is an interrupted attempt reported as unresolved.

Before a window is stamped, one eligible tick is allowed and later cadence invocations hold with
no provider work. During an active window the cursor drains all candidates through the exact
fourteen-day end. Once that population is drained, lifecycle becomes `measurement_complete` and
later ticks perform no provider work.

## Version handling

The owner accepts only schema version 1. Missing state initializes version 1. An older or newer
version is refused with a no-wake error; no reader or writer treats it as empty state. Shape
changes require a new schema version and an owner migration before deployment.

## Privacy and authority

State is a private measurement snapshot, not authority to contact a user or enable enforcement.
The fourteen-day clock starts only from an explicit `window_started` event written after the
deployed revision, cadence row, and live no-effect tick have been independently verified.
The body-free report requires a frozen expected-group manifest and validates every state/event
field against this schema. It reports missing and extra run IDs, requires eligible tick gaps no
larger than one hour, and accepts operator confirmations only as unique opaque IDs that resolve
to actual `unanswered` decisions in the active window.

The expected-group manifest is an exact object with `schema_version`, the 40-hex
`deployment_source_revision`, and a unique nonempty `expected_run_ids` list containing the
`check-unanswered-<20 hex>` IDs from deployment/registration evidence. The optional confirmation
file is an exact object with `schema_version` and a nonempty `confirmations` list. Each confirmation
has only a unique 24-hex `opaque_id` and boolean `real_drop`; counts are derived, never supplied.
