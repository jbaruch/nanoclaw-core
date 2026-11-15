# Check-unanswered state and reader contract

`scripts/check-unanswered.py` is the sole reader/writer of
`/workspace/state/check-unanswered/seen.json`. The host mounts `/workspace/state`
per group (`jbaruch/nanoclaw`, `src/volume-mounts.ts`). The file is
`{"schema_version": 1, "chat_jid": "<native chat>", "seen": {"<message id>": {"input": "<SHA-256>", "choice": "<validated Choice>"}}}`.
The file is one versioned record; `seen` entries belong to that record.
An optional `handled: true` on a seen entry records Claude's final decision that
the supplied message is already handled or needs no reply. Absence means pending.
The owning script also accepts the literal argument `handled` with a nonempty
JSON array of message IDs on stdin. It requires the current chat's valid state
and an existing `unanswered` Choice for every ID, then atomically records the
dispositions without querying the database or calling Jev. Other arguments,
invalid JSON, unknown IDs and cross-chat state exit 1 without changing state.
The reader accepts only integer version 1. Missing or unsupported versions,
malformed JSON and another chat's state produce an unavailable result without
rewriting the file. A missing file means no previous results. This script owns
future schema changes and migrations; there are no accepted older versions.
The private directory is mode `0700` and the state file is mode `0600`, including
when replacing an existing record. Writes replace the file atomically.
Only checked candidates still present in
the live query are retained.

The digest covers the pinned model, question and bounded evidence. Unchanged
evidence reuses the valid Choice; new text or context gets a new Choice.
`unanswered` remains pending and is emitted again until the host records an
answer or Claude records a final disposition. Handled entries stay silent even
when following context changes and are pruned when the live candidate query no
longer includes them. Emission is not acknowledgement. `cant_tell` stays silent;
new evidence can resolve it. Invalid/unavailable Jev results are not cached,
never retried within a run, and never wake Claude. Diagnostics contain no
provider body or message text.

Evidence construction and its bounds live in `scripts/check-unanswered.py` —
`evidence()` and the top-level constants. Capped evidence is classified with
`complete: false`; Jev returns `cant_tell` when clipping prevents a reliable
judgment. Valid Choices are cached and confirmed drops are emitted through the
same path as complete evidence. Deferred drops remain eligible on the next run. The fixed
Choice contract and owner issue citation live beside `QUESTION` in that script.

This is a core per-group cadence, as required by the owner's
[placement ruling](https://github.com/jbaruch/nanoclaw-core/issues/110#issuecomment-6843296921).
A single cross-group sweep would belong in admin. No group registry or other
chat's messages are read, even when a trusted group's DB mount contains them.

The existing runtime owns and initializes `messages` inline in
`jbaruch/nanoclaw`, `src/db.ts` `createSchema`; `reply_to_message_id` is added
by `addColumnIfMissing`, and the `telegram_message_id` inline upgrade backfills
inbound Telegram IDs. This reader requires message `id`, `chat_jid`,
`sender_name`, `content`, `timestamp`, `is_from_me`, `is_bot_message`,
`reply_to_message_id`, and `telegram_message_id`.
It also reads the existing `reactions` table, initialized by `createSchema`,
requiring `message_id`, `message_chat_jid`, and `reactor_jid`. A current-chat
`bot@telegram` reaction excludes a candidate, as does a threaded bot reply.
This uses script-delegation's precheck envelope and stateful-artifacts'
read-only legacy runtime-table contract: it never initializes or upgrades the DB.
Untrusted groups receive the host's current-chat filtered snapshot from
`src/filtered-db.ts`; this reader never substitutes a broader source. A missing
file/schema or failed query exits 1 with an unavailable payload, never a
successful empty read.
