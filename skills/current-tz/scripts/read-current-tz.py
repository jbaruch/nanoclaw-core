#!/usr/bin/env python3
"""Resolve the operator's current IANA timezone.

The one reader of `tz_state.current_tz` every plugin shares. It used to
exist twice — `nanoclaw-admin/skills/scheduler-timezone` (with a
`home_tz` → `$TZ` → `UTC` guess ladder) and
`nanoclaw-travel/skills/flight-assist` (no guessing) — and the two had
already drifted. This copy keeps the no-guess contract: the zone the
host resolved from the operator's live location, or nothing.

Callers that need a fallback use the container `$TZ`, which since
`jbaruch/nanoclaw#954` is the operator's zone at spawn (server zone
only when the host had no `tz_state` row).

stdlib-only per `jbaruch/coding-policy: dependency-management`.

Source: the `tz_state` singleton at `/workspace/store/messages.db`
(host-owned, mounted RW in main/trusted containers). Written by the
host's location-first resolver (`jbaruch/nanoclaw#951`, `#953`,
`#955`); this script never writes.

Reader contract per `jbaruch/coding-policy: stateful-artifacts`: a
non-owner reader never migrates. A `tz_state.schema_version` other than
the supported value is treated as "no usable timezone". Bump
`SUPPORTED_TZ_STATE_SCHEMA_VERSION` in lock-step with the host-side
state-NNN migration that changes the `current_tz` shape.

Usage:
    read-current-tz.py [--now <ISO-8601 instant with offset>]

`--now` pins the instant the local fields are derived from (tests;
deterministic replays). Default: the real current UTC instant.

Stdout (single-line JSON):
    {"available": true,  "tz": "<iana>",
     "local_now": "<ISO-8601 with offset>", "local_date": "YYYY-MM-DD"}
    {"available": false, "tz": null, "local_now": null, "local_date": null}

`local_now` / `local_date` are the pinned instant expressed in `tz`, so
a caller never converts by hand (`jbaruch/coding-policy:
script-delegation`).

Exit codes:
    0 — the store was read; `available` says whether a usable zone
        came out of it (no row, empty column, unsupported
        schema_version and an unparseable zone name are all expected
        unavailable states, each with a stderr diagnostic)
    1 — the store could not be read (missing file, no `tz_state` table,
        corruption, permission). The unavailable shape is still on
        stdout so a surface caller can degrade; a scheduling caller
        treats it as a hard failure
    2 — CLI misuse (unknown argument, naive `--now`)
"""

import argparse
import json
import sqlite3
import sys
import zoneinfo
from datetime import datetime, timezone

DB_PATH = "/workspace/store/messages.db"

# Highest `tz_state.schema_version` this reader interprets. The host
# orchestrator owns `tz_state` writes; a higher version means a shape
# this reader doesn't understand, so it degrades to unavailable.
SUPPORTED_TZ_STATE_SCHEMA_VERSION = 4


class StoreUnreadable(Exception):
    """The `tz_state` store could not be read at all — an operational
    failure, distinct from a store that was read and holds no usable
    zone."""


def _emit(tz: str | None, now: datetime) -> None:
    if tz is None:
        payload = {"available": False, "tz": None, "local_now": None, "local_date": None}
    else:
        local = now.astimezone(zoneinfo.ZoneInfo(tz))
        payload = {
            "available": True,
            "tz": tz,
            "local_now": local.isoformat(timespec="seconds"),
            "local_date": local.date().isoformat(),
        }
    print(json.dumps(payload, separators=(",", ":")))


def _read_row() -> tuple[object, object] | None:
    """Return `(current_tz, schema_version)` from the singleton, or None
    when the store was read and holds no row. Raises `StoreUnreadable`
    when the store itself cannot be read."""
    conn = None
    try:
        # Read-only URI open: a non-owner reader must never create the
        # host-owned messages.db (a plain connect() would materialise an
        # empty file when the mount is missing) nor mutate it.
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        return conn.execute(
            "SELECT current_tz, schema_version FROM tz_state WHERE id = 1"
        ).fetchone()
    except sqlite3.Error as exc:
        raise StoreUnreadable(f"cannot read tz_state from {DB_PATH}: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


def resolve_current_tz() -> str | None:
    """Return the operator's `current_tz` IANA name, or None.

    None on every expected miss: `tz_state` singleton row absent,
    `current_tz` empty, `schema_version` unsupported, or the stored name
    not a valid zoneinfo zone. Each miss writes a stderr diagnostic.
    `home_tz` is deliberately NOT a fallback — the answer is where the
    operator is *now*, and a missing current_tz must not degrade to a
    guessed home zone. A store that cannot be read raises
    `StoreUnreadable`.
    """
    row = _read_row()
    if row is None:
        print(f"read-current-tz: tz_state has no singleton row at {DB_PATH}", file=sys.stderr)
        return None

    current_tz, schema_version = row
    if not isinstance(schema_version, int) or schema_version != SUPPORTED_TZ_STATE_SCHEMA_VERSION:
        print(
            f"read-current-tz: tz_state.schema_version={schema_version!r} unsupported "
            f"(reader supports {SUPPORTED_TZ_STATE_SCHEMA_VERSION})",
            file=sys.stderr,
        )
        return None

    if not isinstance(current_tz, str) or not current_tz.strip():
        print(f"read-current-tz: tz_state.current_tz empty at {DB_PATH}", file=sys.stderr)
        return None

    name = current_tz.strip()
    try:
        zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
        print(f"read-current-tz: unrecognised timezone {name!r}: {exc}", file=sys.stderr)
        return None

    return name


def _parse_now(raw: str | None) -> datetime:
    """The instant the local fields are derived from. A pinned value must
    carry an offset; a naive one is a usage error (exit 2)."""
    if raw is None:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--now is not ISO-8601: {raw!r} ({exc})") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(f"--now must carry a timezone offset: {raw!r}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="read-current-tz.py",
        description="Resolve the operator's current IANA timezone from tz_state.",
    )
    parser.add_argument(
        "--now",
        type=_parse_now,
        default=None,
        help="ISO-8601 instant with offset to derive local_now / local_date from",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits 2 on usage errors and 0 on --help; keep both.
        return int(exc.code) if isinstance(exc.code, int) else 2
    now = args.now if args.now is not None else datetime.now(timezone.utc)

    try:
        tz = resolve_current_tz()
    except StoreUnreadable as exc:
        print(f"read-current-tz: {exc}", file=sys.stderr)
        _emit(None, now)
        return 1
    _emit(tz, now)
    return 0


if __name__ == "__main__":
    sys.exit(main())
