#!/usr/bin/env python3
"""
Pre-check script for group heartbeat tasks.

Runs check-unanswered.py and compares results against the previous run.
If no NEW unanswered messages appeared since last check, outputs
{"wakeAgent": false} so the scheduler skips the LLM entirely.

Works for any group — uses NANOCLAW_CHAT_JID from environment (same as
check-unanswered.py) and stores seen state under /home/node/.claude/.
That directory is the per-session .claude/ bind mount and is always
writable regardless of container trust tier; /workspace/group/ (the
earlier location) is read-only for untrusted groups, which made the
precheck silently fail with EACCES, return scriptResult=null in the
agent-runner, and skip the LLM every tick — strictly worse than no
precheck. Per-session scoping is fine here: scheduled tasks always
fire in the `maintenance` session (src/task-scheduler.ts), so the
seen-set tracks maintenance's view of this group's unanswered history.

Usage in schedule_task script field:
    python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/unanswered-precheck.py
"""

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_SCRIPT = os.path.join(SCRIPT_DIR, 'check-unanswered.py')
SEEN_STATE_DIR = '/home/node/.claude/nanoclaw-state'
SEEN_FILE = os.path.join(SEEN_STATE_DIR, 'unanswered-seen.json')


def main():
    # Run check-unanswered.py
    result = subprocess.run(
        [sys.executable, CHECK_SCRIPT],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        # Script failed — wake agent so it can investigate
        print(json.dumps({"wakeAgent": True, "data": {"error": result.stderr[:500]}}))
        return

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(json.dumps({"wakeAgent": True, "data": {"error": "bad JSON from check-unanswered"}}))
        return

    current_ids = sorted(str(m['id']) for m in data.get('unanswered', []))

    # Soft env-var warnings ride in data['error'] with an `env-warning:`
    # prefix — the script exited 0 but wants operators to notice a
    # config typo. Carry it into our own payload so the scheduler sees
    # it in the wake payload instead of having to tail container logs;
    # stderr is swallowed by capture_output=True on the success path.
    # Hard errors exit non-zero and are handled above, so on this code
    # path `error` is either `None` or an env-warning string.
    err = data.get('error')
    env_warning = err if isinstance(err, str) and err.startswith('env-warning:') else None

    # Load previous seen set
    try:
        with open(SEEN_FILE) as f:
            prev_ids = sorted(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        prev_ids = []

    # Always persist current state for next run. mkdir-with-parents is
    # idempotent and avoids hand-written existence checks; the parent
    # dir is created on first run, then no-op every run after.
    os.makedirs(SEEN_STATE_DIR, exist_ok=True)
    with open(SEEN_FILE, 'w') as f:
        json.dump(current_ids, f)

    # Find genuinely new messages
    prev_set = set(prev_ids)
    new_ids = [i for i in current_ids if i not in prev_set]

    data_out: dict = {}
    if new_ids:
        data_out["new_count"] = len(new_ids)
        data_out["total"] = len(current_ids)
    if env_warning:
        data_out["env_warning"] = env_warning

    payload: dict = {"wakeAgent": bool(new_ids)}
    if data_out:
        payload["data"] = data_out

    print(json.dumps(payload))


if __name__ == '__main__':
    main()
