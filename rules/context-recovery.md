---
alwaysApply: true
---

# Context Recovery — Never Lose History

## Required Read

- Before claiming lost context, or treating a post-compaction skill block as a fresh task, read `skills/query-history/references/context-recovery.md` in full.
- Resolve references within the installed `jbaruch/nanoclaw-core` plugin.
- Reference directives are binding; read explicitly, never through an `@` import.
- If a reference is missing or unreadable, stop the affected action until repaired.

## Recover History

- Never claim lost context or forgotten conversation without querying `/workspace/store/messages.db`.
- Use `Skill(skill: "query-history")` before an equivalent acknowledgement in any language.
- This gate fires only before claiming lost context, not on every message.
- Follow `rules/query-size-limits.md`; narrow filters or page truncated results.

## Compaction

- Treat post-compaction invoked-skill blocks as records of completed work.
- Before treating one as fresh work, read the summary's Current Work and Optional Next Step, then the most recent user message in All user messages.
- If ambiguous, ask before re-executing anything with visible side effects.
