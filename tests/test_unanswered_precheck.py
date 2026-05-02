"""Baseline tests for skills/check-unanswered/scripts/unanswered-precheck.py.

Locks down the documented contract per `coding-policy: testing-standards`:

  - Runs `check-unanswered.py` via `subprocess.run` and decides
    `wakeAgent` based on whether NEW unanswered messages appeared
    since the previous run
  - Pre-#220 legacy seen-state at `LEGACY_SEEN_FILE` is migrated to
    the canonical `/workspace/state/check-unanswered/` path on first
    run; idempotent, best-effort (OSError → stderr warning, no
    crash); when both paths exist, canonical wins and legacy is
    dropped
  - Subprocess failure modes all hit `wakeAgent: True` with a
    descriptive `error`: non-zero exit, JSONDecodeError, malformed
    `unanswered` shape (not-a-list, non-dict items, items missing
    `id`)
  - Soft `env-warning:`-prefixed errors from check-unanswered are
    carried through to `data.env_warning` rather than being treated
    as a hard error (since check-unanswered exits 0 on those)
  - Seen-state load: missing / malformed file resets `prev_ids = []`
    (waking the agent for everything is acceptable; a rebuilt seen
    set converges next run)
  - Seen-state write: atomic via tempfile + fsync + os.replace; on
    OSError, the precheck STILL emits `wakeAgent: True` with an
    error rather than crashing — the silent-precheck-failure class
    that gates this script's wake decision is what it exists to
    prevent
  - Decision: any new id → `wakeAgent: True` with `data.new_count` +
    `data.total`; no new ids → `wakeAgent: False` (and no `data`
    field unless an env_warning is being carried)
"""

import json
import os

import pytest


def _write_check_script(check_script, *, exit_code=0, stdout="", stderr=""):
    """Write a stub `check-unanswered.py` that emits the given
    stdout/stderr and exits with the given code. The fake stays
    deterministic across runs — no time / env reads."""
    body_lines = [
        "import sys",
    ]
    if stdout:
        # Escape so newlines inside stdout don't break the embedded
        # string literal.
        body_lines.append(f"sys.stdout.write({stdout!r})")
    if stderr:
        body_lines.append(f"sys.stderr.write({stderr!r})")
    body_lines.append(f"sys.exit({exit_code})")
    check_script.write_text("\n".join(body_lines))


def _run_main(module, capsys):
    code = 0
    try:
        result = module.main()
        code = 0 if result is None else int(result)
    except SystemExit as exc:
        code = 0 if exc.code is None else int(exc.code)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------


def test_migrate_legacy_no_op_when_legacy_absent(unanswered_precheck):
    """No legacy file → migration returns silently without touching
    canonical."""
    module, seen_dir, seen_file, legacy_seen_file, _ = unanswered_precheck
    assert not legacy_seen_file.exists()

    module.migrate_legacy_seen_state()
    assert not seen_file.exists()
    assert not seen_dir.exists()


def test_migrate_legacy_only_moves_to_canonical(unanswered_precheck):
    """Legacy present, canonical absent → file moved to canonical;
    legacy is gone after the migration."""
    module, _, seen_file, legacy_seen_file, _ = unanswered_precheck
    legacy_seen_file.parent.mkdir(parents=True)
    legacy_seen_file.write_text(json.dumps(["id-1", "id-2"]))

    module.migrate_legacy_seen_state()

    assert not legacy_seen_file.exists()
    assert json.loads(seen_file.read_text()) == ["id-1", "id-2"]


def test_migrate_legacy_drops_legacy_when_canonical_exists(unanswered_precheck):
    """Both paths exist → canonical wins, legacy dropped (idempotent
    convergence)."""
    module, seen_dir, seen_file, legacy_seen_file, _ = unanswered_precheck
    seen_dir.mkdir()
    seen_file.write_text(json.dumps(["canonical-id"]))
    legacy_seen_file.parent.mkdir(parents=True)
    legacy_seen_file.write_text(json.dumps(["legacy-id"]))

    module.migrate_legacy_seen_state()

    assert not legacy_seen_file.exists()
    # Canonical is untouched.
    assert json.loads(seen_file.read_text()) == ["canonical-id"]


