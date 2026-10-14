"""Body-free aggregation for check-unanswered shadow state."""

import json
from pathlib import Path


def _root(path: Path, *, run_id: str, window_start="2026-09-23T12:00:00Z"):
    path.mkdir()
    (path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "window_start_utc": window_start,
            }
        )
    )
    return path


def _events(path: Path, rows):
    (path / "events.jsonl").write_text(
        "".join(json.dumps({"schema_version": 1, **row}) + "\n" for row in rows)
    )


def test_report_aggregates_groups_without_private_locators(unanswered_report, tmp_path):
    first = _root(tmp_path / "first", run_id="run-a")
    second = _root(tmp_path / "second", run_id="run-b")
    _events(
        first,
        [
            {
                "event": "candidate_started",
                "at_utc": "2026-09-23T12:00:00Z",
                "candidate_key": "private-key-a",
                "message_id": "private-message-a",
                "candidate_timestamp": "2026-09-23T10:00:00Z",
                "opaque_id": "opaque-a",
                "count_truncated": True,
                "bytes_truncated": False,
            },
            {
                "event": "decision",
                "at_utc": "2026-09-23T12:00:01Z",
                "candidate_key": "private-key-a",
                "opaque_id": "opaque-a",
                "label": "unanswered",
                "latency_ms": 100,
                "candidate_bytes_truncated": False,
            },
            {"event": "tick", "at_utc": "2026-09-23T12:00:02Z", "eligible": True},
        ],
    )
    _events(
        second,
        [
            {
                "event": "candidate_started",
                "at_utc": "2026-09-24T12:00:00Z",
                "candidate_key": "private-key-b",
                "message_id": "private-message-b",
                "candidate_timestamp": "2026-09-24T10:00:00Z",
                "opaque_id": "opaque-b",
                "count_truncated": False,
                "bytes_truncated": True,
            },
            {
                "event": "error",
                "at_utc": "2026-09-24T12:00:01Z",
                "candidate_key": "private-key-b",
                "opaque_id": "opaque-b",
                "category": "provider_unavailable",
                "scope": "candidate",
                "latency_ms": 300,
            },
            {"event": "tick", "at_utc": "2026-09-24T12:00:02Z", "eligible": True},
        ],
    )
    report = unanswered_report.build_report([first, second])
    encoded = json.dumps(report)
    assert report["eligible_groups"] == ["run-a", "run-b"]
    assert report["window"]["complete_14_days"] is False
    assert report["candidates_per_day"] == {"2026-09-23": 1, "2026-09-24": 1}
    assert report["label_distribution"]["unanswered"] == 1
    assert report["provider_errors"] == {"provider_unavailable": 1}
    assert report["truncation"] == {
        "candidate_bytes": 0,
        "following_count": 1,
        "following_bytes": 1,
    }
    assert report["latency_ms"] == {"p50": 100, "p95": 300}
    assert report["unanswered_sample_opaque_ids"] == ["opaque-a"]
    assert "private-message" not in encoded
    assert "private-key" not in encoded


def test_report_marks_interrupted_attempt_unresolved(unanswered_report, tmp_path):
    root = _root(tmp_path / "state", run_id="run-a")
    _events(
        root,
        [
            {
                "event": "candidate_started",
                "at_utc": "2026-09-23T12:00:00Z",
                "candidate_key": "private-key",
                "candidate_timestamp": "2026-09-23T10:00:00Z",
                "opaque_id": "opaque-a",
            }
        ],
    )
    report = unanswered_report.build_report([root])
    assert report["unresolved_opaque_ids"] == ["opaque-a"]


def test_report_refuses_unknown_schema(unanswered_report, tmp_path):
    root = _root(tmp_path / "state", run_id="run-a")
    (root / "state.json").write_text(json.dumps({"schema_version": 2}))
    (root / "events.jsonl").write_text("")
    try:
        unanswered_report.build_report([root])
    except unanswered_report.ReportError as exc:
        assert "unsupported state schema" in str(exc)
    else:
        raise AssertionError("unknown schema was accepted")


def test_report_applies_go_no_go_only_after_complete_window_and_confirmation(
    unanswered_report, tmp_path
):
    root = _root(tmp_path / "state", run_id="run-a")
    _events(
        root,
        [
            {
                "event": "tick",
                "at_utc": "2026-10-07T12:00:00Z",
                "eligible": True,
            }
        ],
    )
    no_go = unanswered_report.build_report([root], confirmed_real_drops=0, sample_size=5)
    assert no_go["window"]["complete_14_days"] is True
    assert no_go["go_no_go"] == "no_go_keep_retired"
    go = unanswered_report.build_report([root], confirmed_real_drops=1, sample_size=5)
    assert go["go_no_go"] == "go_follow_up_only"


def test_report_refuses_partial_or_impossible_confirmation(unanswered_report, tmp_path):
    root = _root(tmp_path / "state", run_id="run-a")
    _events(root, [])
    for drops, sample in ((1, None), (None, 1), (-1, 1), (2, 1), (0, 0)):
        try:
            unanswered_report.build_report([root], confirmed_real_drops=drops, sample_size=sample)
        except unanswered_report.ReportError:
            pass
        else:
            raise AssertionError((drops, sample))
