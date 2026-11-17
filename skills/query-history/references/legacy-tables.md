# Read-only legacy runtime tables contract

The finite table inventory is `messages`, `chats` and `registered_groups` in
the host's shared `messages.db` (container default:
`/workspace/store/messages.db`). The owner and schema of record are
[`jbaruch/nanoclaw`, `src/db.ts:createSchema`](https://github.com/jbaruch/nanoclaw/blob/main/src/db.ts).
That function initializes the tables and performs inline upgrades, including
adding legacy message flags and chat metadata. This contract makes no
migration-version or per-record schema-version guarantee.

## Readers and required fields

| Reader | Table | Required fields and use |
| --- | --- | --- |
| `skills/query-history/scripts/query-message-history.py` | `messages` | `chat_jid` scopes to `NANOCLAW_CHAT_JID`; `id` and `timestamp` order results; `id`, `timestamp`, `sender_name`, `content`, `is_from_me` are returned. Keyword filters use `content`; sender filters use `sender_name`. |
| Default-silence's registration check (`rules/default-silence.md`) | `registered_groups` | `jid` identifies the current chat; `requires_trigger` selects triggered (`1`) or untriggered (`0`) mode. |

`sender_name` stores `Display (@username)`; `is_from_me = 1` marks the bot's
own messages. `chats` belongs to the host's history schema, but neither reader
above queries it or requires its columns. This contract does not require
unrelated tables or columns to run these reads.

## Read and refusal behavior

Readers only query the authorized host database for the current chat. The
history helper opens it with SQLite `mode=ro`; `NANOCLAW_DB` can identify its
mounted path. Registration uses `registered_groups`, not the derivative,
incomplete `/workspace/ipc/available_groups.json`.

Readers never initialize, migrate, backfill or substitute a database. Missing
required tables or columns, or any query failure, mean the read is unavailable,
never a successful empty search or an unregistered/default-triggered chat.
The history helper exits non-zero with an error payload and actionable stderr;
the registration check reports unavailable and stops rather than guessing a
mode. Check the host DB mount/path and ask the host runtime owner to restore
the required schema; readers do not repair it. A successful query with no
matching rows is distinct from a query failure.
