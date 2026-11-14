---
alwaysApply: true
---

# Temporal Awareness

## Time and Context

- Before scheduling/firing reminders, heartbeat/email alerts or proactive messages/suggestions, check real UTC, owner's local time, calendar and travel context.
- Assess open action window, ability to act, existing awareness and appropriate timing. If clearly useless, stay silent; if uncertain, weigh usefulness versus noise.
- Compute past/future framing, elapsed deadlines and remaining time via `Skill(skill: "now-vs-deadline")`; resolve a timezone-aware instant first, follow its location-agnostic verdict, never eyeball.

## Scoped current-zone script contract

- Use `jbaruch/nanoclaw-core`'s regular target `/home/node/.claude/skills/tessl__current-tz/scripts/read-current-tz.py`; never container clock, handwritten SQL, copied reader or caller-selected path.
- Production: no arguments/input; no `--now` clock substitution.
- JSON stdout: `available,tz,local_now,local_date`. Usable: `available:true`, valid IANA zone and local instant/date. Unavailable: `false`, null projection fields. Failed reads grant no zone; retain caller-required unavailable/error handling. Target docstring owns exits/diagnostics.
- No timezone-write, scheduling, model, owner or delivery authority; no exception to later checks.

## Runtime owner

- `jbaruch/nanoclaw`'s `src/db-tz.ts` writes `tz_state` in `/workspace/store/messages.db`. Schema: `src/state-migrations/state-010-tz-state.schema.md`; migrations there: `state-010-tz-state.ts`, `state-012-tz-state-segments.ts`, `state-013-tz-state-segments-datetime.ts`, `state-015-tz-state-stale-warning.ts`.
- Select only `current_tz,schema_version` at `id=1`; accept only record version4, nonblank valid IANA zone. Missing row, unsupported version or invalid zone is unavailable. Host alone migrates; reader never rewrites/upgrades.
- Source-authoring verification binds trusted base manifest to this repo and reads this declared regular rule; never claims unmerged content is installed.
