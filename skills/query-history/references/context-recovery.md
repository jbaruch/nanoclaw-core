# Context Recovery — Never Lose History

## The rule

**Never say you've lost context or forgotten a previous conversation without querying `messages.db` for it.** Context compaction removes history from active context — the database at `/workspace/store/messages.db` still has it. Conditional gate, not a per-message action: fires only when you're about to claim lost context.

## Required behavior

Before responding with "Потерял контекст", "I don't remember this thread", "I don't have context on this topic", or any equivalent acknowledgement that prior conversation is unavailable, run the `query-history` skill's search helper:

```bash
python3 /home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py --keyword "<text>"
```

Filters: `--sender <name>` (matches `sender_name`; see the Schema section below for the `Display (@username)` shape — a username fragment is enough), `--limit N` (default 20, cap 50 per `rules/query-size-limits.md`), `--offset N` (batch through larger result sets). Output is single-line JSON on stdout (exit 0 and exit 1; usage errors at exit 2 print a stderr diagnostic only — do not parse stdout), capped to the `rules/query-size-limits.md` tool-result budget — `truncated` / `content_truncated` / `rows_dropped` report cuts; narrow the filters or batch with `--offset` on a truncated result. Chat scope from `NANOCLAW_CHAT_JID`. The command above is the installed-container mount path (standard `tessl__<name>` convention); in a checkout of this repo the same script is `skills/query-history/scripts/query-message-history.py`.

## Schema (quick reference)

```sql
messages(id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)
chats(jid, name, last_message_time, channel, is_group)
```

`is_from_me = 1` is the bot's own messages. `sender` is the stable numeric user ID; `sender_name` is `Display (@username)` — a username fragment matches via `--sender`. Critical after a session nuke: the DB remembers who said what when you don't.

## Post-compaction skill blocks are HISTORY, not new tasks

When the conversation resumes after compaction, the system-reminder tail may carry a block opening with *"The following skills were invoked in this session. Continue to follow these guidelines:"* followed by `### Skill:` headers with `ARGUMENTS:` lines. That block is a **record of what already ran during the now-compacted window** — the skill already executed, the side effects (scrapes, messages, file writes) already landed. Re-executing it duplicates work and spams the user.

Before treating any such skill as a fresh task: read the conversation summary's **Current Work** and **Optional Next Step** sections (if the skill's ARGUMENTS aren't mentioned there, it was already handled and the summary moved on), then the most recent user message in the "All user messages" list (if the user's last move was NOT the skill invocation — e.g. "понял" or a topic shift — the skill is closed). If ambiguous, ask before re-executing anything with visible side effects.

Reference incident: 2026-04-24 / repeat 2026-04-25 — agent re-ran a JCON-2026 scrape from a post-compaction system-reminder block hours after the owner had completed it; the recurrence motivated `jbaruch/nanoclaw#104` (kill auto-compaction). Full narrative: `docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md`.

## Hard requirement

Claiming lost context without checking the database is fabrication. The information exists. Retrieve it.

## Helper execution details

When this reference is read from `query-history` Step 1, continue to Step 2; do not recursively invoke the skill. This reference owns the invocation and output contract.

Provide at least one of `--keyword <text>` (matches `content`) or `--sender <name>`; combined filters AND together. Limits above 50 and negative offsets are usage errors. Offset defaults to 0. The script escapes `%`, `_` and `\` to match them literally. It opens the database read-only (`mode=ro`); a missing store is an error, never a newly created empty database.

The JSON payload is `{rows, chat_jid, query, truncated, rows_dropped, error}`. Each row carries `id`, `timestamp`, `sender_name`, `content`, `is_from_me` and `content_truncated`, newest first. `rows_dropped` counts rows removed to fit the tool-result budget. An empty `rows` with `error:null` is a successful search with no matches: proceed silently and do not fabricate matches. A non-null `error` is a runtime failure on exit 1: surface the diagnostic and stop. Otherwise return matched rows in the caller's required format.

## Runtime-owned history table

This is a read-only consumer under **Read-Only Legacy Runtime Tables** in `jbaruch/coding-policy: stateful-artifacts`. Its finite table inventory is `messages`; it does not query `chats` or require unrelated columns.

The owner is `jbaruch/nanoclaw`. Its schema of record is [`src/db.ts`, `createSchema` and `initDatabase`](https://github.com/jbaruch/nanoclaw/blob/ef8cf4d6837427f8924deda83b7af00c215996fc/src/db.ts#L109). `initDatabase` opens the host store and calls `createSchema` before applying registered state migrations. Inline upgrades in `createSchema` add/backfill `is_bot_message`, add reply metadata, and add/backfill `telegram_message_id`. The later [`state-029-messages-thread-id.ts`](https://github.com/jbaruch/nanoclaw/blob/ef8cf4d6837427f8924deda83b7af00c215996fc/src/state-migrations/state-029-messages-thread-id.ts) adds `thread_id`. None supplies a per-record version for this legacy table; do not invent one.

The runtime writer is [`src/db-messages.ts`, `storeMessage` / `storeMessageDirect`](https://github.com/jbaruch/nanoclaw/blob/ef8cf4d6837427f8924deda83b7af00c215996fc/src/db-messages.ts#L101). The reader requires these columns:

| Field | Reader use and owner representation |
| --- | --- |
| `id` | Text message identifier; primary key with `chat_jid`; returned and used to break timestamp ties |
| `chat_jid` | Text chat identifier; must equal runtime-provided `NANOCLAW_CHAT_JID` |
| `timestamp` | Text timestamp; returned and sorted newest first |
| `sender_name` | Text display name, optionally `Display (@username)`; sender filter searches this, not numeric `sender` |
| `content` | Text message body; keyword filter and returned content |
| `is_from_me` | Integer bot-origin flag; projected as a JSON boolean |

Columns have no reader-supplied defaults. SQLite permits nulls in this legacy schema; text nulls remain null in output and do not match text filters, and the reader projects a null `is_from_me` as false. A successful empty search proves no matches only within its declared scope.

Use only the runtime-mounted `/workspace/store/messages.db`, opened read-only by the helper and scoped to the runtime's chat identity. `NANOCLAW_DB` is the existing test seam, not permission to select a different operational database. The runtime's [`src/filtered-db.ts`, `createFilteredDb`](https://github.com/jbaruch/nanoclaw/blob/ef8cf4d6837427f8924deda83b7af00c215996fc/src/filtered-db.ts#L34) owns untrusted per-chat projections; readers never replace them with the full store.

Missing chat identity, missing required schema, or query failure is unavailable evidence, never a successful empty history. Follow Helper execution details above, surface the diagnostic, and have the operator repair the runtime identity/mount or owner schema. Never initialize, migrate, backfill, rewrite or substitute a database.

## Maintainer source links

The source-repository ADR cited above is available as the [maintainer decision record](https://github.com/jbaruch/nanoclaw-core/blob/ed9964a/docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md). It is not a container-local path.
