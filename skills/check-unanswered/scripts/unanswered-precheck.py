#!/usr/bin/env python3
"""
Pre-check script for group heartbeat tasks.

Runs check-unanswered.py and compares results against the previous run.
If no NEW unanswered messages appeared since last check, outputs
{"wakeAgent": false} so the scheduler skips the LLM entirely.

Works for any group — uses NANOCLAW_CHAT_JID from environment (same as
check-unanswered.py) and stores seen state under
/workspace/state/check-unanswered/. That path is the per-group
canonical writable mount available to every container regardless of
trust tier (jbaruch/nanoclaw#99 Cat 4, host PR jbaruch/nanoclaw#220 —
data/state/<folder>/ on the host bound at /workspace/state). Pre-#220
this script wrote to /home/node/.claude/nanoclaw-state/ as a
workaround because /workspace/group/ is read-only on untrusted tiers
and any write silently EACCES'd; with /workspace/state/ available,
the workaround is no longer needed. The "agent's persisted state,
every tier, always RW" convention is documented in the host repo's
docs/SPEC.md under "Container Workspace Layout"
(https://github.com/jbaruch/nanoclaw/blob/main/docs/SPEC.md).

Per-group scoping (not per-session): the seen-set tracks the group's
unanswered history regardless of which session ran the check, so
on-demand reruns from the user-facing session and scheduled
maintenance fires share state. Cross-group leakage is impossible by
virtue of the bind being scoped to <folder>.

Existing seen-state at the legacy path is detected and migrated on
first run after deploy — see migrate_legacy_seen_state below — so no
spurious wake cycle.

Usage in schedule_task script field:
    python3 /home/node/.claude/skills/tessl__check-unanswered/scripts/unanswered-precheck.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHECK_SCRIPT = os.path.join(SCRIPT_DIR, 'check-unanswered.py')
SEEN_STATE_DIR = '/workspace/state/check-unanswered'
SEEN_FILE = os.path.join(SEEN_STATE_DIR, 'unanswered-seen.json')

# Legacy location used before host PR #220 landed the /workspace/state/
# convention. Detected and migrated on first run so the freshly-deployed
# precheck doesn't lose its seen-set and re-wake the agent for every
# already-known unanswered message. Migration is idempotent (the legacy
# file is removed after the move) and best-effort: a failure here just
# falls through to the normal "no prev state -> rebuild" path, which is
# acceptable because the seen-set is purely an optimization.
LEGACY_SEEN_FILE = '/home/node/.claude/nanoclaw-state/unanswered-seen.json'


def migrate_legacy_seen_state():
    """One-shot migration from the pre-#220 path. Idempotent.

    Runs once per container, before the seen-set load. If both paths
    exist, the canonical one wins (legacy is deleted to converge); if
    only the legacy one exists, it gets moved into place. Failures
    surface as warnings in stderr but don't block the precheck — the
    scheduler still gets a valid wake decision based on whichever set
    was reachable.
    """
    if not os.path.exists(LEGACY_SEEN_FILE):
        return
    try:
        os.makedirs(SEEN_STATE_DIR, exist_ok=True)
        if os.path.exists(SEEN_FILE):
            # Canonical already populated — this run is the FIRST one
            # AFTER the canonical file was created (likely a rerun
            # after the migration's first pass). Drop the legacy copy
            # so subsequent runs don't keep going through this branch.
            os.unlink(LEGACY_SEEN_FILE)
            return
        shutil.move(LEGACY_SEEN_FILE, SEEN_FILE)
    except OSError as e:
        # Don't crash the precheck on migration failure — the seen-set
        # is a heuristic and the next run will rebuild it from the
        # current candidate set. Surface as a stderr line so an
        # operator tailing logs sees it.
        print(
            f"unanswered-precheck: legacy seen-state migration failed: {e}",
            file=sys.stderr,
        )


def main():
    # One-shot migration of pre-#220 seen-state before any read. No-op
    # on the steady state (post-migration the legacy file is gone); no
    # crash on failure (the seen-set is a heuristic, will rebuild).
    migrate_legacy_seen_state()

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

    # Always persist current state for next run. Atomic write: a
    # SIGKILL / disk-full mid-`json.dump` would leave SEEN_FILE
    # truncated, and the next run's JSONDecodeError branch resets
    # prev_ids=[] — waking the agent spuriously for every existing
    # candidate. Write to a temp file in the same dir, fsync, then
    # os.replace (atomic rename on POSIX) so readers see either the
    # old file or the complete new file, never a partial one.
    #
    # On failure, surface via wake-JSON rather than raising. An
    # unhandled exception here would crash the precheck, the runner
    # would yield scriptResult=null, and the scheduler would skip
    # waking the agent entirely — the exact "silent precheck failure"
    # this script exists to prevent. The catch is scoped to OSError
    # (covers makedirs/mkstemp/fdopen/write/fsync/replace/unlink) so
    # real bugs still crash visibly.
    try:
        os.makedirs(SEEN_STATE_DIR, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix='.unanswered-seen-', dir=SEEN_STATE_DIR
        )
        try:
            # Hand ownership of fd to a file object. If os.fdopen
            # itself raises before wrapping completes, fd is still
            # open and would leak. Close it explicitly on that narrow
            # path before re-raising into the outer handler.
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
            # Best-effort cleanup of the temp file on any inner
            # failure, then re-raise to the outer OSError handler (or
            # propagate non-OSError up if something else went wrong).
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
    except OSError as e:
        print(json.dumps({
            "wakeAgent": True,
            "data": {"error": f"seen-file write failed: {e}"},
        }))
        return

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
