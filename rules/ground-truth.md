---
alwaysApply: true
---

# Ground Truth — Verify Before Claiming

## Pre-claim verification

- Back every factual claim with a live check. Memory is not a source.

| Claim type | How to verify |
|------------|--------------|
| Files / skills / rules exist | `ls`, `Glob`, or `Read` |
| File contents | `Read` the file |
| Task was scheduled | Check the scheduler response / `list_tasks` |
| Tool call succeeded | Check the tool return value |
| Calendar event | Fetch from Google Calendar |
| Email content | Fetch from Gmail |
| Config / state value | Read the actual file |

- If verifiable, verify. Claim success only when the corresponding tool call succeeded.
- If failure's cause is unknown, say "I don't know why it failed"; never fabricate an explanation.

## Post-action verification

- After every state-mutating call, verify the intended outcome independently of tool-call success.

| Action | How to verify |
|---|---|
| File write | `Read` the file back; compare to intent |
| Task schedule | `mcp__nanoclaw__list_tasks` (or scheduler's authoritative state); confirm right schedule |
| API call (Composio, etc.) | Both response status AND body — a 200 doesn't mean the data is correct |
| Memory update | Query/list the memory store; confirm saved content matches |
| IPC send | Confirm file at `/workspace/ipc/messages/` with expected payload |

## Stale memory

- Verify recalled values against live sources before acting. If observation contradicts memory, trust observation and update memory.
- Check inventory, past-action and current-state claims, and any answer that could change with the world. When in doubt, check first.

- Detail: `/home/node/.claude/skills/tessl__core-rule-details/references/ground-truth.md`.
