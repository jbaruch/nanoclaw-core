"""Body-free aggregation for check-unanswered shadow state."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REVISION = "a" * 40
RUN_A = "check-unanswered-" + "1" * 20
RUN_B = "check-unanswered-" + "2" * 20
OPAQUE_A = "a" * 24
OPAQUE_B = "b" * 24
OPAQUE_C = "c" * 24
OPAQUE_D = "d" * 24
START = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _utc(value):
    return value.isoformat().replace("+00:00", "Z")


def _state(path: Path, *, run_id: str, start=None, lifecycle="initializing"):
    path.mkdir()
    (path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "group_id": run_id.removeprefix("check-unanswered-"),
                "model": "jev-1.13.0",
                "question_version": "unanswered-choice-v1",
                "cursor": (
                    None
                    if lifecycle == "initializing"
                    else {"timestamp": _utc(START), "id": "\uffff"}
                ),
                "deployment_source_revision": REVISION if start is not None else None,
                "window_start_utc": _utc(start) if start is not None else None,
                "lifecycle": lifecycle,
            }
        )
    )
    return path


def _write_events(path: Path, rows):
    (path / "events.jsonl").write_text(
        "".join(json.dumps({"schema_version": 1, **row}) + "\n" for row in rows)
    )


def _candidate(opaque=OPAQUE_A, *, timestamp=START, key=None):
    return {
        "event": "candidate_started",
        "at_utc": _utc(START),
        "candidate_key": key or "private-key-" + opaque,
        "message_id": "private-message-" + opaque,
        "candidate_timestamp": _utc(timestamp),
        "opaque_id": opaque,
        "following_count": 1,
        "following_bytes": 100,
        "count_truncated": True,
        "bytes_truncated": False,
    }


def _decision(opaque=OPAQUE_A, label="unanswered", probabilities=None, *, key=None):
    return {
        "event": "decision",
        "at_utc": _utc(START + timedelta(seconds=1)),
        "candidate_key": key or "private-key-" + opaque,
        "opaque_id": opaque,
        "label": label,
        "probabilities": probabilities
        or {
            "addressed_inline": 0.1,
            "unanswered": 0.8,
            "cant_tell": 0.1,
        },
        "confidence": 0.8,
        "latency_ms": 100,
        "input_tokens": 12,
        "output_tokens": 3,
        "candidate_bytes_truncated": False,
        "model": "jev-1.13.0",
        "question_version": "unanswered-choice-v1",
    }


def _candidate_error(opaque=OPAQUE_A, *, key=None):
    return {
        "event": "error",
        "at_utc": _utc(START + timedelta(seconds=1)),
        "scope": "candidate",
        "candidate_key": key or "private-key-" + opaque,
        "opaque_id": opaque,
        "category": "provider_unavailable",
        "latency_ms": 100,
        "model": "jev-1.13.0",
        "question_version": "unanswered-choice-v1",
    }


def _tick(at, *, lifecycle="active"):
    return {
        "event": "tick",
        "at_utc": _utc(at),
        "eligible": True,
        "reason": "main",
        "candidate_count": 0,
        "classified_count": 0,
        "error_count": 0,
        "deduped_count": 0,
        "cursor": {"timestamp": _utc(at - timedelta(seconds=60)), "id": "\uffff"},
        "page_full": False,
        "scan_cutoff_utc": _utc(at - timedelta(seconds=60)),
        "lifecycle": lifecycle,
    }


def _window_event():
    return {
        "event": "window_started",
        "at_utc": _utc(START),
        "window_start_utc": _utc(START),
        "deployment_source_revision": REVISION,
        "verified_tick_at_utc": _utc(START),
    }


def _manifest(*run_ids):
    return {
        "schema_version": 1,
        "deployment_source_revision": REVISION,
        "expected_run_ids": list(run_ids),
    }


def _complete_events(*extra):
    ticks = [_tick(START + timedelta(hours=hour)) for hour in range(14 * 24 + 1)]
    ticks[-1]["lifecycle"] = "measurement_complete"
    return [ticks[0], _window_event(), *extra, *ticks[1:]]


def test_report_aggregates_without_private_locators(unanswered_report, tmp_path):
    first = _state(tmp_path / "first", run_id=RUN_A, start=START, lifecycle="active")
    second = _state(tmp_path / "second", run_id=RUN_B, start=START, lifecycle="active")
    _write_events(first, [_tick(START), _window_event(), _candidate(), _decision()])
    _write_events(second, [_tick(START), _window_event(), _candidate(OPAQUE_B)])
    report = unanswered_report.build_report(
        [first, second], expected_manifest=_manifest(RUN_A, RUN_B)
    )
    encoded = json.dumps(report)
    assert report["group_coverage"]["complete_14_days"] is False
    assert report["candidates_per_day"] == {"2026-09-23": 2}
    assert report["label_distribution"]["unanswered"] == 1
    assert report["unresolved_opaque_ids"] == [OPAQUE_B]
    assert report["unanswered_sample_opaque_ids"] == [OPAQUE_A]
    assert "private-message" not in encoded
    assert "private-key" not in encoded


def test_report_refuses_decision_label_below_probability_maximum(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A)
    _write_events(
        root,
        [
            _candidate(),
            _decision(
                probabilities={
                    "addressed_inline": 0.8,
                    "unanswered": 0.1,
                    "cant_tell": 0.1,
                }
            ),
        ],
    )
    with pytest.raises(unanswered_report.ReportError, match="invalid decision event"):
        unanswered_report.build_report([root], expected_manifest=_manifest(RUN_A))


@pytest.mark.parametrize("label", ["addressed_inline", "unanswered"])
def test_report_accepts_either_tied_maximum(unanswered_report, tmp_path, label):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="active")
    _write_events(
        root,
        [
            _tick(START),
            _window_event(),
            _candidate(),
            _decision(
                label=label,
                probabilities={
                    "addressed_inline": 0.45,
                    "unanswered": 0.45,
                    "cant_tell": 0.1,
                },
            ),
        ],
    )
    report = unanswered_report.build_report([root], expected_manifest=_manifest(RUN_A))
    assert report["label_distribution"][label] == 1


def test_sparse_window_stays_pending_and_reports_gap(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(
        root,
        [
            _tick(START),
            _window_event(),
            _tick(START + timedelta(days=14), lifecycle="measurement_complete"),
        ],
    )
    report = unanswered_report.build_report(
        [root],
        expected_manifest=_manifest(RUN_A),
    )
    coverage = report["group_coverage"]["by_run_id"][RUN_A]
    assert coverage["gap_count"] == 1
    assert report["group_coverage"]["complete_14_days"] is False
    assert report["go_no_go"] == "pending"


def test_complete_window_and_keyed_confirmations_drive_go_no_go(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(root, _complete_events(_candidate(), _decision()))
    no_go = unanswered_report.build_report(
        [root],
        expected_manifest=_manifest(RUN_A),
        confirmations=[{"opaque_id": OPAQUE_A, "real_drop": False}],
    )
    assert no_go["group_coverage"]["complete_14_days"] is True
    assert no_go["operator_confirmation"]["sample_size"] == 1
    assert no_go["operator_confirmation"]["confirmation_complete"] is True
    assert no_go["operator_confirmation"]["real_dropped_message_rate"] == 0.0
    assert no_go["go_no_go"] == "no_go_keep_retired"
    go = unanswered_report.build_report(
        [root],
        expected_manifest=_manifest(RUN_A),
        confirmations=[{"opaque_id": OPAQUE_A, "real_drop": True}],
    )
    assert go["operator_confirmation"]["real_dropped_message_rate"] == 1.0
    assert go["go_no_go"] == "go_follow_up_only"


def test_provider_failure_keeps_complete_window_pending(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(
        root,
        _complete_events(
            _candidate(OPAQUE_A),
            _candidate_error(OPAQUE_A),
            _candidate(OPAQUE_B),
            _decision(OPAQUE_B),
        ),
    )
    report = unanswered_report.build_report(
        [root],
        expected_manifest=_manifest(RUN_A),
        confirmations=[{"opaque_id": OPAQUE_B, "real_drop": False}],
    )
    assert report["provider_errors"] == {"provider_unavailable": 1}
    assert report["candidate_population_complete"] is False
    assert report["group_coverage"]["complete_14_days"] is False
    assert report["go_no_go"] == "pending"


def test_interrupted_candidate_keeps_complete_window_pending(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(root, _complete_events(_candidate()))
    report = unanswered_report.build_report([root], expected_manifest=_manifest(RUN_A))
    assert report["unresolved_opaque_ids"] == [OPAQUE_A]
    assert report["candidate_population_complete"] is False
    assert report["group_coverage"]["complete_14_days"] is False
    assert report["go_no_go"] == "pending"


def test_candidate_population_uses_exact_window_boundaries(unanswered_report, tmp_path):
    end = START + timedelta(days=14)
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(
        root,
        _complete_events(
            _candidate(OPAQUE_A, timestamp=START - timedelta(microseconds=1)),
            _decision(OPAQUE_A),
            _candidate(OPAQUE_B, timestamp=START),
            _decision(OPAQUE_B),
            _candidate(OPAQUE_C, timestamp=end - timedelta(microseconds=1)),
            _decision(OPAQUE_C),
            _candidate(OPAQUE_D, timestamp=end),
            _decision(OPAQUE_D),
        ),
    )
    report = unanswered_report.build_report([root], expected_manifest=_manifest(RUN_A))
    assert report["candidates_per_day"] == {"2026-09-23": 1, "2026-10-07": 1}
    assert report["label_distribution"]["unanswered"] == 2
    assert report["unanswered_sample_opaque_ids"] == [OPAQUE_B, OPAQUE_C]


def test_terminal_must_belong_to_candidate_group(unanswered_report, tmp_path):
    first = _state(tmp_path / "first", run_id=RUN_A, start=START, lifecycle="active")
    second = _state(tmp_path / "second", run_id=RUN_B, start=START, lifecycle="active")
    _write_events(first, [_tick(START), _window_event(), _candidate()])
    _write_events(second, [_tick(START), _window_event(), _decision()])
    with pytest.raises(unanswered_report.ReportError, match="invalid candidate relationships"):
        unanswered_report.build_report([first, second], expected_manifest=_manifest(RUN_A, RUN_B))


def test_candidate_keys_are_scoped_to_their_group(unanswered_report, tmp_path):
    shared_key = "same-private-key"
    first = _state(tmp_path / "first", run_id=RUN_A, start=START, lifecycle="active")
    second = _state(tmp_path / "second", run_id=RUN_B, start=START, lifecycle="active")
    _write_events(
        first,
        [
            _tick(START),
            _window_event(),
            _candidate(OPAQUE_A, key=shared_key),
            _decision(OPAQUE_A, key=shared_key),
        ],
    )
    _write_events(
        second,
        [
            _tick(START),
            _window_event(),
            _candidate(OPAQUE_B, key=shared_key),
            _decision(OPAQUE_B, key=shared_key),
        ],
    )
    report = unanswered_report.build_report(
        [first, second], expected_manifest=_manifest(RUN_A, RUN_B)
    )
    assert report["label_distribution"]["unanswered"] == 2


def test_incomplete_confirmation_census_stays_pending(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(
        root,
        _complete_events(
            _candidate(OPAQUE_A),
            _decision(OPAQUE_A),
            _candidate(OPAQUE_B),
            _decision(OPAQUE_B),
        ),
    )
    report = unanswered_report.build_report(
        [root],
        expected_manifest=_manifest(RUN_A),
        confirmations=[{"opaque_id": OPAQUE_A, "real_drop": False}],
    )
    assert report["operator_confirmation"]["confirmation_complete"] is False
    assert report["operator_confirmation"]["real_dropped_message_rate"] is None
    assert report["go_no_go"] == "pending"


def test_complete_confirmation_census_reports_exact_rate(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(
        root,
        _complete_events(
            _candidate(OPAQUE_A),
            _decision(OPAQUE_A),
            _candidate(OPAQUE_B),
            _decision(OPAQUE_B),
        ),
    )
    report = unanswered_report.build_report(
        [root],
        expected_manifest=_manifest(RUN_A),
        confirmations=[
            {"opaque_id": OPAQUE_A, "real_drop": True},
            {"opaque_id": OPAQUE_B, "real_drop": False},
        ],
    )
    assert report["operator_confirmation"]["confirmation_complete"] is True
    assert report["operator_confirmation"]["real_dropped_message_rate"] == 0.5
    assert report["go_no_go"] == "go_follow_up_only"


def test_confirmation_must_name_unique_unanswered_decision(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A, start=START, lifecycle="measurement_complete")
    _write_events(root, _complete_events(_candidate(), _decision()))
    with pytest.raises(unanswered_report.ReportError, match="does not match"):
        unanswered_report.build_report(
            [root],
            expected_manifest=_manifest(RUN_A),
            confirmations=[{"opaque_id": OPAQUE_B, "real_drop": False}],
        )
    with pytest.raises(unanswered_report.ReportError, match="operator confirmations"):
        unanswered_report.build_report(
            [root],
            expected_manifest=_manifest(RUN_A),
            confirmations=[
                {"opaque_id": OPAQUE_A, "real_drop": False},
                {"opaque_id": OPAQUE_A, "real_drop": False},
            ],
        )


def test_expected_group_manifest_exposes_omission(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A)
    _write_events(root, [])
    report = unanswered_report.build_report([root], expected_manifest=_manifest(RUN_A, RUN_B))
    assert report["group_coverage"]["missing_run_ids"] == [RUN_B]
    assert report["group_coverage"]["all_groups_started"] is False
    assert report["go_no_go"] == "pending"


def test_duplicate_run_id_is_refused(unanswered_report, tmp_path):
    first = _state(tmp_path / "first", run_id=RUN_A)
    second = _state(tmp_path / "second", run_id=RUN_A)
    _write_events(first, [])
    _write_events(second, [])
    with pytest.raises(unanswered_report.ReportError, match="duplicate run ID"):
        unanswered_report.build_report([first, second], expected_manifest=_manifest(RUN_A))


def test_strict_validation_does_not_reflect_private_canary(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A)
    state = json.loads((root / "state.json").read_text())
    state["PRIVATE-CANARY"] = "PRIVATE-CANARY"
    (root / "state.json").write_text(json.dumps(state))
    _write_events(root, [])
    with pytest.raises(unanswered_report.ReportError) as caught:
        unanswered_report.build_report([root], expected_manifest=_manifest(RUN_A))
    assert "PRIVATE-CANARY" not in str(caught.value)


def test_report_refuses_unknown_schema(unanswered_report, tmp_path):
    root = _state(tmp_path / "state", run_id=RUN_A)
    state = json.loads((root / "state.json").read_text())
    state["schema_version"] = 2
    (root / "state.json").write_text(json.dumps(state))
    _write_events(root, [])
    with pytest.raises(unanswered_report.ReportError, match="invalid shadow state"):
        unanswered_report.build_report([root], expected_manifest=_manifest(RUN_A))


@pytest.mark.parametrize(
    ("target_name", "operation", "expected_diagnostic"),
    [
        ("state", "stat", "invalid shadow state root"),
        ("state", "read_text", "invalid shadow state root"),
        ("events", "stat", "invalid shadow state root"),
        ("events", "read_text", "invalid shadow state root"),
        ("manifest", "stat", "invalid expected-groups manifest"),
        ("manifest", "read_text", "invalid expected-groups manifest"),
        ("confirmations", "stat", "invalid operator confirmations"),
        ("confirmations", "read_text", "invalid operator confirmations"),
    ],
)
def test_cli_normalizes_filesystem_failures_without_private_paths(
    unanswered_report,
    tmp_path,
    monkeypatch,
    capsys,
    target_name,
    operation,
    expected_diagnostic,
):
    module = unanswered_report
    root = _state(tmp_path / "PRIVATE-CANARY-state", run_id=RUN_A)
    _write_events(root, [])
    manifest = tmp_path / "PRIVATE-CANARY-manifest.json"
    manifest.write_text(json.dumps(_manifest(RUN_A)))
    confirmations = tmp_path / "PRIVATE-CANARY-confirmations.json"
    confirmations.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "confirmations": [{"opaque_id": OPAQUE_A, "real_drop": False}],
            }
        )
    )
    targets = {
        "state": root / "state.json",
        "events": root / "events.jsonl",
        "manifest": manifest,
        "confirmations": confirmations,
    }
    target = targets[target_name]
    original = getattr(Path, operation)

    def fail_selected(path, *args, **kwargs):
        if path == target:
            raise PermissionError(f"PRIVATE-CANARY {path}")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, operation, fail_selected)
    result = module.main(
        [
            str(root),
            "--expected-groups",
            str(manifest),
            "--confirmations",
            str(confirmations),
        ]
    )
    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert expected_diagnostic in captured.err
    assert "PRIVATE-CANARY" not in captured.err
