---
alwaysApply: true
---

# Ground Truth — Verify Before Claiming

Any factual claim must be backed by a live check. Never synthesize answers from memory, conversation history, or prior context when the ground truth is verifiable.

## The rule

Before stating that something is true, check:

| Claim type | How to verify |
|------------|--------------|
| Files/skills/rules exist | `ls`, `Glob`, or `Read` |
| File contents | `Read` the file |
| Task was scheduled | Check the scheduler response |
| Tool call succeeded | Check the tool return value |
| Calendar event | Fetch from Google Calendar |
| Email content | Fetch from Gmail |
| Config/state value | Read the actual file |

**If you can verify it, you must verify it. Memory is not a source.**

## Never claim success without confirmation

Never claim a tool ran, a task was scheduled, a file changed, or memory was saved unless the corresponding tool call succeeded. If something didn't work and you don't know why, say "I don't know why it failed" — never fabricate an explanation.

## Why this matters

LLMs synthesize plausible-sounding answers from prior context. This produces confident, wrong reports. Whether the question is about tile inventory, scheduled tasks, file contents, or past actions — the model's memory of what *should* be there is not the same as what *is* there.

## Applies to

- Any "what's installed / what exists" question
- Any "did X happen / was X done" claim
- Any report on current system state
- Any answer that could be wrong if the world changed since you last looked

When in doubt: check first, then answer.
