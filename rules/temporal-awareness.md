---
alwaysApply: true
---

# Temporal Awareness

## Required Read

- Before proactive action, past/present/future framing or current-zone reads, read `skills/current-tz/references/temporal-awareness.md` in full.
- Read it before scheduling and firing reminders, heartbeat alerts, email flags, messages and suggestions, including reliance on any exception.
- Resolve references within the installed `jbaruch/nanoclaw-core` plugin.
- Reference directives are binding; read explicitly, never through an `@` import.
- If a reference is missing or unreadable, stop the affected action until repaired.

## Time and Context

- Check real UTC time, owner's local time, calendar and travel context before proactive action.
- Assess whether the action window is open, owner can act, owner already knows, and timing is appropriate.
- If reaching out clearly makes no sense, do not; if uncertain, assess usefulness versus noise.
- Compute past/future, elapsed deadlines and remaining time with `Skill(skill: "now-vs-deadline")`; resolve a timezone-aware instant first and follow the verdict.

## Scoped current-zone script contract

- Read current zone only through this provider's regular target `/home/node/.claude/skills/tessl__current-tz/scripts/read-current-tz.py`.
- Never use container clock, handwritten SQL, copied readers or caller-selected paths for this lookup.
- Production invocation takes no arguments or input; never use `--now` operationally.
- Follow the reference's Scoped current-zone script contract for schema, output and failures.
- Retain caller-required unavailable/error handling; a failed read never grants a usable zone.
- Parsing grants no timezone-write, scheduling, model, owner or delivery authority and no exception to subsequent checks.
- Host alone migrates; reader never rewrites or upgrades rows.