def test_migrate_legacy_oserror_warns_but_continues(unanswered_precheck, monkeypatch, capsys):
    """OSError mid-migration → stderr warning, no exception (the
    seen-set is a heuristic; falling through to "no prev state" is
    acceptable)."""
    module, _, _, legacy_seen_file, _ = unanswered_precheck
    legacy_seen_file.parent.mkdir(parents=True)
    legacy_seen_file.write_text(json.dumps(["id-1"]))

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.os, "makedirs", _boom)

    module.migrate_legacy_seen_state()
    captured = capsys.readouterr()
    assert "legacy seen-state migration failed" in captured.err


# ---------------------------------------------------------------------------
# Subprocess failure modes
# ---------------------------------------------------------------------------


def test_check_unanswered_nonzero_exit_wakes_agent_with_error(unanswered_precheck, capsys):
    """check-unanswered.py exits non-zero → `wakeAgent: True` with
    the stderr tail (capped at 500 chars) in `data.error`."""
    module, _, _, _, check_script = unanswered_precheck
    _write_check_script(check_script, exit_code=2, stderr="DB locked\n")

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True
    assert "DB locked" in payload["data"]["error"]


def test_check_unanswered_invalid_json_wakes_agent(unanswered_precheck, capsys):
    """Subprocess exits 0 but emits non-JSON stdout → `wakeAgent:
    True` with `bad JSON from check-unanswered`."""
    module, *_, check_script = unanswered_precheck
    _write_check_script(check_script, exit_code=0, stdout="not json at all")

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True
    assert payload["data"]["error"] == "bad JSON from check-unanswered"


@pytest.mark.parametrize(
    "bad_unanswered",
    [
        # Not a list at all.
        {"unanswered": {"id": "x"}},
        # List of strings (no .get('id') possible).
        {"unanswered": ["id-1", "id-2"]},
        # List of dicts missing 'id'.
        {"unanswered": [{"timestamp": 1}]},
    ],
    ids=["dict-not-list", "list-of-strings", "dict-missing-id"],
)
def test_bad_unanswered_shape_wakes_agent_with_error(unanswered_precheck, capsys, bad_unanswered):
    """Three malformed-shape variants — each must wake the agent with
    a "bad unanswered shape" error rather than crashing the precheck
    on `m['id']`."""
    module, *_, check_script = unanswered_precheck
    _write_check_script(check_script, stdout=json.dumps(bad_unanswered))

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True
    assert payload["data"]["error"] == "bad unanswered shape from check-unanswered"


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def test_no_prev_state_treats_all_current_as_new(unanswered_precheck, capsys):
    """First run (seen file absent) → every current id is new →
    `wakeAgent: True` with `new_count == total`."""
    module, _, _, _, check_script = unanswered_precheck
    _write_check_script(
        check_script,
        stdout=json.dumps(
            {
                "unanswered": [
                    {"id": "msg-1"},
                    {"id": "msg-2"},
                ]
            }
        ),
    )

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True
    assert payload["data"]["new_count"] == 2
    assert payload["data"]["total"] == 2


def test_unchanged_set_returns_wake_false(unanswered_precheck, capsys):
    """Prev seen-file lists same ids as current → no new → `wakeAgent:
    False`, no `data` field (unless env-warning carries one)."""
    module, seen_dir, seen_file, _, check_script = unanswered_precheck
    seen_dir.mkdir()
    seen_file.write_text(json.dumps(["msg-1", "msg-2"]))
    _write_check_script(
        check_script,
        stdout=json.dumps({"unanswered": [{"id": "msg-2"}, {"id": "msg-1"}]}),
    )

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload == {"wakeAgent": False}


def test_partial_overlap_emits_only_new_count(unanswered_precheck, capsys):
    """Prev has msg-1, current has msg-1 + msg-2 → only msg-2 is new
    → `new_count == 1`, `total == 2`."""
    module, seen_dir, seen_file, _, check_script = unanswered_precheck
    seen_dir.mkdir()
    seen_file.write_text(json.dumps(["msg-1"]))
    _write_check_script(
        check_script,
        stdout=json.dumps({"unanswered": [{"id": "msg-1"}, {"id": "msg-2"}]}),
    )

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True
    assert payload["data"]["new_count"] == 1
    assert payload["data"]["total"] == 2


