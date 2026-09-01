# WeighLink

**Protocol-agnostic serial instrument bridge — RS232/RS485 to compliance logging and workflow automation via webhook/n8n.**

---

## What This Is

WeighLink sits between an industrial serial instrument (weighing scales, balances, load cells) and your business systems. It reads weight data over RS232/RS485, enforces configurable tolerances, writes an immutable audit trail, and pushes compliant records to a workflow engine (n8n) via webhook for alerting, storage, and reporting.

It replaces the gap between free keyboard-emulators (232key, WinCT) and locked-in enterprise systems (Yaveon, V5) — open, lightweight, vendor-neutral.

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Protocol    │───→│ Compliance  │───→│ Integration │───→│  Workflow    │
│  Layer       │    │ Layer       │    │ Layer       │    │  Engine      │
│  (listener)  │    │ (validator) │    │ (pusher)    │    │  (n8n/VPS)  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
  RS232/RS485        Tolerance          Webhook POST       Receive & Store
  A&D protocol       check              Retry w/backoff    Tolerance Alert
  Config-driven      Audit log          Configurable       Daily Summary
  parser             Hash chain         endpoint           Shift Report
```

**Each layer talks to the next through a defined interface. Each interface is a seam where future extensions attach without touching today's build.**

## Reference Implementation

The v1 reference implementation uses an **A&D industrial scale** as the source instrument. The A&D standard ASCII protocol (17-character format, 9600 baud, 7-E-1) is the first protocol configuration. Interoperability has been validated against A&D's own RsWeight software.

The architecture is protocol-agnostic by design — adding support for Mettler Toledo (MT-SICS), Ohaus, Sartorius (SBI), or any ASCII-output serial instrument is a JSON config entry, not a code change.

## Key Capabilities (v1)

- **Protocol-agnostic serial listener** — config-driven parser, A&D reference implementation
- **Scale simulator** — physically realistic (settling dynamics, vibration, tare), interop-validated against A&D RsWeight 6.04
- **Fill controller GUI** — proportional closed-loop motor control (bulk → micro-trickle → target kill)
- **Compliance logging** — timestamped weighment records with operator ID, lot/batch reference, tolerance result (PASS/FAIL), append-only JSONL with SHA-256 hash chain for tamper evidence
- **Tolerance engine** — configurable min/max per product, automatic flagging of out-of-spec readings
- **Webhook integration** — pushes compliant records to n8n (or any webhook endpoint) with retry and backoff
- **n8n workflow templates** — importable JSON workflows for receive/store, tolerance alerting, and daily shift summaries

## Compliance Positioning

WeighLink demonstrates the data architecture required for traceable, auditable weight records in regulated environments (pharmaceutical, food & beverage, logistics). Every weighment carries: timestamp (ISO 8601 UTC), device ID, operator ID, lot/batch reference, tolerance result, and a hash-chained audit trail.

**Note:** This is an architectural demonstration and reference implementation. It does not claim regulatory certification (FDA 21 CFR Part 11, FSMA, BRCGS, ISO 22000). Regulatory validation is a deployment-specific activity that depends on the target facility's quality management system.

## Interoperability Proof

A&D RsWeight 6.04 receiving and correctly parsing data from the WeighLink scale simulator over virtual COM ports (com0com):

![A&D RsWeight Interoperability](docs/images/rsweight_interop_proof.png)

## Built With

- **Python 3.x** — core runtime
- **pyserial** — RS232/RS485 communication
- **n8n** (self-hosted) — workflow automation engine
- **com0com** — virtual COM port driver (development/demo)

## Designed-For-Tomorrow Seams (Not Built in v1)

- RS485 multi-drop bus support (device_id field present, bus not yet implemented)
- Protocol configs beyond A&D (Mettler Toledo MT-SICS, Ohaus, Sartorius SBI)
- Operator authentication beyond manual text entry (badge reader, barcode, LDAP)
- ERP tolerance lookup (currently local config file)
- MQTT and direct ERP output adapters (currently webhook only)
- Offline buffer sync (local audit log is the buffer — sync not yet automated)
- RAG query interface over weight history (DB schema supports it)
- ERP sync workflow (Odoo, SAP, Business Central — n8n has native nodes)

Each seam has a named interface in the architecture. None requires rework to add — only new code at a defined attachment point.

## Repository Structure

```
weighlink/
├── config/                  Configuration (ports, protocols, tolerances)
│   ├── app_config.json
│   ├── protocols/
│   │   └── a_and_d.json
│   └── tolerances/
│       └── demo_product.json
├── simulator/               A&D scale simulator (interop-validated)
├── listener/                Serial reader + config-driven protocol parser
├── controller/              Fill controller GUI (proportional motor control)
├── compliance/              Weighment records, tolerance engine, audit logger
├── integration/             Webhook pusher (n8n / any endpoint)
├── n8n_workflows/           Importable n8n workflow JSON files
├── docs/                    Architecture, protocol guide, compliance model
├── data/audit_log/          Runtime audit trail (gitignored)
└── demo/                    Walkthrough script and recording
```

## Status

🔧 **Under active development.** Core architecture defined. Implementation in progress.

---

*WeighLink — bridging serial instruments to compliant, automated workflows.*
