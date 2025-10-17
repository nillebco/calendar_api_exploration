#!/usr/bin/env python3

import argparse
import sys
import csv
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

import requests
from dateutil import tz, parser as dtparser
from icalendar import Calendar, Event
import recurring_ical_events


def load_ics(source: str) -> bytes:
    # Fetch ICS from URL or read from local file
    if source.lower().startswith(("http://", "https://")):
        resp = requests.get(source, timeout=30)
        resp.raise_for_status()
        return resp.content
    else:
        with open(source, "rb") as f:
            return f.read()


def ensure_timezone(dt, default_tz: tz.tzoffset) -> datetime:
    # Convert naive datetimes to default timezone, keep aware ones as-is
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=default_tz)
        return dt
    # Some all-day events may be dates; convert to midnight in default tz
    if hasattr(dt, "year") and hasattr(dt, "month") and hasattr(dt, "day"):
        return datetime(dt.year, dt.month, dt.day, tzinfo=default_tz)
    return dt


def normalize_to_tz(dt: datetime, target_tz: tz.tzoffset) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(target_tz)


def expand_events(
    cal: Calendar, start: datetime, end: datetime, default_tz: tz.tzoffset
) -> List[Event]:
    # recurring_ical_events handles RRULE/EXDATE/RECURRENCE-ID expansion
    events = recurring_ical_events.of(cal).between(start, end)
    # Also include non-recurring events that fall in range (library should cover this, but be explicit)
    return events


def serialize_event(
    evt: Event, target_tz: tz.tzoffset, default_tz: tz.tzoffset
) -> Dict[str, Any]:
    def get_prop(name: str):
        return evt.get(name)

    uid = str(get_prop("UID") or "")
    summary = str(get_prop("SUMMARY") or "")
    description = str(get_prop("DESCRIPTION") or "")
    location = str(get_prop("LOCATION") or "")
    organizer = str(get_prop("ORGANIZER") or "")

    dtstart = get_prop("DTSTART").dt if get_prop("DTSTART") else None
    dtend = get_prop("DTEND").dt if get_prop("DTEND") else None
    all_day = False

    # Convert naive -> default_tz, then to target_tz
    if dtstart is not None:
        if not isinstance(dtstart, datetime):
            # date instance => all-day
            all_day = True
            dtstart = ensure_timezone(dtstart, default_tz)
        else:
            dtstart = ensure_timezone(dtstart, default_tz)
        dtstart = normalize_to_tz(dtstart, target_tz)

    if dtend is not None:
        if not isinstance(dtend, datetime):
            all_day = True
            dtend = ensure_timezone(dtend, default_tz)
        else:
            dtend = ensure_timezone(dtend, default_tz)
        dtend = normalize_to_tz(dtend, target_tz)

    # Some feeds omit DTEND for all-day events; infer using DURATION or +1 day rule
    if dtstart and not dtend:
        duration = get_prop("DURATION")
        if duration:
            dtend = dtstart + duration.dt
        else:
            # RFC 5545: if no DTEND, treat as zero-duration; for all-day, make it 1-day
            dtend = dtstart + (timedelta(days=1) if all_day else timedelta(minutes=0))

    # Attendees (optional)
    attendees = []
    if "ATTENDEE" in evt:
        raw = evt.get("ATTENDEE")
        if isinstance(raw, list):
            attendees.extend([str(x) for x in raw])
        else:
            attendees.append(str(raw))

    transparency = str(get_prop("TRANSP") or "")
    status = str(get_prop("STATUS") or "")
    categories = get_prop("CATEGORIES")
    if isinstance(categories, list):
        categories = [str(c) for c in categories]
    elif categories is not None:
        categories = [str(categories)]

    return {
        "uid": uid,
        "summary": summary,
        "description": description,
        "location": location,
        "organizer": organizer,
        "start": dtstart.isoformat() if dtstart else None,
        "end": dtend.isoformat() if dtend else None,
        "all_day": all_day,
        "status": status,
        "transparency": transparency,
        "categories": categories,
        "raw_class": str(get_prop("CLASS") or ""),
        "attendees": attendees,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Read and expand events from an ICS feed (URL or file)."
    )
    p.add_argument("--source", required=True, help="ICS URL or local .ics file path")
    p.add_argument(
        "--start",
        help="Start datetime (e.g., 2025-01-01 or 2025-01-01T00:00). Defaults: now-7d.",
    )
    p.add_argument(
        "--end",
        help="End datetime (e.g., 2025-12-31 or 2025-12-31T23:59). Defaults: now+90d.",
    )
    p.add_argument(
        "--tz",
        default="Europe/Paris",
        help="Target timezone for output (default: Europe/Paris)",
    )
    p.add_argument(
        "--default-tz",
        default="UTC",
        help="Assumed tz for naive datetimes in feed (default: UTC)",
    )
    p.add_argument(
        "--output",
        choices=["json", "csv"],
        default="json",
        help="Output format (default: json)",
    )
    p.add_argument(
        "--limit", type=int, default=0, help="Limit number of events (0 = no limit)"
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    target_tz = tz.gettz(args.tz)
    default_tz = tz.gettz(args.default_tz)

    now = datetime.now(timezone.utc)
    start = (
        dtparser.parse(args.start).astimezone(timezone.utc)
        if args.start
        else (now - timedelta(days=7))
    )
    end = (
        dtparser.parse(args.end).astimezone(timezone.utc)
        if args.end
        else (now + timedelta(days=90))
    )

    ics_bytes = load_ics(args.source)
    cal = Calendar.from_ical(ics_bytes)

    events = expand_events(cal, start, end, default_tz)

    rows = []
    for e in events:
        rows.append(serialize_event(e, target_tz, default_tz))

    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    if args.output == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        # CSV
        fieldnames = [
            "uid",
            "summary",
            "description",
            "location",
            "organizer",
            "start",
            "end",
            "all_day",
            "status",
            "transparency",
            "categories",
            "raw_class",
        ]
        w = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            # Flatten categories for CSV
            r = dict(r)
            if isinstance(r.get("categories"), list):
                r["categories"] = ";".join(r["categories"])
            w.writerow(r)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
