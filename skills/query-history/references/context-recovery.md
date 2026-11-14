# Context Recovery Reference

Reference incident: 2026-04-24 / repeat 2026-04-25 — agent re-ran a JCON-2026 scrape from a post-compaction system-reminder block hours after the owner had completed it; the recurrence motivated `jbaruch/nanoclaw#104` (kill auto-compaction). Full narrative: `docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md`.

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

Missing chat identity, missing required schema, or query failure is unavailable evidence, never a successful empty history. Follow the owning `skills/query-history/SKILL.md` execution and error contract, surface the diagnostic, and have the operator repair the runtime identity/mount or owner schema. Never initialize, migrate, backfill, rewrite or substitute a database.

## Maintainer source links

The source-repository ADR cited above is available as the [maintainer decision record](https://github.com/jbaruch/nanoclaw-core/blob/ed9964a/docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md). It is not a container-local path.
