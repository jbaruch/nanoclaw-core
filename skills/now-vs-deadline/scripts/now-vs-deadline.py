#!/usr/bin/env python3
"""
Compare a deadline against the real current instant — deterministically.

Invoked from `rules/temporal-awareness.md` before any past/future,
"deadline elapsed", or "still time to act" framing. LLMs default to
treating all information as present-tense: they convert a local
deadline to UTC correctly and then assert "already passed" from vibes
without ever comparing the two instants. This helper does the
comparison so the model never has to eyeball it.

Reference incident (2026-06-12): a flight-assist alert declared the
15:00 UTC (11:00 EDT) Hertz pickup deadline "already passed" at
13:10 UTC — ~2h *before* it. The offset conversion was right; the
comparison against `now` never happened.

Location-agnostic by design: this compares *instants* only. The
caller resolves any local wall-clock deadline to a timezone-aware
instant (the offset conversion, e.g. 11:00 EDT -> 15:00 UTC) and
passes it in. The past/future result is offset-independent, so no
physical location and no `current_tz` lookup is needed here.
Interpreting relative phrasings ("today"/"now"/"сейчас"/"here") into a
local frame stays in the trusted plugin.

Usage:
    python3 .../now-vs-deadline.py --deadline "2026-06-12T15:00:00Z"
    python3 .../now-vs-deadline.py --deadline "2026-06-12T11:00:00-04:00"

Output (stdout, single-line JSON):
    {
      "now": "<ISO8601 UTC>",
      "deadline": "<ISO8601 UTC>",
      "relation": "past" | "future" | "now",
      "delta_seconds": int,        # int(delta.total_seconds()) — truncates
                                   # toward zero. Sign is meaningful only
                                   # when non-zero (>0 future, <0 past);
                                   # a sub-second past/future delta reads
                                   # 0 while `relation` still says "past"
                                   # or "future". `relation` is the
                                   # authority — never classify from
                                   # delta_seconds alone.
      "delta_text": str,           # e.g. "1h 49m from now", "2h 30m ago"
      "deadline_elapsed": bool,    # relation == "past"
      "still_time_to_act": bool,   # relation == "future"
      "error": null
    }

Exit codes:
    0 — clean success (JSON on stdout).
    2 — usage error: --deadline missing, unparseable, or naive (no
        timezone offset). Diagnostic on stderr, no JSON.
"""

import argparse
import datetime
import json
import sys
from typing import Optional


def parse_deadline(value: str) -> datetime.datetime:
    """Parse an ISO8601 deadline and require it to be timezone-aware.

    A naive datetime (no offset / no `Z`) is rejected: comparing it
    against `now` would silently assume the host timezone and reopen
    the exact "asserted from vibes" failure this helper exists to
    close. The caller must resolve the local->UTC offset first.
    """
    raw = value.strip()
    if not raw:
        raise ValueError("deadline is empty")
    # `datetime.fromisoformat` only learned to accept a trailing `Z`
    # in 3.11; normalize it so the helper behaves the same on 3.7-3.10.
    normalized = raw[:-1] + "+00:00" if raw[-1:] in ("Z", "z") else raw
    dt = datetime.datetime.fromisoformat(normalized)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(
            "deadline has no timezone offset; include 'Z' or '+HH:MM' "
            "(resolve the local->UTC offset before calling)"
        )
    return dt


def _iso_utc(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _humanize(delta_seconds: int, relation: str) -> str:
    """Render a magnitude + direction as 'Xd Yh Zm from now' / '... ago'.

    Driven by `relation` (not the sign of `delta_seconds`) so it stays
    consistent with the comparison: a sub-second delta truncates to 0
    here but is still 'past'/'future', rendered as '<1s'.
    """
    if relation == "now":
        return "now"
    seconds = abs(delta_seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:  # sub-minute magnitude
        parts.append(f"{seconds}s" if seconds else "<1s")
    body = " ".join(parts)
    return f"{body} ago" if relation == "past" else f"{body} from now"


def compare(now: datetime.datetime, deadline: datetime.datetime) -> dict:
    """Pure function — takes `now` as input so tests can pin time.

    Both inputs must be timezone-aware; subtracting aware datetimes
    compares true instants regardless of their offsets.
    """
    delta = deadline - now
    # Decide past/future from the raw timedelta, not from
    # int(total_seconds()): the int truncates toward zero, so a deadline
    # a fraction of a second in the past/future would otherwise round to
    # 0 and be mislabelled "now".
    if delta > datetime.timedelta(0):
        relation = "future"
    elif delta < datetime.timedelta(0):
        relation = "past"
    else:
        relation = "now"
    delta_seconds = int(delta.total_seconds())
    return {
        "now": _iso_utc(now),
        "deadline": _iso_utc(deadline),
        "relation": relation,
        "delta_seconds": delta_seconds,
        "delta_text": _humanize(delta_seconds, relation),
        "deadline_elapsed": relation == "past",
        "still_time_to_act": relation == "future",
        "error": None,
    }


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare a deadline against the current instant.",
    )
    parser.add_argument(
        "--deadline",
        help="ISO8601 deadline WITH a timezone offset (e.g. "
        "2026-06-12T15:00:00Z or 2026-06-12T11:00:00-04:00).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if not args.deadline:
        sys.stderr.write("Usage error: --deadline is required.\n")
        return 2

    try:
        deadline = parse_deadline(args.deadline)
    except ValueError as e:
        sys.stderr.write(f"Usage error: could not parse --deadline {args.deadline!r}: {e}.\n")
        return 2

    now = datetime.datetime.now(datetime.timezone.utc)
    print(json.dumps(compare(now, deadline)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
