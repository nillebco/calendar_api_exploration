import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# Scopes needed to create/update calendar events for the signed-in user
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


def build_event_payload(
    summary: str,
    start: str,
    end: str,
    timezone: str,
    description: Optional[str],
    location: Optional[str],
) -> Dict[str, Any]:
    for label, value in (("start", start), ("end", end)):
        try:
            datetime.fromisoformat(value)
        except ValueError as err:
            raise SystemExit(f"Invalid {label} datetime '{value}': {err}")

    event: Dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }
    if description:
        event["description"] = description
    if location:
        event["location"] = location
    return event


def load_credentials(client_secrets_path: Path, token_path: Path) -> Credentials:
    creds: Optional[Credentials] = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GOOGLE_SCOPES)
    # Refresh or start a new flow if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_path), GOOGLE_SCOPES
            )
            # Use console-based flow to keep this non-interactive friendly
            creds = flow.run_console()
        token_path.write_text(creds.to_json())
    return creds


def upsert_event(
    client_secrets: str,
    token_file: str,
    calendar_id: str,
    summary: str,
    start: str,
    end: str,
    timezone: str,
    description: Optional[str],
    location: Optional[str],
    event_id: Optional[str],
) -> Dict[str, Any]:
    creds = load_credentials(Path(client_secrets), Path(token_file))
    service = build("calendar", "v3", credentials=creds)

    payload = build_event_payload(
        summary=summary,
        start=start,
        end=end,
        timezone=timezone,
        description=description,
        location=location,
    )

    if event_id:
        result = (
            service.events()
            .patch(calendarId=calendar_id, eventId=event_id, body=payload)
            .execute()
        )
    else:
        result = service.events().insert(calendarId=calendar_id, body=payload).execute()

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update a Google Calendar event (delegated OAuth)"
    )
    parser.add_argument(
        "--client-secrets",
        required=True,
        help="Path to OAuth client secrets JSON downloaded from Google Cloud Console",
    )
    parser.add_argument(
        "--token-file",
        default=str(Path.home() / ".config" / "nillebCal" / "google_token.json"),
        help="Where to cache user tokens (will be created if missing)",
    )
    parser.add_argument(
        "--calendar-id", default="primary", help="Calendar ID (default primary)"
    )

    # Unified flags
    parser.add_argument("--title", help="Event title/summary")
    parser.add_argument("--description", help="Optional description")
    parser.add_argument(
        "--start", required=True, help="Local start datetime, e.g. 2025-10-17T09:00:00"
    )
    parser.add_argument(
        "--end", required=True, help="Local end datetime, e.g. 2025-10-17T10:00:00"
    )
    parser.add_argument(
        "--timezone", default="UTC", help="Timezone, e.g. Europe/Rome or UTC"
    )
    parser.add_argument("--location", help="Optional location")
    parser.add_argument(
        "--event-id", help="If provided, update the given event ID; otherwise create"
    )

    # Backward-compatible alias
    parser.add_argument("--summary", help="Alias of --title")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Ensure token directory exists
    token_path = Path(args.token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve unified + alias args
    title = args.title or args.summary
    if not title:
        raise SystemExit("--title is required (or provide --summary)")

    event = upsert_event(
        client_secrets=args.client_secrets,
        token_file=args.token_file,
        calendar_id=args.calendar_id,
        summary=title,
        start=args.start,
        end=args.end,
        timezone=args.timezone,
        description=args.description,
        location=args.location,
        event_id=args.event_id,
    )

    event_id = event.get("id", "<unknown>")
    html_link = event.get("htmlLink")
    print(f"OK event_id={event_id}")
    if html_link:
        print(f"htmlLink={html_link}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
