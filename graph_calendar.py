import argparse
import sys
from datetime import datetime
from typing import Optional, Dict, Any

import requests
import msal
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


GRAPH_SCOPES = [
    "Calendars.ReadWrite",
    "offline_access",
    "User.Read",
]


def build_event_payload(
    subject: str,
    start: str,
    end: str,
    timezone: str,
    body: Optional[str] = None,
    location: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a Microsoft Graph event payload.

    Args:
        subject: Event subject.
        start: ISO 8601 local datetime string, e.g. 2025-10-17T09:00:00.
        end: ISO 8601 local datetime string.
        timezone: IANA/Windows timezone name, e.g. "Europe/Rome" or "UTC".
        body: Optional body content (HTML allowed, will be treated as text).
        location: Optional location display name.
    """

    # Validate inputs early to fail fast with clear messages
    for label, value in (("start", start), ("end", end)):
        try:
            # Only validate format; Graph accepts strings with timezone separate
            datetime.fromisoformat(value)
        except ValueError as err:
            raise SystemExit(f"Invalid {label} datetime '{value}': {err}")

    event: Dict[str, Any] = {
        "subject": subject,
        "start": {"dateTime": start, "timeZone": timezone},
        "end": {"dateTime": end, "timeZone": timezone},
    }

    if body:
        event["body"] = {"contentType": "text", "content": body}
    if location:
        event["location"] = {"displayName": location}

    return event


def acquire_token_device_code(tenant_id: str, client_id: str) -> Dict[str, Any]:
    """Acquire an access token using Device Code flow.

    Returns the token result payload from MSAL.
    """

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id=client_id, authority=authority)

    flow = app.initiate_device_flow(
        scopes=[f"https://graph.microsoft.com/{s}" for s in GRAPH_SCOPES]
    )
    if "user_code" not in flow:
        raise SystemExit(f"Failed to create device flow. Details: {flow}")

    print(flow["message"])  # Guidance for the user to authenticate
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        error = result.get("error")
        desc = result.get("error_description")
        raise SystemExit(f"Failed to acquire token: {error}: {desc}")

    return result


def acquire_token_auth_code(
    tenant_id: str, client_id: str, client_secret: str, redirect_uri: str
) -> Dict[str, Any]:
    """Acquire an access token using Authorization Code flow for confidential clients.

    Opens the system browser and listens on the redirect URI to capture the auth code.
    """

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )

    scopes = [f"https://graph.microsoft.com/{s}" for s in GRAPH_SCOPES]
    auth_url = app.get_authorization_request_url(
        scopes=scopes, redirect_uri=redirect_uri
    )

    # Minimal local server to capture the authorization code
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8400
    code_holder: Dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # type: ignore[override]
            query = parse_qs(urlparse(self.path).query)
            if "code" in query:
                code_holder["code"] = query["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(
                    b"You may close this window and return to the application."
                )
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, format, *args):  # noqa: A003 - silence server logs
            return

    httpd = HTTPServer((host, port), Handler)
    print(f"Opening browser for consent: {auth_url}")
    try:
        webbrowser.open(auth_url)
    except Exception:
        print("Please open the URL above manually in a browser.")

    # Serve a single request to capture the code
    httpd.handle_request()
    httpd.server_close()

    if "code" not in code_holder:
        raise SystemExit("Authorization code not received")

    result = app.acquire_token_by_authorization_code(
        code_holder["code"], scopes=scopes, redirect_uri=redirect_uri
    )
    if "access_token" not in result:
        error = result.get("error")
        desc = result.get("error_description")
        raise SystemExit(f"Failed to acquire token via auth code: {error}: {desc}")
    return result


def graph_request(
    method: str, path: str, token: str, json: Optional[Dict[str, Any]] = None
) -> requests.Response:
    url = f"https://graph.microsoft.com/v1.0{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.request(method=method, url=url, headers=headers, json=json)
    return resp


def upsert_event(
    tenant_id: str,
    client_id: str,
    subject: str,
    start: str,
    end: str,
    timezone: str,
    body: Optional[str],
    location: Optional[str],
    event_id: Optional[str],
    calendar_id: Optional[str],
    client_secret: Optional[str],
    redirect_uri: Optional[str],
) -> Dict[str, Any]:
    if client_secret and redirect_uri:
        token_result = acquire_token_auth_code(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
    else:
        token_result = acquire_token_device_code(
            tenant_id=tenant_id, client_id=client_id
        )
    access_token = token_result["access_token"]

    payload = build_event_payload(
        subject=subject,
        start=start,
        end=end,
        timezone=timezone,
        body=body,
        location=location,
    )

    if event_id:
        # Update existing event
        resp = graph_request(
            "PATCH", f"/me/events/{event_id}", token=access_token, json=payload
        )
    else:
        # Create new event on default calendar or a specific calendar if provided
        if calendar_id and calendar_id != "calendar":
            path = f"/me/calendars/{calendar_id}/events"
        else:
            path = "/me/calendar/events"
        resp = graph_request("POST", path, token=access_token, json=payload)

    if resp.status_code >= 300:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise SystemExit(f"Graph API error {resp.status_code}: {detail}")

    return resp.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update a Microsoft Graph calendar event (delegated)"
    )
    parser.add_argument(
        "--tenant-id", required=True, help="Azure AD tenant ID (GUID) or domain name"
    )
    parser.add_argument(
        "--client-id", required=True, help="Azure AD application (client) ID"
    )
    # Unified flags
    parser.add_argument("--title", help="Event title/subject")
    parser.add_argument("--description", help="Optional description/body text")
    parser.add_argument(
        "--start", required=True, help="Local start datetime, e.g. 2025-10-17T09:00:00"
    )
    parser.add_argument(
        "--end", required=True, help="Local end datetime, e.g. 2025-10-17T10:00:00"
    )
    parser.add_argument(
        "--timezone", default="UTC", help="Timezone, e.g. Europe/Rome or UTC"
    )
    parser.add_argument("--location", help="Optional location display name")
    parser.add_argument(
        "--event-id", help="If provided, update the given event ID; otherwise create"
    )
    parser.add_argument(
        "--calendar-id", default="calendar", help="Calendar ID (default user's primary)"
    )

    # Optional confidential client auth (use these instead of device code)
    parser.add_argument(
        "--client-secret",
        help="Use confidential client auth code flow with this secret",
    )
    parser.add_argument(
        "--redirect-uri",
        help="Redirect URI for auth code flow (e.g. http://localhost:8400/callback)",
    )

    # Backward-compatible aliases
    parser.add_argument("--subject", help="Alias of --title")
    parser.add_argument("--body", help="Alias of --description")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # Resolve unified + alias args
    title = args.title or args.subject
    if not title:
        raise SystemExit("--title is required (or provide --subject)")
    description = args.description or args.body

    event = upsert_event(
        tenant_id=args.tenant_id,
        client_id=args.client_id,
        subject=title,
        start=args.start,
        end=args.end,
        timezone=args.timezone,
        body=description,
        location=args.location,
        event_id=args.event_id,
        calendar_id=args.calendar_id,
        client_secret=args.client_secret,
        redirect_uri=args.redirect_uri,
    )

    # Print minimal output so this can be scripted easily
    event_id = event.get("id", "<unknown>")
    web_link = event.get("webLink")
    print(f"OK event_id={event_id}")
    if web_link:
        print(f"webLink={web_link}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
