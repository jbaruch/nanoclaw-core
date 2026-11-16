# Check-unanswered state and reader contract

`scripts/check-unanswered.py` is the sole reader/writer of
`/workspace/state/check-unanswered/seen.json`. The host mounts `/workspace/state`
per group (`jbaruch/nanoclaw`, `src/volume-mounts.ts`). The file is
`{"schema_version": 1, "chat_jid": "<native chat>", "seen": {"<message id>": "<validated Choice>"}}`.
The file is one versioned record; `seen` entries belong to that record.
The reader accepts only integer version 1. Missing or unsupported versions,
malformed JSON, another chat's state and a `seen` value outside the Choice set
produce an unavailable result without
rewriting the file. A missing file means no previous results. This script owns
future schema changes and migrations; there are no accepted older versions.
The private directory is mode `0700` and the state file is mode `0600`, including
when replacing an existing record. Writes replace the file atomically.
Only checked candidates still present in
the live query are retained.

Each candidate gets one Jev Choice, recorded by message ID and never requested
again while the candidate stays in the live query. Only a newly recorded
`unanswered` wakes Claude, once. Invalid/unavailable Jev results are not recorded,
never retried within a run, and never wake Claude. Diagnostics contain no
provider body or message text. A run starts new Jev requests only within
`CLASSIFY_BUDGET_SECONDS`, so it ends inside the host's maintenance-container
timeout; candidates it does not reach stay unrecorded for the next run.

Evidence construction and its bounds live in `scripts/check-unanswered.py` —
`evidence()` and the top-level constants. Capped evidence is classified with
`complete: false`; Jev returns `cant_tell` when clipping prevents a reliable
judgment. A candidate whose minimal evidence still exceeds
the Jev input bound (for example escaped control characters) is skipped with a
sanitized diagnostic, is never cached or woken, and does not block later candidates.
A drop that does not fit the output bound is not recorded, so the next run offers it. The fixed
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
