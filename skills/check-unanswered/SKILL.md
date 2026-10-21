---
name: check-unanswered
description: "Shadow-measures user messages that lack a threaded bot reply or bot reaction. Runs on cadence without waking the agent, classifies each new candidate with Jev, and records body-free outcomes for the check-unanswered go/no-go report."
cadence: "*/30 * * * *"
script: "scripts/unanswered-precheck.py"
---

# Check Unanswered Shadow

Process steps in order. Do not skip ahead.

## Step 1 — Run the shadow tick

The cadence registry runs `scripts/unanswered-precheck.py` before any agent turn. The script
scans only historically eligible groups, makes one Jev Choice request per new candidate, and
appends private shadow records under `/workspace/state/check-unanswered/`.

The scan consumes at most 50 deterministic cursor-ordered candidates per tick. A full page is
recorded as backlog for the next tick. Before measurement starts, the first eligible tick holds
all later invocations; after the exact fourteen-day population drains, the terminal lifecycle
makes no further provider calls.

Its last stdout line is always `{"wake_agent": false, "data": {...}}`. Provider, database,
configuration, and state errors remain shadow records and never wake the agent.

Proceed immediately to Step 2.

## Step 2 — Preserve the no-effect boundary

Do not send a message, reply, reaction, or agent wake from a shadow result. Labels are evidence
for the later report only. `addressed_inline`, `unanswered`, and `cant_tell` have no runtime
side effect.

Finish here.

## State and reporting

The state contract is in `skills/check-unanswered/references/state-schema.md`. After deployment and an
independently verified live no-effect tick, stamp the measurement window with the precheck's
`--stamp-window-start` mode. Build the body-free aggregate with
`scripts/check-unanswered-report.py`, supplying the frozen expected-group manifest and optional
keyed operator-confirmation census; its argument and output contracts are in that script's
top-level docstring.
