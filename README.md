# nillebCal

Lightweight wrappers to upsert (create/update) events on Microsoft 365 (Graph) and Google Calendar using delegated user permissions.

## Prerequisites

- Python 3.11+
- uv for dependency management
- `uv sync`

## Common CLI interface

Both wrappers expose a common set of arguments (credentials differ per provider):

- `--title` (required): Event title
- `--description`: Optional description/body
- `--start` (required): Local start datetime, e.g. `2025-10-17T09:00:00`
- `--end` (required): Local end datetime, e.g. `2025-10-17T10:00:00`
- `--timezone`: IANA timezone (e.g. `Europe/Rome` or `UTC`)
- `--location`: Optional location string
- `--event-id`: If provided, the script updates an existing event; otherwise creates
- `--calendar-id`: Target calendar; defaults to primary calendar

Back-compat aliases:
- Microsoft Graph: `--subject` (alias for `--title`), `--body` (alias for `--description`)
- Google: `--summary` (alias for `--title`)

## Microsoft 365 (Graph)

### App registration (Terraform)

Provision the app with delegated scopes and domain consent:

```bash
cd infra
terraform init
terraform apply -auto-approve -var="display_name=nillebCal-Graph-App"
```

Outputs will include `application_id` (client id) and `tenant_id`.

### Usage

```bash
uv run graph_calendar.py \
  --tenant-id <TENANT_ID_OR_DOMAIN> \
  --client-id <APP_CLIENT_ID> \
  --title "Team sync" \
  --start 2025-10-17T09:00:00 \
  --end 2025-10-17T09:30:00 \
  --timezone Europe/Rome \
  --location "Room 1"

# Update existing event by id on primary calendar
uv run graph_calendar.py \
  --tenant-id <TENANT_ID_OR_DOMAIN> \
  --client-id <APP_CLIENT_ID> \
  --title "Team sync (updated)" \
  --start 2025-10-17T09:00:00 \
  --end 2025-10-17T09:45:00 \
  --timezone Europe/Rome \
  --event-id <EVENT_ID>

# Create on a specific calendar by id
uv run graph_calendar.py \
  --tenant-id <TENANT_ID_OR_DOMAIN> \
  --client-id <APP_CLIENT_ID> \
  --title "Project kickoff" \
  --start 2025-10-18T10:00:00 \
  --end 2025-10-18T11:00:00 \
  --timezone UTC \
  --calendar-id <CALENDAR_ID>
```

Notes:
- Uses Device Code flow, delegated to the signed-in user; operates on `/me` calendar.
- `--calendar-id` supports posting to `/me/calendars/{id}/events`; default is the user's primary calendar (`/me/calendar/events`).

## Google Calendar

### Enable API (Terraform) and create OAuth client

```bash
cd infra_google
terraform init
terraform apply -auto-approve -var="project_id=<YOUR_PROJECT_ID>"

bash infra_google/create_oauth_client.sh <YOUR_PROJECT_ID> nillebCal-Desktop
```

If the script can't create the client (policy-dependent), create a Desktop OAuth client in the Cloud Console and download the `client_secret.json`.

### Usage

```bash
uv run google_calendar.py \
  --client-secrets /absolute/path/client_secret.json \
  --calendar-id primary \
  --title "Team sync" \
  --start 2025-10-17T09:00:00 \
  --end 2025-10-17T09:30:00 \
  --timezone Europe/Rome \
  --location "Room 1"

# Update existing event
uv run google_calendar.py \
  --client-secrets /absolute/path/client_secret.json \
  --calendar-id primary \
  --title "Team sync (updated)" \
  --start 2025-10-17T09:00:00 \
  --end 2025-10-17T09:45:00 \
  --timezone Europe/Rome \
  --event-id <EVENT_ID>
```

Notes:
- Stores user tokens at `~/.config/nillebCal/google_token.json` by default; use `--token-file` to override.
- Uses Installed App OAuth (console) and operates only on the authenticated user's calendar.