def test_corrupt_seen_file_resets_prev_ids(unanswered_precheck, capsys):
    """Malformed seen-file → caught by the JSONDecodeError /
    ValueError except → prev_ids resets to []. Every current id
    becomes new."""
    module, seen_dir, seen_file, _, check_script = unanswered_precheck
    seen_dir.mkdir()
    seen_file.write_text("{ not json")
    _write_check_script(
        check_script,
        stdout=json.dumps({"unanswered": [{"id": "msg-1"}]}),
    )

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True
    assert payload["data"]["new_count"] == 1


def test_seen_file_persisted_after_run(unanswered_precheck, capsys):
    """Every successful run writes the current id set to SEEN_FILE so
    the next run can compare. The atomic write also leaves no
    `.unanswered-seen-*` orphans."""
    module, seen_dir, seen_file, _, check_script = unanswered_precheck
    _write_check_script(
        check_script,
        stdout=json.dumps({"unanswered": [{"id": "msg-2"}, {"id": "msg-1"}]}),
    )

    _run_main(module, capsys)

    persisted = json.loads(seen_file.read_text())
    # Sorted (set + sorted in script).
    assert persisted == ["msg-1", "msg-2"]
    # No tempfile orphans.
    leftover = [p for p in seen_dir.iterdir() if p.name.startswith(".unanswered-seen-")]
    assert leftover == []


# ---------------------------------------------------------------------------
# env-warning passthrough
# ---------------------------------------------------------------------------


def test_env_warning_carried_into_payload(unanswered_precheck, capsys):
    """check-unanswered exit 0 with `error: "env-warning: ..."` →
    operator-visible `data.env_warning`. wakeAgent reflects the
    new-id decision independently."""
    module, _, _, _, check_script = unanswered_precheck
    _write_check_script(
        check_script,
        stdout=json.dumps(
            {
                "unanswered": [{"id": "msg-1"}],
                "error": "env-warning: NANOCLAW_CHAT_JID is empty",
            }
        ),
    )

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True  # msg-1 is new (no prev state)
    assert payload["data"]["env_warning"].startswith("env-warning:")


def test_env_warning_with_no_new_ids_still_emits_data(unanswered_precheck, capsys):
    """env_warning surfaces even on a no-new-ids run, so an
    operator-visible config issue isn't lost just because the wake
    decision is False."""
    module, seen_dir, seen_file, _, check_script = unanswered_precheck
    seen_dir.mkdir()
    seen_file.write_text(json.dumps(["msg-1"]))
    _write_check_script(
        check_script,
        stdout=json.dumps(
            {
                "unanswered": [{"id": "msg-1"}],
                "error": "env-warning: NANOCLAW_CHAT_JID is empty",
            }
        ),
    )

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is False
    assert payload["data"]["env_warning"].startswith("env-warning:")


# ---------------------------------------------------------------------------
# Atomic-write failure path
# ---------------------------------------------------------------------------


def test_seen_file_write_failure_wakes_agent_with_error(unanswered_precheck, monkeypatch, capsys):
    """Atomic write fails (OSError mid-replace) → `wakeAgent: True`
    with `data.error: "seen-file write failed: ..."` rather than
    propagating the exception. The silent-precheck-failure baseline."""
    module, _, _, _, check_script = unanswered_precheck
    _write_check_script(
        check_script,
        stdout=json.dumps({"unanswered": [{"id": "msg-1"}]}),
    )

    def _boom(src, dst):
        # Clean up the tmp file the script wrote so the test directory
        # is left tidy; the OSError below is what the script under
        # test must catch and convert to the wake-with-error payload.
        try:
            os.unlink(src)
        except FileNotFoundError:
            pass
        raise OSError("disk full")

    monkeypatch.setattr(module.os, "replace", _boom)

    _, out, _ = _run_main(module, capsys)
    payload = json.loads(out)
    assert payload["wakeAgent"] is True
    assert payload["data"]["error"].startswith("seen-file write failed: ")
