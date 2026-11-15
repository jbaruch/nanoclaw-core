# Check-unanswered state and reader contract

`scripts/check-unanswered.py` is the sole reader/writer of
`/workspace/state/check-unanswered/seen.json`. The host mounts `/workspace/state`
per group (`jbaruch/nanoclaw`, `src/volume-mounts.ts`). The file is
`{"schema_version": 1, "chat_jid": "<native chat>", "seen": {"<message id>": {"input": "<SHA-256>", "choice": "<validated Choice>"}}}`.
The file is one versioned record; `seen` entries belong to that record.
The reader accepts only integer version 1. Missing or unsupported versions,
malformed JSON and another chat's state produce an unavailable result without
rewriting the file. A missing file means no previous results. This script owns
future schema changes and migrations; there are no accepted older versions.
Writes replace the file atomically. Only checked candidates still present in
the live query are retained.

The digest covers the pinned model, question and bounded evidence. Unchanged
evidence reuses the valid Choice; new text or context gets a new Choice.
`unanswered` remains pending and is emitted again until the host records an
answer. Emission is not acknowledgement. `cant_tell` stays silent;
new evidence can resolve it. Invalid/unavailable Jev results are not cached,
never retried within a run, and never wake Claude. Diagnostics contain no
provider body or message text.

Evidence construction and its bounds live in `scripts/check-unanswered.py` —
`evidence()` and the top-level constants. Incomplete evidence is never classified,
cached or emitted. Deferred drops remain eligible on the next run. The fixed
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
This uses script-delegation's precheck envelope and stateful-artifacts'
read-only legacy runtime-table contract: it never initializes or upgrades the DB.
Untrusted groups receive the host's current-chat filtered snapshot from
`src/filtered-db.ts`; this reader never substitutes a broader source. A missing
file/schema or failed query exits 1 with an unavailable payload, never a
successful empty read.
