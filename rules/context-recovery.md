---
alwaysApply: true
---

# Context Recovery — Never Lose History

## Recover History

- Before claiming lost context or forgotten conversation in any language, query `/workspace/store/messages.db` with `Skill(skill: "query-history")`; that skill owns the helper command and its filter, output and failure contract.
- This gate fires before claiming lost context, not on every message.

## Compaction

- A system-reminder block opening "The following skills were invoked in this session. Continue to follow these guidelines:" with `### Skill:` and `ARGUMENTS:` records completed work from the compacted window, including its side effects.
- Before treating it as fresh work, read the summary's Current Work and Optional Next Step: arguments absent there mean already handled and moved on.
- Then read the most recent user message in All user messages: if the user's last move was not the invocation, that invocation is closed.
- If ambiguous, ask before repeating visible side effects.

## Detail

- Schema and incident context: `/home/node/.claude/skills/tessl__query-history/references/context-recovery.md`.
