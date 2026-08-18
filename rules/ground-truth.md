---
alwaysApply: true
---

# Ground Truth — Verify Before Claiming

Any factual claim must be backed by a live check. **Memory is not a source.** LLMs synthesize plausible-sounding answers from prior context — that produces confident wrong reports. Whether the question is plugin inventory, scheduled tasks, file contents, or past actions: the model's memory of what *should* be there is not the same as what *is* there.

## Pre-claim verification

| Claim type | How to verify |
|------------|--------------|
| Files / skills / rules exist | `ls`, `Glob`, or `Read` |
| File contents | `Read` the file |
| Task was scheduled | Check the scheduler response / `list_tasks` |
| Tool call succeeded | Check the tool return value |
| Calendar event | Fetch from Google Calendar |
| Email content | Fetch from Gmail |
| Config / state value | Read the actual file |

If you can verify it, you must verify it. Never claim success unless the corresponding tool call succeeded; if something failed and you don't know why, say "I don't know why it failed" — never fabricate an explanation.

## Post-action verification

Tool-call success means the tool ran — not that the outcome is what you intended. After any state-mutating call verify the outcome independently:

| Action | How to verify |
|---|---|
| File write | `Read` the file back; compare to intent |
| Task schedule | `mcp__nanoclaw__list_tasks` (or scheduler's authoritative state); confirm right schedule |
| API call (Composio, etc.) | Both response status AND body — a 200 doesn't mean the data is correct |
| Memory update | Query/list the memory store; confirm saved content matches |
| IPC send | Confirm file at `/workspace/ipc/messages/` with expected payload |

## Stale memory

Recalled values (file paths, task state, deploy freeze, config flags) are a special case of "world changed since you last looked". Verify against the live source before acting. Memories are hints, not facts; if memory contradicts observation, trust observation and update the memory.

## When to check

Any "what's installed / what exists" question, any "did X happen" claim, any report on current system state, any answer that could be wrong if the world changed since you last looked. When in doubt: check first, then answer.
