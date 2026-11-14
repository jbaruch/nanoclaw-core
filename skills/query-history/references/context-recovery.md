# Context Recovery — Never Lose History

## The rule

**Never say you've lost context or forgotten a previous conversation without querying `messages.db` for it.** Context compaction removes history from active context — the database at `/workspace/store/messages.db` still has it. Conditional gate, not a per-message action: fires only when you're about to claim lost context.

## Required behavior

Before responding with "Потерял контекст", "I don't remember this thread", "I don't have context on this topic", or any equivalent acknowledgement that prior conversation is unavailable, use `Skill(skill: "query-history")`.

The canonical invocation, inputs, JSON output and exit contract live in `/home/node/.claude/skills/tessl__query-history/SKILL.md`, Steps 2–3. When this reference is read from that skill's Step 1, continue to Step 2; do not recursively invoke it.

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

Missing chat identity, missing required schema, or query failure is unavailable evidence, never a successful empty history. Follow the canonical skill's error path, surface the diagnostic, and have the operator repair the runtime identity/mount or owner schema. Never initialize, migrate, backfill, rewrite or substitute a database.

## Post-compaction skill blocks are HISTORY, not new tasks

When the conversation resumes after compaction, the system-reminder tail may carry a block opening with *"The following skills were invoked in this session. Continue to follow these guidelines:"* followed by `### Skill:` headers with `ARGUMENTS:` lines. That block is a **record of what already ran during the now-compacted window** — the skill already executed, the side effects (scrapes, messages, file writes) already landed. Re-executing it duplicates work and spams the user.

Before treating any such skill as a fresh task: read the conversation summary's **Current Work** and **Optional Next Step** sections (if the skill's ARGUMENTS aren't mentioned there, it was already handled and the summary moved on), then the most recent user message in the "All user messages" list (if the user's last move was NOT the skill invocation — e.g. "понял" or a topic shift — the skill is closed). If ambiguous, ask before re-executing anything with visible side effects.

Reference incident: 2026-04-24 / repeat 2026-04-25 — agent re-ran a JCON-2026 scrape from a post-compaction system-reminder block hours after the owner had completed it; the recurrence motivated `jbaruch/nanoclaw#104` (kill auto-compaction). Full narrative: [maintainer decision record](https://github.com/jbaruch/nanoclaw-core/blob/e45ddcf2d800108859180ec01d93e943f6f457ca/docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md).

## Hard requirement

Claiming lost context without checking the database is fabrication. The information exists. Retrieve it.
