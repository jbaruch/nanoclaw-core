---
name: status
description: Quick read-only health check — session context, workspace mounts, tool availability, and task snapshot. Use when the user asks for system status, health check, diagnostics, system info, check environment, what tools are available, or runs /status.
---

# /status — System Status Check

Generate a quick read-only status report of the current agent environment.

**No access restrictions.** This skill works in any group.

## How to gather the information

Run the checks below and compile results into the report format.

### 1. Session context

```bash
echo "Timestamp: $(date)"
echo "Working dir: $(pwd)"
echo "Channel: main"
```

### 2. Container uptime

Read `container_started` from `/workspace/group/session-state.json` and compute age:

```python
import json, datetime
state = json.load(open('/workspace/group/session-state.json'))
started = state.get('container_started')
if started:
    now = datetime.datetime.now(datetime.timezone.utc)
    # endswith-slice instead of `.replace("Z", ...)` — `.replace`
    # would corrupt any timestamp that contains 'Z' inside a numeric
    # offset (`+0Z00`-style malformed strings) or in microsecond
    # precision. The 'Z' suffix is positional; treat it that way.
    iso = started[:-1] + '+00:00' if started.endswith('Z') else started
    started_dt = datetime.datetime.fromisoformat(iso)
    age = now - started_dt
    print(f"{age.days}d {age.seconds // 3600}h (since {started})")
else:
    print("unknown")
```

### 3. Workspace and mount visibility

```bash
echo "=== Workspace ==="
ls /workspace/ 2>/dev/null
echo "=== Group folder ==="
ls /workspace/group/ 2>/dev/null | head -20
echo "=== Extra mounts ==="
ls /workspace/extra/ 2>/dev/null || echo "none"
echo "=== IPC ==="
ls /workspace/ipc/ 2>/dev/null
```

### 4. Tool availability and container utilities

```bash
which agent-browser 2>/dev/null && echo "Web (agent-browser): available" || echo "Web (agent-browser): unavailable"
ls /workspace/ipc/ 2>/dev/null && echo "Orchestration (IPC): available" || echo "Orchestration (IPC): unavailable"
node --version 2>/dev/null
claude --version 2>/dev/null
```

Then call `mcp__nanoclaw__list_tasks` — if it succeeds, report **MCP: available** and use the result for step 5; if it errors, report **MCP: unavailable**.

### 5. Task snapshot

Use the result from `mcp__nanoclaw__list_tasks`. If no tasks exist, report "No scheduled tasks."

## Report format

Present using Telegram HTML, adapting each section to what you actually found:

```
🔍 <b>NanoClaw Status</b>

<b>Session:</b>
• Channel: main
• Time: 2026-03-14 09:30 UTC
• Working dir: /workspace/group

<b>Container:</b>
• Uptime: Nd Hh (started YYYY-MM-DDTHH:MM:SSZ)
• agent-browser: ✓ / not installed
• Node: vXX.X.X
• Claude Code: vX.X.X

<b>Workspace:</b>
• Group folder: ✓ (N files)
• Extra mounts: none / N directories
• IPC: ✓ (messages, tasks, input)

<b>Tools:</b>
• Core: ✓  Web: ✓  Orchestration: ✓  MCP: ✓

<b>Scheduled Tasks:</b>
• N active tasks / No scheduled tasks
```

Keep it concise — this is a quick health check, not a deep diagnostic.

**See also:** `/capabilities` for a full list of installed skills and tools.
