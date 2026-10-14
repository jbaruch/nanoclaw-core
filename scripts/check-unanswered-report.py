#!/usr/bin/env python3
"""Aggregate body-free check-unanswered shadow data.

Usage: ``python3 scripts/check-unanswered-report.py STATE_DIR [STATE_DIR ...]``.
Each directory must contain ``state.json`` and ``events.jsonl`` at schema
version 1. Success emits one JSON object with window bounds, eligible-group
run IDs, tick health, candidates per UTC day, label distribution, provider
error categories, truncation counts, unresolved attempts, latency p50/p95,
and opaque IDs awaiting operator confirmation. No private message locator or
message content leaves the input state roots.

Exit 1 names an actionable state error on stderr and emits no stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
LABELS = ("addressed_inline", "unanswered", "cant_tell")


class ReportError(Exception):
    pass


def read_root(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        state = json.loads((path / "state.json").read_text(encoding="utf-8"))
        lines = (path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        events = [json.loads(line) for line in lines]
    except FileNotFoundError as exc:
        raise ReportError(f"missing shadow state under {path}") from exc
    except (UnicodeError, ValueError) as exc:
        raise ReportError(f"invalid shadow state under {path}") from exc
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise ReportError(f"unsupported state schema under {path}")
    if any(
        not isinstance(event, dict) or event.get("schema_version") != SCHEMA_VERSION
        for event in events
    ):
        raise ReportError(f"unsupported event schema under {path}")
    return state, events


def percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ReportError("state timestamp has no UTC offset")
    return parsed


def build_report(
    roots: list[Path],
    *,
    confirmed_real_drops: int | None = None,
    sample_size: int | None = None,
) -> dict[str, Any]:
    if (confirmed_real_drops is None) != (sample_size is None):
        raise ReportError("provide both operator-confirmation counts or neither")
    if confirmed_real_drops is not None and (
        confirmed_real_drops < 0
        or sample_size is None
        or sample_size <= 0
        or confirmed_real_drops > sample_size
    ):
        raise ReportError("operator-confirmation counts must satisfy 0 <= drops <= sample size")
    states: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    durations: dict[str, int | None] = {}
    for root in roots:
        state, events = read_root(root)
        states.append(state)
        start_text = state.get("window_start_utc")
        if start_text is None:
            all_events.extend(events)
            durations[str(state.get("run_id"))] = None
            continue
        try:
            start = parse_utc(str(start_text))
            scoped = [
                event
                for event in events
                if event.get("at_utc") is not None and parse_utc(str(event["at_utc"])) >= start
            ]
        except (TypeError, ValueError) as exc:
            raise ReportError(f"invalid state timestamp under {root}") from exc
        all_events.extend(scoped)
        tick_times = [
            parse_utc(str(event["at_utc"]))
            for event in scoped
            if event.get("event") == "tick" and event.get("at_utc") is not None
        ]
        durations[str(state.get("run_id"))] = (
            max(0, int((max(tick_times) - start).total_seconds())) if tick_times else 0
        )
    starts = [event for event in all_events if event.get("event") == "candidate_started"]
    terminals = {
        str(event.get("candidate_key")): event
        for event in all_events
        if event.get("event") in {"decision", "error"}
    }
    decisions = [event for event in all_events if event.get("event") == "decision"]
    errors = [event for event in all_events if event.get("event") == "error"]
    candidate_errors = [event for event in errors if event.get("scope") == "candidate"]
    tick_errors = [event for event in errors if event.get("scope") == "tick"]
    ticks = [event for event in all_events if event.get("event") == "tick"]
    per_day = Counter(str(event.get("candidate_timestamp", ""))[:10] for event in starts)
    per_day.pop("", None)
    labels = Counter(str(event.get("label")) for event in decisions)
    error_categories = Counter(str(event.get("category")) for event in candidate_errors)
    tick_error_categories = Counter(str(event.get("category")) for event in tick_errors)
    unresolved = [
        str(event.get("opaque_id"))
        for event in starts
        if str(event.get("candidate_key")) not in terminals
    ]
    unanswered_ids = [
        str(event.get("opaque_id")) for event in decisions if event.get("label") == "unanswered"
    ]
    latencies = [
        int(event["latency_ms"])
        for event in decisions + candidate_errors
        if type(event.get("latency_ms")) is int
    ]
    window_starts = sorted(
        str(state["window_start_utc"])
        for state in states
        if state.get("window_start_utc") is not None
    )
    event_times = sorted(str(event.get("at_utc")) for event in ticks if event.get("at_utc"))
    complete = len(window_starts) == len(states) and all(
        duration is not None and duration >= int(timedelta(days=14).total_seconds())
        for duration in durations.values()
    )
    if not complete or confirmed_real_drops is None:
        go_no_go = "pending"
    elif confirmed_real_drops == 0:
        go_no_go = "no_go_keep_retired"
    else:
        go_no_go = "go_follow_up_only"
    return {
        "schema_version": SCHEMA_VERSION,
        "window": {
            "starts_utc": window_starts,
            "observed_end_utc": event_times[-1] if event_times else None,
            "all_groups_started": len(window_starts) == len(states),
            "duration_seconds_by_group": dict(sorted(durations.items())),
            "complete_14_days": complete,
        },
        "eligible_groups": sorted(str(state.get("run_id")) for state in states),
        "tick_health": {
            "total": len(ticks),
            "eligible": sum(event.get("eligible") is True for event in ticks),
            "ineligible": sum(event.get("eligible") is False for event in ticks),
        },
        "candidates_per_day": dict(sorted(per_day.items())),
        "label_distribution": {label: labels.get(label, 0) for label in LABELS},
        "provider_errors": dict(sorted(error_categories.items())),
        "tick_errors": dict(sorted(tick_error_categories.items())),
        "truncation": {
            "candidate_bytes": sum(
                event.get("candidate_bytes_truncated") is True for event in decisions
            ),
            "following_count": sum(event.get("count_truncated") is True for event in starts),
            "following_bytes": sum(event.get("bytes_truncated") is True for event in starts),
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
        },
        "unresolved_opaque_ids": sorted(unresolved),
        "unanswered_sample_opaque_ids": sorted(unanswered_ids),
        "operator_confirmation": {
            "confirmed_real_drops": confirmed_real_drops,
            "sample_size": sample_size,
        },
        "go_no_go": go_no_go,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Aggregate check-unanswered shadow state")
    result.add_argument("state_dirs", nargs="+", type=Path)
    result.add_argument("--confirmed-real-drops", type=int)
    result.add_argument("--sample-size", type=int)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = build_report(
            args.state_dirs,
            confirmed_real_drops=args.confirmed_real_drops,
            sample_size=args.sample_size,
        )
    except ReportError as exc:
        print(f"check-unanswered report failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
