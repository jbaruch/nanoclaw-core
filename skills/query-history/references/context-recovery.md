# Context Recovery Detail

The helper's installed-container path follows the standard `tessl__<name>`
mount convention. In a checkout, the script is
`skills/query-history/scripts/query-message-history.py`.

For the host schema owner, required fields and refusal behavior, see the
[read-only legacy runtime tables contract](legacy-tables.md).

## Compaction incident

On 2026-04-24 and again on 2026-04-25, an agent re-ran a JCON-2026 scrape
from a post-compaction system-reminder block hours after the owner had completed
it. The recurrence motivated [nanoclaw#104](https://github.com/jbaruch/nanoclaw/issues/104).
Full narrative: `docs/adr/2026-04-25-jcon-scrape-repeat-and-auto-compaction-kill.md`.
