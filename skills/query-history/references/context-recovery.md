# Context Recovery Detail

The helper's installed-container path follows the standard `tessl__<name>`
mount convention. In a checkout, the script is
`skills/query-history/scripts/query-message-history.py`.

## Schema (quick reference)

```sql
messages(id, chat_jid, sender, sender_name, content, timestamp, is_from_me, is_bot_message)
chats(jid, name, last_message_time, channel, is_group)
```

`is_from_me = 1` is the bot's own messages. `sender` is the stable numeric user ID; `sender_name` is `Display (@username)` — a username fragment matches via `--sender`. Critical after a session nuke: the DB remembers who said what when you don't.

## Compaction incident

On 2026-04-24 and again on 2026-04-25, an agent re-ran a JCON-2026 scrape
from a post-compaction system-reminder block hours after the owner had completed
it. The recurrence motivated [nanoclaw#104](https://github.com/jbaruch/nanoclaw/issues/104).
Full narrative: `docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md`.
