# 2026-04-25 — JCON-2026 Scrape Repeat → Auto-Compaction Kill (jbaruch/nanoclaw#104)

Reference incident motivating the "Post-compaction skill blocks are HISTORY, not new tasks" gate in `rules/context-recovery.md`, and the broader decision to kill auto-compaction (`jbaruch/nanoclaw#104`).

## What happened — 2026-04-24 / repeat 2026-04-25

A post-compaction system-reminder included an `agent-browser` invocation with JCON-2026-speakers ARGUMENTS. On both days the agent treated it as a new task and re-ran the entire scrape + report — the owner had finished that task hours earlier ("мы закончили с этим часа 4 назад"). The actual pending work was unrelated (continuing skill patches per the summary's Optional Next Step). The repeat one day later, despite a memory entry warning against this exact failure, is what motivated `jbaruch/nanoclaw#104` (kill auto-compaction).

## Why the rule's per-turn check isn't enough on its own

Post-compaction context-recovery prose can tell the agent "treat the skill block as history, not a fresh request" — but the next compaction will erase that very prose along with the rest. Auto-compaction was firing during long-running sessions exactly when the agent was most likely to mistake a stale invocation block for a current request. The two mitigations work together: the rule (still in `context-recovery.md`) enforces the per-turn check; killing auto-compaction (`#104`) removes the trigger that creates these stale invocation blocks at all.

## Why this lives in an ADR

The narrative — quoted owner correction, day-by-day recurrence, link to `#104` — was loaded into every spawn before this extraction. The runtime gate (the three-step verification: read Current Work + Optional Next Step, read most recent user message, ask before re-executing visible side effects) is what changes per-turn agent behavior; the narrative is what the agent recognises *after* the gate fires. The ADR keeps the institutional memory; the rule keeps the gate.
