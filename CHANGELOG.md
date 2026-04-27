# Changelog

## Unreleased

### Rules — removed (covered by runtime hooks in `qwibitai/nanoclaw#135` + `#136`)

- **no-lazy-verification** — Deleted. Runtime enforcement moved into the `lazy-verification-detector` Stop hook (jbaruch/nanoclaw#135 / PR #175): the regex catalogue + `Tried X — got Y` enumeration carve-out fully replace the prose rule. The runtime is now the source of truth.
- **default-silence** — Trimmed the "React with an emoji to acknowledge" line. The acknowledgement reaction is now emitted unconditionally by the `react-first` UserPromptSubmit hook (jbaruch/nanoclaw#136 / PR #173); the rule's other sections (forbidden phrases, parentheses-aren't-internal, not-for-me handling) stay.

### Rules — added previously

- **context-recovery** — Adds a "Post-compaction skill blocks are HISTORY, not new tasks" section. The system-reminder block listing skills invoked during the now-compacted window is a record, not a re-up of the request — re-executing it duplicates work and can spam the user. Reference incident: 2026-04-24 / 2026-04-25 JCON-2026 speakers scrape repeated twice across consecutive sessions despite a memory entry warning against this exact failure mode (motivated #104).

### Surface sync

- `tile.json` removes the `no-lazy-verification` rule entry.
- `README.md` rules table removes the `no-lazy-verification` row.
