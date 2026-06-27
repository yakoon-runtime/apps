# y5napp-crm — Mini CRM

A minimal but functional CRM running on the Yakoon runtime.

Purpose: demonstrate how processes, human decisions and AI-assisted steps work together in a runtime where sessions outlive clients and flows survive disconnects.

## Scope

This is not a feature-rich CRM. It is a **provable prototype** that real business data — contacts, addresses, notes — can be managed through long-running, client-independent flows.

## Features

### Phase 1 — Core (must work)

- **Contact management** — add, list, search, edit, delete contacts
- **Contact fields** — name, company, email, phone, address (street, zip, city, country)
- **Persistent storage** — all data stored via EntityStore (survives runtime restart)
- **Human-in-the-loop** — create flow pauses for human review before persisting new contacts
- **Session survival** — start a contact creation flow, close the client, re-attach later: flow is still there

### Phase 2 — AI-assisted (illustrates the model)

- **AI-suggested enrichment** — after entering a company name, AI proposes address data from the name
- **Duplicate detection** — AI checks existing contacts before creating a new one
- **AI-generated notes** — from conversation snippets or meeting notes stored as plain text

### Phase 3 — Process-oriented (demonstrates the runtime)

- **Sequential flows** — "create contact → create opportunity → log interaction" as a guided process
- **Multi-client observation** — one user fills a form in Texture, another watches the projection in Web
- **Role-based projections** — sales sees a different view than admin

## Non-goals

- No calendar, no tasks, no workflow engine, no email integration
- No authentication system (reuses Yakoon's built-in permissions)
- No web UI beyond the existing yakoon-web client
- No import/export

## Data Model

```
Contact {
  id: string
  name: string
  company: string
  email: string
  phone: string
  address: {
    street: string
    zip: string
    city: string
    country: string
  }
  notes: string
  created_at: datetime
  updated_at: datetime
}
```

## How to run

```bash
pip install -e apps/y5napp-crm
```

See `docs/GETTING_STARTED.md` for runtime setup.
