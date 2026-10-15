#!/usr/bin/env python3
"""Aggregate body-free check-unanswered shadow data.

Usage: ``python3 scripts/check-unanswered-report.py --expected-groups MANIFEST
STATE_DIR [STATE_DIR ...] [--confirmations FILE]``.

The manifest freezes the expected body-free run IDs and deployed source revision.
The optional confirmations file contains operator judgments keyed by opaque IDs.
Success emits one strictly validated, body-free JSON report. Exit 1 emits only a
fixed diagnostic identifying the input class and never reflects private values.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

SCHEMA_VERSION = 1
MODEL = "jev-1.13.0"
QUESTION_VERSION = "unanswered-choice-v1"
LABELS = ("addressed_inline", "unanswered", "cant_tell")
MEASUREMENT_DAYS = 14
MAX_TICK_GAP_SECONDS = 60 * 60
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_FOLLOWING_MESSAGES = 40
MAX_FOLLOWING_BYTES = 32_768
MAX_CANDIDATES_PER_TICK = 50
MAX_LATENCY_MS = 120_000
MAX_TOKEN_COUNT = 10_000_000
RUN_ID_PATTERN = re.compile(r"check-unanswered-[0-9a-f]{20}")
OPAQUE_ID_PATTERN = re.compile(r"[0-9a-f]{24}")
GROUP_ID_PATTERN = re.compile(r"[0-9a-f]{20}")
SOURCE_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
ERROR_CATEGORIES = {
    "provider_unavailable",
    "provider_http_error",
    "provider_response_too_large",
    "provider_response_invalid",
    "database_unavailable",
    "group_lookup_failed",
    "group_not_registered",
    "group_config_invalid",
    "candidate_query_failed",
    "context_query_failed",
}


class ReportError(Exception):
    """A body-free refusal of malformed or incomplete private input."""


def _fail(kind: str) -> NoReturn:
    raise ReportError(f"invalid {kind}")


def _exact_keys(value: dict[str, Any], keys: set[str], kind: str) -> None:
    if set(value) != keys:
        _fail(kind)


def parse_utc(value: Any, kind: str = "timestamp") -> datetime:
    if not isinstance(value, str) or len(value) > 35:
        _fail(kind)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(kind)
    if parsed.tzinfo is None:
        _fail(kind)
    return parsed.astimezone(timezone.utc)


def _bounded_string(value: Any, maximum: int, kind: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        _fail(kind)
    return value


def _nonnegative_int(value: Any, kind: str) -> int:
    if type(value) is not int or value < 0:
        _fail(kind)
    return value


def _optional_nonnegative_int(value: Any, kind: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, kind)


def _validate_cursor(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        _fail("state cursor")
    _exact_keys(value, {"timestamp", "id"}, "state cursor")
    parse_utc(value["timestamp"], "state cursor")
    if not isinstance(value["id"], str) or len(value["id"].encode("utf-8")) > 1_024:
        _fail("state cursor")


def _validate_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("shadow state")
    _exact_keys(
        value,
        {
            "schema_version",
            "run_id",
            "group_id",
            "model",
            "question_version",
            "cursor",
            "deployment_source_revision",
            "window_start_utc",
            "lifecycle",
        },
        "shadow state",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        _fail("shadow state")
    if not isinstance(value["run_id"], str) or RUN_ID_PATTERN.fullmatch(value["run_id"]) is None:
        _fail("shadow state")
    if (
        not isinstance(value["group_id"], str)
        or GROUP_ID_PATTERN.fullmatch(value["group_id"]) is None
        or value["run_id"] != f"check-unanswered-{value['group_id']}"
    ):
        _fail("shadow state")
    if value["model"] != MODEL or value["question_version"] != QUESTION_VERSION:
        _fail("shadow state")
    _validate_cursor(value["cursor"])
    revision = value["deployment_source_revision"]
    if revision is not None and (
        not isinstance(revision, str) or SOURCE_REVISION_PATTERN.fullmatch(revision) is None
    ):
        _fail("shadow state")
    start = value["window_start_utc"]
    if start is not None:
        parse_utc(start, "shadow state")
    if value["lifecycle"] not in {
        "initializing",
        "awaiting_window_start",
        "active",
        "measurement_complete",
    }:
        _fail("shadow state")
    if start is None:
        if revision is not None or value["lifecycle"] not in {
            "initializing",
            "awaiting_window_start",
        }:
            _fail("shadow state")
    elif revision is None or value["lifecycle"] not in {"active", "measurement_complete"}:
        _fail("shadow state")
    if value["lifecycle"] != "initializing" and value["cursor"] is None:
        _fail("shadow state")
    return value


def _base_event(value: Any, kind: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        _fail(kind)
    parse_utc(value.get("at_utc"), kind)
    return value


def _validate_event(value: Any) -> dict[str, Any]:
    event = _base_event(value, "shadow event")
    name = event.get("event")
    base = {"schema_version", "event", "at_utc"}
    if name == "candidate_started":
        _exact_keys(
            event,
            base
            | {
                "candidate_key",
                "message_id",
                "candidate_timestamp",
                "opaque_id",
                "following_count",
                "following_bytes",
                "count_truncated",
                "bytes_truncated",
            },
            "candidate event",
        )
        _bounded_string(event["candidate_key"], 4_096, "candidate event")
        _bounded_string(event["message_id"], 1_024, "candidate event")
        parse_utc(event["candidate_timestamp"], "candidate event")
        if (
            not isinstance(event["opaque_id"], str)
            or OPAQUE_ID_PATTERN.fullmatch(event["opaque_id"]) is None
        ):
            _fail("candidate event")
        if _nonnegative_int(event["following_count"], "candidate event") > MAX_FOLLOWING_MESSAGES:
            _fail("candidate event")
        if _nonnegative_int(event["following_bytes"], "candidate event") > MAX_FOLLOWING_BYTES:
            _fail("candidate event")
        if type(event["count_truncated"]) is not bool or type(event["bytes_truncated"]) is not bool:
            _fail("candidate event")
    elif name == "decision":
        _exact_keys(
            event,
            base
            | {
                "candidate_key",
                "opaque_id",
                "label",
                "probabilities",
                "confidence",
                "latency_ms",
                "input_tokens",
                "output_tokens",
                "candidate_bytes_truncated",
                "model",
                "question_version",
            },
            "decision event",
        )
        _bounded_string(event["candidate_key"], 4_096, "decision event")
        if (
            not isinstance(event["opaque_id"], str)
            or OPAQUE_ID_PATTERN.fullmatch(event["opaque_id"]) is None
        ):
            _fail("decision event")
        if (
            event["label"] not in LABELS
            or event["model"] != MODEL
            or event["question_version"] != QUESTION_VERSION
        ):
            _fail("decision event")
        probabilities = event["probabilities"]
        if not isinstance(probabilities, dict) or set(probabilities) != set(LABELS):
            _fail("decision event")
        if not all(
            type(item) in (int, float) and math.isfinite(item) and 0 <= item <= 1
            for item in probabilities.values()
        ):
            _fail("decision event")
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-3):
            _fail("decision event")
        if probabilities[event["label"]] != max(probabilities.values()):
            _fail("decision event")
        confidence = event["confidence"]
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            _fail("decision event")
        if _nonnegative_int(event["latency_ms"], "decision event") > MAX_LATENCY_MS:
            _fail("decision event")
        for key in ("input_tokens", "output_tokens"):
            token_count = _optional_nonnegative_int(event[key], "decision event")
            if token_count is not None and token_count > MAX_TOKEN_COUNT:
                _fail("decision event")
        if type(event["candidate_bytes_truncated"]) is not bool:
            _fail("decision event")
    elif name == "error":
        scope = event.get("scope")
        if scope == "candidate":
            _exact_keys(
                event,
                base
                | {
                    "scope",
                    "candidate_key",
                    "opaque_id",
                    "category",
                    "latency_ms",
                    "model",
                    "question_version",
                },
                "candidate error event",
            )
            _bounded_string(event["candidate_key"], 4_096, "candidate error event")
            if (
                not isinstance(event["opaque_id"], str)
                or OPAQUE_ID_PATTERN.fullmatch(event["opaque_id"]) is None
            ):
                _fail("candidate error event")
            if _nonnegative_int(event["latency_ms"], "candidate error event") > MAX_LATENCY_MS:
                _fail("candidate error event")
            if event["model"] != MODEL or event["question_version"] != QUESTION_VERSION:
                _fail("candidate error event")
        elif scope == "tick":
            _exact_keys(event, base | {"scope", "category"}, "tick error event")
        else:
            _fail("error event")
        if event["category"] not in ERROR_CATEGORIES:
            _fail("error event")
    elif name == "tick":
        if event.get("eligible") is False:
            _exact_keys(event, base | {"eligible", "reason"}, "tick event")
            if event["reason"] != "heartbeat_disabled":
                _fail("tick event")
        else:
            _exact_keys(
                event,
                base
                | {
                    "eligible",
                    "reason",
                    "candidate_count",
                    "classified_count",
                    "error_count",
                    "deduped_count",
                    "cursor",
                    "page_full",
                    "scan_cutoff_utc",
                    "lifecycle",
                },
                "tick event",
            )
            if event["eligible"] is not True or event["reason"] not in {
                "main",
                "heartbeat_enabled",
            }:
                _fail("tick event")
            for key in ("candidate_count", "classified_count", "error_count", "deduped_count"):
                if _nonnegative_int(event[key], "tick event") > MAX_CANDIDATES_PER_TICK:
                    _fail("tick event")
            if (
                event["classified_count"] + event["error_count"] + event["deduped_count"]
                != event["candidate_count"]
            ):
                _fail("tick event")
            _validate_cursor(event["cursor"])
            if type(event["page_full"]) is not bool:
                _fail("tick event")
            parse_utc(event["scan_cutoff_utc"], "tick event")
            if event["lifecycle"] not in {
                "awaiting_window_start",
                "active",
                "measurement_complete",
            }:
                _fail("tick event")
    elif name == "window_started":
        _exact_keys(
            event,
            base
            | {
                "window_start_utc",
                "deployment_source_revision",
                "verified_tick_at_utc",
            },
            "window event",
        )
        start = parse_utc(event["window_start_utc"], "window event")
        proof = parse_utc(event["verified_tick_at_utc"], "window event")
        if start != proof:
            _fail("window event")
        revision = event["deployment_source_revision"]
        if not isinstance(revision, str) or SOURCE_REVISION_PATTERN.fullmatch(revision) is None:
            _fail("window event")
    elif name == "lifecycle":
        _exact_keys(event, base | {"status"}, "lifecycle event")
        if event["status"] != "capacity_exhausted":
            _fail("lifecycle event")
    else:
        _fail("shadow event")
    return event


def read_root(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        state_path = path / "state.json"
        events_path = path / "events.jsonl"
        if state_path.stat().st_size > 64 * 1024 or events_path.stat().st_size > MAX_INPUT_BYTES:
            _fail("shadow state root")
        state = _validate_state(json.loads(state_path.read_text(encoding="utf-8")))
        raw_lines = events_path.read_text(encoding="utf-8").splitlines()
        events = [_validate_event(json.loads(line)) for line in raw_lines]
    except FileNotFoundError:
        _fail("shadow state root")
    except OSError:
        _fail("shadow state root")
    except (UnicodeError, ValueError):
        _fail("shadow state root")
    return state, events


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > 64 * 1024:
            _fail("expected-groups manifest")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail("expected-groups manifest")
    except OSError:
        _fail("expected-groups manifest")
    except (UnicodeError, ValueError):
        _fail("expected-groups manifest")
    return validate_manifest(value)


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("expected-groups manifest")
    _exact_keys(
        value,
        {"schema_version", "deployment_source_revision", "expected_run_ids"},
        "expected-groups manifest",
    )
    revision = value["deployment_source_revision"]
    run_ids = value["expected_run_ids"]
    if (
        value["schema_version"] != SCHEMA_VERSION
        or not isinstance(revision, str)
        or SOURCE_REVISION_PATTERN.fullmatch(revision) is None
    ):
        _fail("expected-groups manifest")
    if not isinstance(run_ids, list) or not run_ids or len(run_ids) > 50:
        _fail("expected-groups manifest")
    if any(not isinstance(item, str) or RUN_ID_PATTERN.fullmatch(item) is None for item in run_ids):
        _fail("expected-groups manifest")
    if len(set(run_ids)) != len(run_ids):
        _fail("expected-groups manifest")
    return value


def read_confirmations(path: Path) -> list[dict[str, Any]]:
    try:
        if path.stat().st_size > 256 * 1024:
            _fail("operator confirmations")
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail("operator confirmations")
    except OSError:
        _fail("operator confirmations")
    except (UnicodeError, ValueError):
        _fail("operator confirmations")
    if not isinstance(value, dict):
        _fail("operator confirmations")
    _exact_keys(value, {"schema_version", "confirmations"}, "operator confirmations")
    if value["schema_version"] != SCHEMA_VERSION:
        _fail("operator confirmations")
    return validate_confirmations(value["confirmations"])


def validate_confirmations(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        _fail("operator confirmations")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            _fail("operator confirmations")
        _exact_keys(row, {"opaque_id", "real_drop"}, "operator confirmations")
        opaque = row["opaque_id"]
        if (
            not isinstance(opaque, str)
            or OPAQUE_ID_PATTERN.fullmatch(opaque) is None
            or opaque in seen
        ):
            _fail("operator confirmations")
        if type(row["real_drop"]) is not bool:
            _fail("operator confirmations")
        seen.add(opaque)
    return rows


def percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


def build_report(
    roots: list[Path],
    *,
    expected_manifest: dict[str, Any],
    confirmations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not roots:
        raise ReportError("at least one shadow state root is required")
    expected_manifest = validate_manifest(expected_manifest)
    if confirmations is not None:
        confirmations = validate_confirmations(confirmations)
    loaded = [read_root(root) for root in roots]
    states = [item[0] for item in loaded]
    run_ids = [state["run_id"] for state in states]
    if len(set(run_ids)) != len(run_ids):
        raise ReportError("duplicate run ID")
    expected = set(expected_manifest["expected_run_ids"])
    observed = set(run_ids)
    expected_revision = expected_manifest["deployment_source_revision"]
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)

    all_events: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, Any]] = {}
    capacity_exhausted = False
    for state, events in loaded:
        run_id = state["run_id"]
        capacity_exhausted = capacity_exhausted or any(
            event["event"] == "lifecycle" and event["status"] == "capacity_exhausted"
            for event in events
        )
        start_text = state["window_start_utc"]
        window_events = [event for event in events if event["event"] == "window_started"]
        if start_text is None:
            if window_events or state["deployment_source_revision"] is not None:
                _fail("window provenance")
            coverage[run_id] = {
                "window_start_utc": None,
                "required_end_utc": None,
                "observed_end_utc": None,
                "eligible_ticks": 0,
                "gap_count": 0,
                "max_gap_seconds": None,
                "population_drained": False,
                "complete": False,
            }
            all_events.extend(events)
            continue
        if len(window_events) != 1:
            _fail("window provenance")
        window_event = window_events[0]
        if (
            window_event["window_start_utc"] != start_text
            or window_event["verified_tick_at_utc"] != start_text
            or window_event["deployment_source_revision"] != state["deployment_source_revision"]
            or state["deployment_source_revision"] != expected_revision
        ):
            _fail("window provenance")
        start = parse_utc(start_text, "window provenance")
        required_end = start + timedelta(days=MEASUREMENT_DAYS)
        scoped = [event for event in events if parse_utc(event["at_utc"]) >= start]
        tick_times = sorted(
            parse_utc(event["at_utc"])
            for event in scoped
            if event["event"] == "tick" and event["eligible"] is True
        )
        if not tick_times or tick_times[0] != start:
            _fail("window provenance")
        bounded_ticks = [item for item in tick_times if item <= required_end]
        if tick_times[-1] >= required_end and bounded_ticks[-1] < required_end:
            bounded_ticks.append(required_end)
        gaps = [
            int((right - left).total_seconds())
            for left, right in zip(bounded_ticks, bounded_ticks[1:], strict=False)
        ]
        gap_count = sum(gap > MAX_TICK_GAP_SECONDS for gap in gaps)
        population_drained = state["lifecycle"] == "measurement_complete"
        complete = (
            tick_times[-1] >= required_end
            and gap_count == 0
            and population_drained
            and not capacity_exhausted
        )
        coverage[run_id] = {
            "window_start_utc": start_text,
            "required_end_utc": required_end.isoformat().replace("+00:00", "Z"),
            "observed_end_utc": tick_times[-1].isoformat().replace("+00:00", "Z"),
            "eligible_ticks": len(tick_times),
            "gap_count": gap_count,
            "max_gap_seconds": max(gaps) if gaps else None,
            "population_drained": population_drained,
            "complete": complete,
        }
        all_events.extend(scoped)

    starts: dict[str, dict[str, Any]] = {}
    terminals: dict[str, dict[str, Any]] = {}
    for event in all_events:
        key = event.get("candidate_key")
        if event["event"] == "candidate_started":
            if key in starts:
                _fail("candidate relationships")
            starts[str(key)] = event
        elif event["event"] in {"decision", "error"} and event.get("scope") != "tick":
            if key in terminals:
                _fail("candidate relationships")
            terminals[str(key)] = event
    for key, terminal in terminals.items():
        if key not in starts or starts[key]["opaque_id"] != terminal["opaque_id"]:
            _fail("candidate relationships")
    opaque_ids = [event["opaque_id"] for event in starts.values()]
    if len(set(opaque_ids)) != len(opaque_ids):
        _fail("candidate relationships")

    decisions = [event for event in terminals.values() if event["event"] == "decision"]
    candidate_errors = [event for event in terminals.values() if event["event"] == "error"]
    tick_errors = [
        event for event in all_events if event["event"] == "error" and event["scope"] == "tick"
    ]
    ticks = [event for event in all_events if event["event"] == "tick"]
    per_day = Counter(event["candidate_timestamp"][:10] for event in starts.values())
    labels = Counter(event["label"] for event in decisions)
    error_categories = Counter(event["category"] for event in candidate_errors)
    tick_error_categories = Counter(event["category"] for event in tick_errors)
    unresolved = sorted(event["opaque_id"] for key, event in starts.items() if key not in terminals)
    unanswered_ids = sorted(
        event["opaque_id"] for event in decisions if event["label"] == "unanswered"
    )
    unanswered_set = set(unanswered_ids)
    if confirmations is not None:
        confirmation_ids = {row["opaque_id"] for row in confirmations}
        if not confirmation_ids.issubset(unanswered_set):
            raise ReportError("operator confirmation does not match unanswered population")
        confirmed_real_drops = sum(row["real_drop"] for row in confirmations)
        sample_size = len(confirmations)
        reviewed_ids = sorted(confirmation_ids)
    else:
        confirmed_real_drops = None
        sample_size = None
        reviewed_ids = []
    latencies = [event["latency_ms"] for event in decisions + candidate_errors]
    all_groups_complete = (
        not capacity_exhausted
        and not missing
        and not extra
        and len(coverage) == len(expected)
        and all(item["complete"] for item in coverage.values())
    )
    if not all_groups_complete or confirmations is None:
        go_no_go = "pending"
    elif confirmed_real_drops == 0:
        go_no_go = "no_go_keep_retired"
    else:
        go_no_go = "go_follow_up_only"
    return {
        "schema_version": SCHEMA_VERSION,
        "deployment_source_revision": expected_revision,
        "group_coverage": {
            "expected_run_ids": sorted(expected),
            "observed_run_ids": sorted(observed),
            "missing_run_ids": missing,
            "extra_run_ids": extra,
            "all_groups_started": not missing
            and all(coverage[item]["window_start_utc"] is not None for item in expected),
            "by_run_id": dict(sorted(coverage.items())),
            "complete_14_days": all_groups_complete,
        },
        "tick_health": {
            "total": len(ticks),
            "eligible": sum(event["eligible"] is True for event in ticks),
            "ineligible": sum(event["eligible"] is False for event in ticks),
            "capacity_exhausted": capacity_exhausted,
        },
        "candidates_per_day": dict(sorted(per_day.items())),
        "label_distribution": {label: labels.get(label, 0) for label in LABELS},
        "provider_errors": dict(sorted(error_categories.items())),
        "tick_errors": dict(sorted(tick_error_categories.items())),
        "truncation": {
            "candidate_bytes": sum(event["candidate_bytes_truncated"] for event in decisions),
            "following_count": sum(event["count_truncated"] for event in starts.values()),
            "following_bytes": sum(event["bytes_truncated"] for event in starts.values()),
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "unresolved_opaque_ids": unresolved,
        "unanswered_sample_opaque_ids": unanswered_ids,
        "operator_confirmation": {
            "reviewed_opaque_ids": reviewed_ids,
            "confirmed_real_drops": confirmed_real_drops,
            "sample_size": sample_size,
        },
        "go_no_go": go_no_go,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Aggregate check-unanswered shadow state")
    result.add_argument("state_dirs", nargs="+", type=Path)
    result.add_argument("--expected-groups", required=True, type=Path)
    result.add_argument("--confirmations", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = build_report(
            args.state_dirs,
            expected_manifest=read_manifest(args.expected_groups),
            confirmations=(read_confirmations(args.confirmations) if args.confirmations else None),
        )
    except ReportError as exc:
        print(f"check-unanswered report failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
