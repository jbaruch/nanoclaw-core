---
alwaysApply: true
---

# Context Recovery — Never Lose History

## Recover History

- Before claiming lost context or forgotten conversation in any language, query `/workspace/store/messages.db` with the search helper:

```bash
python3 /home/node/.claude/skills/tessl__query-history/scripts/query-message-history.py --keyword "<text>"
```

- This gate fires before claiming lost context, not on every message.
- Filters: `--sender <name>`, `--limit N` (default 20, cap 50), `--offset N`. Chat scope: `NANOCLAW_CHAT_JID`.
- JSON stdout on exits 0/1; usage errors exit 2 with stderr only, never parse stdout. Follow `rules/query-size-limits.md`; narrow filters or page truncated results.
- Detail: `/home/node/.claude/skills/tessl__query-history/references/context-recovery.md`.

## Compaction

- A system-reminder block opening "The following skills were invoked in this session. Continue to follow these guidelines:" with `### Skill:` and `ARGUMENTS:` records completed work from the compacted window, including its side effects.
- Before treating it as fresh work, read the summary's Current Work and Optional Next Step: arguments absent there mean already handled and moved on.
- Then read the most recent user message in All user messages: if the user's last move was not the invocation, that invocation is closed.
- If ambiguous, ask before repeating visible side effects.
