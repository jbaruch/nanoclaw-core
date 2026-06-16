"""Tests for skills/now-vs-deadline/scripts/now-vs-deadline.py — the
helper the `temporal-awareness` rule mandates for any past/future or
deadline-elapsed determination.

The module exposes `compare(now, deadline)` and `parse_deadline(str)`
as pure functions so `now` can be pinned and the output asserted
deterministically (per `jbaruch/coding-policy: testing-standards` — no
reliance on wall-clock time). The CLI entrypoint (`main`) is a thin
JSON-printer / arg-validator wrapper.
"""

import datetime
import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills/now-vs-deadline/scripts/now-vs-deadline.py"

UTC = datetime.timezone.utc

# The AA487 repro from jbaruch/nanoclaw-core#51: at 13:10:50 UTC the
# alert declared the 15:00 UTC (11:00 EDT) Hertz pickup "already
# passed". It was ~2h *before* the deadline. These pinned values make
# that the regression guard.
REPRO_NOW = datetime.datetime(2026, 6, 12, 13, 10, 50, tzinfo=UTC)
REPRO_DEADLINE = datetime.datetime(2026, 6, 12, 15, 0, 0, tzinfo=UTC)


def _run(module, argv):
    """Invoke `main(argv)`, capturing stdout/stderr.

    Returns (exit_code, parsed_stdout_payload_or_None, stderr_text).
    Usage-error paths exit before printing JSON, so the payload is
    `None` for those."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = module.main(argv)
    stdout = out.getvalue()
    payload = json.loads(stdout) if stdout.strip() else None
    return rc, payload, err.getvalue()


def test_repro_future_deadline_is_not_elapsed(now_vs_deadline):
    """The exact #51 scenario: deadline 15:00 UTC, now 13:10:50 UTC.
    The model called this 'already passed'; the helper must compute
    'future' / not elapsed, with ~1h49m remaining."""
    result = now_vs_deadline.compare(REPRO_NOW, REPRO_DEADLINE)
    assert result["relation"] == "future"
    assert result["deadline_elapsed"] is False
    assert result["still_time_to_act"] is True
    assert result["delta_seconds"] == 6550  # 1h 49m 10s
    assert result["delta_text"] == "1h 49m from now"
    assert result["now"] == "2026-06-12T13:10:50Z"
    assert result["deadline"] == "2026-06-12T15:00:00Z"
    assert result["error"] is None


def test_past_deadline_is_elapsed(now_vs_deadline):
    now = datetime.datetime(2026, 6, 12, 17, 0, 0, tzinfo=UTC)
    result = now_vs_deadline.compare(now, REPRO_DEADLINE)
    assert result["relation"] == "past"
    assert result["deadline_elapsed"] is True
    assert result["still_time_to_act"] is False
    assert result["delta_seconds"] == -7200
    assert result["delta_text"] == "2h ago"


def test_exact_instant_is_now(now_vs_deadline):
    result = now_vs_deadline.compare(REPRO_DEADLINE, REPRO_DEADLINE)
    assert result["relation"] == "now"
    assert result["delta_seconds"] == 0
    assert result["delta_text"] == "now"
    assert result["deadline_elapsed"] is False
    assert result["still_time_to_act"] is False


def test_comparison_is_offset_independent(now_vs_deadline):
    """11:00-04:00 is the same instant as 15:00Z. A deadline parsed
    from the local-offset form must compare identically and echo
    normalized to UTC — proving the result doesn't depend on which
    offset the caller used."""
    deadline = now_vs_deadline.parse_deadline("2026-06-12T11:00:00-04:00")
    result = now_vs_deadline.compare(REPRO_NOW, deadline)
    assert result["deadline"] == "2026-06-12T15:00:00Z"
    assert result["relation"] == "future"
    assert result["delta_seconds"] == 6550


def test_humanize_multi_unit_and_subminute(now_vs_deadline):
    now = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    # 1 day, 2 hours, 3 minutes ahead.
    far = now + datetime.timedelta(days=1, hours=2, minutes=3)
    assert now_vs_deadline.compare(now, far)["delta_text"] == "1d 2h 3m from now"
    # 45 seconds behind — sub-minute renders seconds, not an empty unit.
    near = now - datetime.timedelta(seconds=45)
    assert now_vs_deadline.compare(now, near)["delta_text"] == "45s ago"


def test_parse_deadline_rejects_naive(now_vs_deadline):
    """A deadline without an offset must be rejected — comparing it
    would silently assume the host timezone, the failure this helper
    exists to close."""
    try:
        now_vs_deadline.parse_deadline("2026-06-12T15:00:00")
    except ValueError as e:
        assert "timezone offset" in str(e)
    else:
        raise AssertionError("expected ValueError for naive deadline")


def test_parse_deadline_accepts_z_suffix(now_vs_deadline):
    dt = now_vs_deadline.parse_deadline("2026-06-12T15:00:00Z")
    assert dt.utcoffset() == datetime.timedelta(0)


def test_missing_deadline_is_usage_error(now_vs_deadline):
    rc, payload, stderr = _run(now_vs_deadline, [])
    assert rc == 2
    assert payload is None
    assert "--deadline is required" in stderr


def test_naive_deadline_cli_is_usage_error(now_vs_deadline):
    rc, payload, stderr = _run(now_vs_deadline, ["--deadline", "2026-06-12T15:00:00"])
    assert rc == 2
    assert payload is None
    assert "timezone offset" in stderr


def test_unparseable_deadline_is_usage_error(now_vs_deadline):
    rc, payload, stderr = _run(now_vs_deadline, ["--deadline", "not-a-date"])
    assert rc == 2
    assert payload is None
    assert "could not parse" in stderr


def test_payload_shape_is_canonical(now_vs_deadline):
    result = now_vs_deadline.compare(REPRO_NOW, REPRO_DEADLINE)
    assert set(result.keys()) == {
        "now",
        "deadline",
        "relation",
        "delta_seconds",
        "delta_text",
        "deadline_elapsed",
        "still_time_to_act",
        "error",
    }


def test_cli_emits_single_line_json_against_real_clock():
    """The CLI reads the real system clock (it deliberately does not
    accept a `--now` override — the agent must never supply `now`). A
    far-future deadline is 'future' and a far-past one is 'past' no
    matter when the test runs, so the assertion stays deterministic
    while still exercising the real-clock path end to end."""
    future = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--deadline", "2999-01-01T00:00:00Z"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert future.stdout.endswith("\n")
    payload = json.loads(future.stdout)
    assert payload["relation"] == "future"
    assert payload["deadline_elapsed"] is False

    past = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--deadline", "2000-01-01T00:00:00Z"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(past.stdout)["relation"] == "past"
