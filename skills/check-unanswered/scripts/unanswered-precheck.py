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
import tempfile

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

    unanswered = data.get('unanswered', [])
    # Narrow the shape: a malformed response (e.g. `unanswered` is a
    # dict, or items are strings) would raise TypeError on `m['id']`
    # below and crash the precheck. Since the precheck gates the
    # scheduled wake, a crash skips the agent entirely — the exact
    # "silent precheck failure" class this script exists to prevent.
    # Surface the bad shape as an error-wake instead.
    if not isinstance(unanswered, list) or not all(
        isinstance(m, dict) and 'id' in m for m in unanswered
    ):
        print(json.dumps({
            "wakeAgent": True,
            "data": {"error": "bad unanswered shape from check-unanswered"},
        }))
        return
    current_ids = sorted(str(m['id']) for m in unanswered)

    # Load previous seen set
    try:
        with open(SEEN_FILE) as f:
            prev_ids = sorted(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        prev_ids = []

    # Always persist current state for next run. Atomic write: a
    # SIGKILL / disk-full mid-`json.dump` would leave SEEN_FILE
    # truncated, and the next run's JSONDecodeError branch resets
    # prev_ids=[] — waking the agent spuriously for every existing
    # candidate. Write to a temp file in the same dir, fsync, then
    # os.replace (atomic rename on POSIX) so readers see either the
    # old file or the complete new file, never a partial one.
    os.makedirs(SEEN_STATE_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix='.unanswered-seen-', dir=SEEN_STATE_DIR
    )
    try:
        # Hand ownership of fd to a file object. If os.fdopen itself
        # raises before wrapping completes, fd is still open and would
        # leak via the outer except (which only unlinks tmp_path). The
        # inner try/except closes fd on that narrow failure path.
        try:
            f = os.fdopen(fd, 'w')
        except BaseException:
            os.close(fd)
            raise
        with f:
            json.dump(current_ids, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SEEN_FILE)
    except BaseException:
        # Re-raise after best-effort cleanup of the temp file. Never
        # swallow the error — a failed write here is a real problem
        # that should surface rather than silently leaving SEEN_FILE
        # stale.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise

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
