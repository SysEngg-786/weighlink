# Architecture

WeighLink connects an industrial weighing instrument to your data and workflow
systems. Out of the box it speaks the **A&D standard ASCII protocol** — the
format used by A&D industrial scales and balances — validated against A&D's own
RsWeight 6.04 software. It reads each weighment over the serial line, turns it
into a compliant record (tolerance-checked, audit-logged, tamper-evident), and
forwards stable weighments to your logging and automation layer over HTTP.

Because the protocol is defined in configuration rather than hard-coded,
WeighLink is not limited to A&D: supporting another instrument (Mettler, Ohaus,
Sartorius) is a configuration entry, not a code change. A&D is the proven
reference implementation; the architecture is protocol-agnostic by design. This
document describes how the pieces fit and how a reading flows through the system.

## Design goals

The system is built around a single idea: **the parts that change often
(instrument protocols, tolerance rules, endpoints) are configuration, and the
parts that stay stable (the pipeline itself) are code.** A&D support ships
working and validated; adding a different scale protocol, a new product
tolerance, or a new webhook target is a config edit, not a code change. Each
stage of the pipeline is an independent module with one responsibility, so a
change to one stage does not ripple into the others.

## Module map

| Module | Responsibility |
|---|---|
| `simulator/scale_simulator.py` | Config-driven fake A&D scale for development — streams realistic ASCII packets at 10 Hz with settling dynamics, tare, and query response. Lets the whole pipeline run with no physical hardware. |
| `listener/protocol_parser.py` | Turns a raw ASCII serial line into a structured reading dict. Field positions and header values come from a protocol JSON, so it is stateless and instrument-agnostic. |
| `listener/serial_reader.py` | Owns the serial port. Opens it with config-driven settings, reads continuously on a background thread, parses each line via `ProtocolParser`, and dispatches parsed readings to a registered callback. |
| `compliance/weighment.py` | `WeighmentRecord` — the canonical data object. Every field is present from creation (explicit defaults, never null), so downstream stages never null-check. |
| `compliance/tolerance_engine.py` | Evaluates a record's weight against a product's configured min/max and stamps `PASS` / `FAIL` / `NO_RULE` onto the record. |
| `compliance/audit_logger.py` | Assigns the sequential `record_id` and `prev_hash`, and appends the record to a tamper-evident local log (see `compliance_model.md`). |
| `integration/webhook_pusher.py` | One output adapter. POSTs a record to a configured HTTP endpoint with retry/backoff and an auth header. Fails loud, never silently drops. |
| `controller/fill_controller_gui.py` | The orchestrator and UI. Wires the pipeline together, runs a real-time fill-control readout, and owns nothing but the GUI and fill logic. |

Configuration lives under `config/`: `app_config.json` (ports, device, active
protocol, tolerance profile, webhook), `config/protocols/*.json` (per-instrument
packet format and serial settings), and `config/tolerances/*.json` (per-product
min/max).

## Data flow

The controller registers a callback on the serial reader, then connects. From
that point every parsed reading travels the same path:

```
serial line (bytes)
  → ProtocolParser.parse()            raw ASCII → reading dict
  → SerialReader dispatches callback  (on a background thread)
  → WeighmentRecord.from_reading()    reading dict → canonical record
  → ToleranceEngine.evaluate()        stamps PASS / FAIL / NO_RULE
  → AuditLogger.log()                 assigns record_id + prev_hash, appends to log
  → WebhookPusher.push()              POST to HTTP endpoint  (stable readings only)
  → UI update                         dispatched to the main GUI thread
```

Two behaviours in this flow are deliberate and worth stating precisely, because
they define the division between the local record and the downstream feed:

1. **Every reading is audit-logged; only stable readings are pushed.** The local
   audit trail is complete — it records every reading for full traceability. The
   webhook fires only when `is_stable` is true, so the downstream automation
   layer receives settled weighments, not the noise of a scale still settling.

2. **Compliance is decided at the source, not downstream.** The tolerance result
   (`PASS` / `FAIL` / `NO_RULE`) is computed by `ToleranceEngine` before the
   record ever leaves the machine. Anything downstream (the webhook receiver, an
   alerting workflow) only reacts to that decision — it does not re-derive it.
   The system of record owns the compliance call.

## Threading

`SerialReader` runs its read loop on a background daemon thread so the UI stays
responsive. The pipeline callback (`_on_reading`) therefore executes off the main
thread; compliance processing happens there, and only the final UI render is
dispatched back to the main GUI thread. This keeps a fast (10 Hz) instrument
stream from blocking the interface.

## Extensibility seams

- **New instrument protocol** → add a `config/protocols/<name>.json` and point
  `app_config.json`'s `serial.protocol` at it. No parser code changes.
- **New product tolerance** → add a `config/tolerances/<name>.json` and set
  `compliance.tolerance_profile`. No engine changes.
- **New output target** (MQTT, direct ERP) → implement the same
  `push(record) -> bool` interface as `WebhookPusher`. The pipeline calls one
  adapter; adding another does not touch the existing one.

## Running the system

For development with no hardware: run the simulator against one end of a virtual
serial pair and the controller against the other (ports set in `app_config.json`
as `simulator_port` / `listener_port`). For real hardware: point `listener_port`
at the instrument's COM port; the rest of the pipeline is unchanged. See
`protocol_guide.md` for protocol config detail and `n8n_setup_guide.md` for the
downstream workflow layer.
