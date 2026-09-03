# n8n Setup Guide

This guide describes the workflow-and-storage layer that receives weighments
from the WeighLink edge pipeline: what it is made of, how the pieces are
arranged, and the design decisions behind them. It is **not** an n8n tutorial —
the workflows use only generic n8n nodes (Webhook, Postgres, IF, HTTP Request,
Schedule Trigger), and their mechanics are covered by n8n's own documentation.
What is documented here is the *design* you would reproduce, not which buttons
to click.

All secrets below are shown as placeholders (`<LIKE_THIS>`). Never commit real
tokens, webhook URLs, encryption keys, or passwords to a repository.

## The stack

The layer runs as a self-hosted, containerized deployment:

- **n8n** (queue mode: a main instance plus a worker) — the workflow engine.
- **PostgreSQL** — weighment storage and aggregation.
- **Redis** — the queue broker n8n uses in queue mode.
- **Traefik** — TLS termination and routing, so the webhook is reachable over
  HTTPS.

WeighLink does not require you to build this stack from scratch; it was
integrated into an existing containerized n8n deployment. The WeighLink-specific
additions are: a dedicated Postgres database, the weighment schema, and three
workflows.

## Database: isolation by design

WeighLink stores weighments in a **dedicated Postgres database, separate from
n8n's own operational database**, owned by a **dedicated role** that cannot
touch n8n's tables. This is deliberate:

- **Separation of concerns** — weighment data never mixes with n8n's internal
  schema; a change or problem on one side cannot ripple into the other.
- **Credential isolation** — the application logs in with a role scoped to its
  own database only.

Because n8n's own schema migrations run inside n8n's database, they cannot see
or alter the WeighLink database — the two are isolated Postgres namespaces on
the same server, so upgrading n8n is safe for the weighment data.

### Schema

The weighment table stores the record fields the edge pipeline sends, plus two
database-owned columns:

- The **13 record fields** from the payload (weight, unit, header, is_stable,
  device_id, the timestamp, operator_id, lot_ref, tolerance_result,
  tolerance_min, tolerance_max, record_id, prev_hash).
- **A database-owned primary key** (`BIGSERIAL`) — row identity assigned by
  Postgres, kept distinct from the application's own `record_id`. Two ids with
  two owners: the app owns audit-chain position, the database owns row identity.
- **A database-owned ingest timestamp** (`DEFAULT now()`) — when the row landed,
  kept distinct from the weighing timestamp (when the weighment happened). The
  gap between the two makes delivery latency visible.

The weighing timestamp is stored as a real timestamp type (not text) so the
daily summary can filter and aggregate by operating day. The table is indexed on
the weighing timestamp, the tolerance result, and the record id — each index
earns its place against one of the workflows below, not speculatively.

## The three workflows

### 1. Receive + Store

The entry point. A **Webhook** node receives the authenticated POST from the
edge pipeline; a small transform lifts the payload to the fields the insert
expects; a **Postgres** node inserts the row.

- **Authenticated.** The webhook requires a shared-secret header
  (`X-Weighlink-Token: <TOKEN>`). Requests without it are rejected. The edge
  pipeline sends the same header; the two share one secret. The compliance
  write-endpoint is not open to the internet.
- **Responds immediately.** The webhook acknowledges as soon as it receives, so
  the edge pusher is not held while the database write completes.
- **Stores every weighment it receives** — the store path does not branch on
  pass/fail; alerting does.

### 2. Tolerance Alert

Branches off the same flow after the insert. An **IF** node checks the record's
`tolerance_result`; on `FAIL` it triggers an **HTTP Request** node that POSTs a
formatted message to a Slack incoming webhook. On `PASS` (or `NO_RULE`) nothing
is sent.

- The alert is **reactive, not authoritative** — it acts on the verdict the edge
  pipeline already stamped; it does not re-evaluate tolerance.
- The Slack message shows the out-of-range value against the allowed range, with
  device, operator, lot, and record id — a compliance alert readable at a
  glance.
- The Slack endpoint is an incoming webhook URL (`<SLACK_WEBHOOK_URL>`), bound to
  the alert channel and kept out of the repo.

### 3. Daily Summary

Time-triggered, not webhook-triggered. A **Schedule Trigger** fires once a day; a
**Postgres** node runs an aggregate query over the day's rows (total, pass/fail
counts, weight min/max/average); an **HTTP Request** node posts the digest to the
same Slack channel.

- **Operating-day boundary.** The query anchors "today" to the operating
  timezone, not the server's UTC clock, so a weighment counts on the day it was
  weighed locally. (Set n8n's instance timezone to the operating timezone so the
  schedule also fires at the intended local hour.)
- No inbound endpoint exists for this workflow — it is self-triggered on the
  clock, so there is nothing to authenticate.

## Configuration and secrets

The edge pipeline points at the workflow layer through its config
(`config/app_config.json`, gitignored — see `config/app_config.example.json`
for the shape). The values it needs:

- `webhook_url` — the **production** webhook URL
  (`https://<YOUR_N8N_HOST>/webhook/<PATH>`), not the test URL.
- `webhook_auth_token` — the shared secret matching the webhook's header-auth
  credential.

n8n-side secrets (never in the repo):

- The **encryption key** — in queue mode, the main and worker instances must
  share the *identical* key, or credentials saved by one cannot be decrypted by
  the other. Pin it in the deployment config so it is stable across restarts.
- The **Slack webhook URL** and **Postgres credentials** — stored in n8n's
  credential store and referenced by the nodes, not written into the repo.

## Activation

The workflows run on demand while building (manual execution) and autonomously
once **activated**. Activation is what turns the production webhook live and puts
the schedule on the clock. Before activating a compliance endpoint: confirm the
webhook auth is in place, point the edge config at the production URL, and start
from a clean table.

For the exact operational recipe of a specific deployment — container names,
volume layout, backup commands, the encryption-key reconciliation procedure —
keep a private operations document outside the public repository. That detail is
deployment-specific and includes information that should not be published.
