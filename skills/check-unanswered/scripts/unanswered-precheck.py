#!/usr/bin/env python3
"""
Pre-check script for group heartbeat tasks.

Runs check-unanswered.py and compares results against the previous run.
If no NEW unanswered messages appeared since last check, outputs
{"wakeAgent": false} so the scheduler skips the LLM entirely.

Works for any group — uses NANOCLAW_CHAT_JID from environment (same as
check-unanswered.py) and stores seen state in /workspace/group/ which
is per-container.

Usage in schedule_task script field:
    python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/unanswered-precheck.py
"""

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_SCRIPT = os.path.join(SCRIPT_DIR, 'check-unanswered.py')
SEEN_FILE = '/workspace/group/unanswered-seen.json'


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

    # Load previous seen set
    try:
        with open(SEEN_FILE) as f:
            prev_ids = sorted(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        prev_ids = []

    # Always persist current state for next run
    with open(SEEN_FILE, 'w') as f:
        json.dump(current_ids, f)

    # Find genuinely new messages
    prev_set = set(prev_ids)
    new_ids = [i for i in current_ids if i not in prev_set]

    if new_ids:
        print(json.dumps({
            "wakeAgent": True,
            "data": {"new_count": len(new_ids), "total": len(current_ids)}
        }))
    else:
        print(json.dumps({"wakeAgent": False}))


if __name__ == '__main__':
    main()
