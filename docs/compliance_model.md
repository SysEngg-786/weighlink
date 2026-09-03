# Compliance Model

WeighLink's compliance layer produces a traceable, tamper-evident record of
every weighment. This document describes what each record contains, how the
audit trail is chained, how tolerance is evaluated, and — importantly — the
exact boundary of what the tamper-evidence mechanism does and does not prove.

## What a compliant record contains

Every weighment becomes a `WeighmentRecord` carrying a complete set of fields
from the moment it is created — no partial records, no nulls to guard against:

- **weight, unit** — the measured value and its unit.
- **header, is_stable** — the instrument's stability indicator and derived flag.
- **device_id** — which instrument produced the reading.
- **timestamp** — ISO 8601 UTC, set at record creation.
- **operator_id, lot_ref** — who ran it and which batch (manual entry in v1;
  a seam exists for badge/barcode/ERP sourcing later).
- **tolerance_result, tolerance_min, tolerance_max** — the compliance verdict
  and the bounds it was judged against.
- **record_id, prev_hash** — the audit-chain position and the link to the
  previous record.

This gives each weighment full traceability: what was weighed, when, on which
device, by whom, for which lot, whether it passed, and where it sits in the
tamper-evident chain.

## Tolerance evaluation

The tolerance engine (`compliance/tolerance_engine.py`) loads a per-product
profile from `config/tolerances/<profile>.json` and stamps each record. The
rules are deliberately simple and explicit:

- **Unstable readings are never judged.** If the scale is still settling
  (`is_stable` false), the result is `NO_RULE` — you do not fail a weighment
  that had not settled.
- **No profile loaded → `NO_RULE`.** Tolerance checking is optional; a
  deployment without a profile simply records weighments without a pass/fail
  verdict. This is a valid mode, not an error.
- **Within `[min, max]` inclusive → `PASS`; outside → `FAIL`.** The bounds that
  were applied are written onto the record (`tolerance_min` / `tolerance_max`),
  so the record is self-describing — a reader sees both the value and the range
  it was judged against.

Crucially, this verdict is computed **at the source**, on the machine at the
instrument, before the record is logged or transmitted. Everything downstream
(the storage layer, the alerting workflow) reacts to this verdict; nothing
downstream re-derives it. The system of record owns the compliance decision.

## The audit trail

The audit logger (`compliance/audit_logger.py`) writes an **append-only** JSONL
file — one JSON object per line, no edits, no deletes, no overwrites. Each run
opens a new session file named with a UTC timestamp
(`audit_YYYYMMDD_HHMMSS.jsonl`), and `record_id` counts from 1 within that
session.

### The hash chain

Each record stores the SHA-256 hash of the record before it, in its `prev_hash`
field. The first record links to a fixed `"GENESIS"` marker. So the log forms a
chain:

```
record 1 : prev_hash = GENESIS
record 2 : prev_hash = SHA256(record 1)
record 3 : prev_hash = SHA256(record 2)
...
```

`AuditLogger.verify_chain()` re-walks a log file, recomputing each record's hash
and checking that the next record's `prev_hash` matches. If any record was
altered, removed, or inserted, the recomputed hash stops matching the stored
`prev_hash` at that point, and verification reports exactly which record broke
the chain. That is the tamper-**evidence**: casual edits to a stored log do not
go unnoticed.

### Boundary of the claim (read this)

The hash chain is **tamper-evidence, not tamper-proofing** — and the difference
matters, so it is stated plainly rather than glossed:

- It reliably detects **accidental or casual** modification: hand-editing a
  value, deleting a line, truncating the file. The chain breaks and
  `verify_chain()` flags it.
- It does **not** defend against a **determined forger** with write access to
  the file. Because each link is a plain SHA-256 with no secret key and no
  external anchor, someone who edits a record can recompute that record's hash
  and every subsequent `prev_hash`, producing a chain that re-verifies clean.

Making the chain resistant to deliberate forgery would require signing each
record with a key the writer does not control, or anchoring hashes to an
external append-only service — a designed-for seam, not part of v1. The v1
mechanism is exactly what the code describes: lightweight tamper evidence,
sufficient to demonstrate the compliance architecture and to catch
non-adversarial corruption, not a cryptographic guarantee against a motivated
insider.

This boundary is stated deliberately. A compliance record whose limits are
honestly declared is more trustworthy than one that implies more assurance than
it delivers.

## Relationship to the stored copy

The local audit log is the complete, authoritative record — every reading,
stable or not, is logged for full traceability. The Postgres store downstream
receives only the **stable** weighments that were pushed over the webhook, and
serves the querying, alerting, and reporting layer. The two are complementary:
the local JSONL is the tamper-evident system of record; the database is the
queryable operational copy. See `architecture.md` for the full data flow and
`n8n_setup_guide.md` for the storage and workflow layer.

## Regulatory boundary

WeighLink demonstrates the *data architecture* for traceable, auditable weight
records in regulated settings. It does not claim regulatory certification
(FDA 21 CFR Part 11, FSMA, BRCGS, ISO 22000). Those are deployment-specific
validations tied to a facility's quality management system, its procedures, and
its full technology stack — not properties a bridge component can assert on its
own.
