# xlsx-mapper

`xlsx-mapper` is a Dockerized collaborative web application for schema-driven Excel editing.

Users can:
- Upload a base `.xlsx` workbook
- Define mapping schema rules (`sheet`, `range`, `type`)
- Reuse that workbook+schema as a **template**
- Create multiple **sessions** from the same template
- Share sessions by link for public editors (no account)
- Invite account collaborators to manage templates/sessions
- Edit values through a generated web form
- Validate types and write values back into the Excel file
- Download the updated workbook

## Features

- Account-based auth (email/password)
- Template management (base workbook + schema JSON)
- Session instances created from templates (reusable workflow)
- Public share token editing (values only)
- Account collaborator sharing for template/session management
- Session auto-expiry after 24h of inactivity
- Real-time lock API (WebSocket lock/unlock/heartbeat)
- Server-side type validation (`number`, `string`, `boolean`, `date`)
- Persistent storage for template and session files

## Project Structure

```text
xlsx-mapper/
  backend/
    app/
      config.py
      database.py
      excel_service.py
      locks.py
      main.py
      models.py
      permissions.py
      schemas.py
      security.py
      routers/
        auth.py
        templates.py
        sessions.py
        locks.py
    requirements.txt
  frontend/
    index.html
    app.js
    styles.css
  .gitignore
  Dockerfile
  docker-compose.yml
```

## Schema Format

Each mapping rule includes:
- `sheet`: worksheet name
- `range`: Excel range (e.g. `A1:A10`)
- `type`: `number | string | boolean | date`
- `label` (optional): field label for generated UI

Example:
```json
[
  {"sheet":"Sheet1","range":"A1:A10","type":"number","label":"Amount"},
  {"sheet":"Sheet1","range":"B1:B10","type":"string","label":"Description"},
  {"sheet":"Sheet1","range":"C1:C10","type":"boolean","label":"Approved"},
  {"sheet":"Sheet1","range":"D1:D10","type":"date","label":"Date"}
]
```

## REST API Overview

### Auth
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

### Templates
- `POST /api/templates` (multipart: `name`, `schema_json`, `file`)
- `GET /api/templates`
- `GET /api/templates/{template_id}`
- `PUT /api/templates/{template_id}/schema`
- `POST /api/templates/{template_id}/collaborators`

### Sessions
- `POST /api/templates/{template_id}/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `GET /api/sessions/{session_id}/form`
- `POST /api/sessions/{session_id}/update`
- `GET /api/sessions/{session_id}/download`
- `POST /api/sessions/{session_id}/collaborators`

### Public Share
- `GET /api/public/sessions/{share_token}`
- `POST /api/public/sessions/{share_token}/update`

### Lock WebSockets
- Authenticated: `ws://host/ws/locks/sessions/{session_id}?token=<jwt>`
- Public: `ws://host/ws/locks/public/{share_token}?name=<guest>`

## Run with Docker

### Prerequisites
- Docker
- Docker Compose

### Start

```bash
docker compose up --build
```

Open:
- App UI: [http://localhost:8080](http://localhost:8080)
- Health: [http://localhost:8080/health](http://localhost:8080/health)

## Typical Workflow

1. Register + login
2. Upload template workbook with schema JSON
3. Create one or more sessions from the template
4. Share session link for public editors or add account collaborators
5. Open session editor and update mapped fields
6. Save changes and download updated `.xlsx`

## Notes

- Public link users can edit mapped values only (no schema updates).
- Session content persists in Docker volume and auto-expires after 24h inactivity.
- Expired sessions return `410 Gone`.
