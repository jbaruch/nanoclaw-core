# Check-unanswered state and reader contract

`scripts/check-unanswered.py` is the sole reader/writer of
`/workspace/state/check-unanswered/seen.json`. The host mounts `/workspace/state`
per group (`jbaruch/nanoclaw`, `src/volume-mounts.ts`). The file is
`{"chat_jid": "<native chat>", "seen": {"<message id>": {"input": "<SHA-256>", "choice": "addressed_inline|unanswered|cant_tell"}}}`.
No schema version or migration machinery is introduced, per #110's KISS scope.
A missing file means no previous results; malformed JSON or another chat's
state is an error, never permission to widen the scan. Writes replace the file
atomically. Only candidates still present in the live query are retained.

The digest covers the pinned model, question and bounded evidence. Unchanged
evidence reuses the valid Choice; new text or context gets a new Choice.
`unanswered` remains pending and is emitted again until the host records an
answer/reaction. Emission is not acknowledgement. `cant_tell` stays silent;
new evidence can resolve it. Invalid/unavailable Jev results are not cached,
never retried within a run, and never wake Claude. Diagnostics contain no
provider body or message text.

Each Choice sees the candidate plus at most 20 following messages, with a
16,384-byte UTF-8 JSON state cap. Content is capped at 4,096 bytes per message,
sender names at 256 bytes. Any clipping or window overflow marks evidence
incomplete for Jev's judgment; insufficient evidence belongs to `cant_tell`.
The fixed Choice contract and owner issue citation live beside `QUESTION`.

This is a core per-group cadence, as required by the owner's
[placement ruling](https://github.com/jbaruch/nanoclaw-core/issues/110#issuecomment-6843296921).
A single cross-group sweep would belong in admin. No group registry or other
chat's messages are read, even when a trusted group's DB mount contains them.

The existing runtime owns and initializes `messages` and `reactions` inline in
`jbaruch/nanoclaw`, `src/db.ts` `createSchema`; `reply_to_message_id` is added
by `addColumnIfMissing`, and the `telegram_message_id` inline upgrade backfills
inbound Telegram IDs. This reader requires message `id`, `chat_jid`,
`sender_name`, `content`, `timestamp`, `is_from_me`, `is_bot_message`,
`reply_to_message_id`, `telegram_message_id`, and reaction `message_id`,
`message_chat_jid`, `reactor_jid`. Threaded replies match the candidate's internal
or platform ID, within the same chat; `bot@telegram` is the runtime's bot reactor
identity. This uses script-delegation's precheck envelope and stateful-artifacts'
read-only legacy runtime-table contract: it never initializes or upgrades the DB.
Untrusted groups receive the host's current-chat filtered snapshot from
`src/filtered-db.ts`; this reader never substitutes a broader source. A missing
file/schema or failed query exits 1 with an unavailable payload, never a
successful empty read.
