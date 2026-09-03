# Protocol Guide

WeighLink parses an instrument's serial output using a JSON protocol definition,
not hard-coded logic. This document explains the A&D protocol configuration
that ships with the system, how the parser consumes it, and how to add a
different instrument as a configuration entry.

## Why config-driven

The parser (`listener/protocol_parser.py`) contains no instrument-specific
constants. It reads field positions, header values, and serial settings from a
protocol JSON at startup and applies them to every incoming line. This means the
same parser handles any fixed-position ASCII instrument — the difference between
an A&D scale and a Mettler balance is a config file, not a code branch. The
active protocol is selected in `app_config.json` (`serial.protocol`), which
resolves to `config/protocols/<name>.json`.

## The A&D protocol, field by field

The delivered configuration is `config/protocols/a_and_d.json`, implementing the
A&D standard ASCII protocol (A&D GX-A/GF-A and FX-i/FZ-i instrument families),
validated against A&D RsWeight 6.04.

### Serial settings

```json
"serial_settings": {
    "baudrate": 9600,
    "bytesize": 7,
    "parity": "even",
    "stopbits": 1,
    "timeout_seconds": 0.5,
    "encoding": "ascii"
}
```

These are the A&D defaults: 9600 baud, 7 data bits, even parity, 1 stop bit
(7-E-1). The parser exposes a `serial_settings` property that maps these
config strings to the constants the serial library expects (for example
`"even"` becomes the even-parity constant), so the reader opens the port with
the correct line discipline without any hard-coded values.

### Packet format

An A&D line is a 17-character fixed format terminated by carriage-return +
line-feed:

```
  HH , S WWW.WWW   UUU  CR LF
  │    │ │         │
  │    │ │         └─ unit  (right-aligned, padded)
  │    │ └─────────── weight (signed, includes sign char)
  │    └───────────── sign   (+ or −, part of the weight field)
  └────────────────── header (stability indicator)

  example:  ST,+001.234   g\r\n
```

The fields block defines each value by character position:

```json
"packet_format": {
    "terminator": "\r\n",
    "min_length": 14,
    "fields": {
        "header": { "start": 0,  "end": 2 },
        "separator": { "position": 2, "expected": "," },
        "sign":   { "position": 3 },
        "weight": { "start": 3,  "end": 11 },
        "unit":   { "start": 11, "end": null, "strip": true }
    }
}
```

- **header** (chars 0–1) — the stability indicator. Mapped to meaning by the
  `header_values` block below.
- **separator** (char 2) — the literal comma; documented for reference.
- **weight** (chars 3–10) — the signed weight, sign character included
  (`+001.234`). The parser converts this substring directly to a float, so the
  sign is handled naturally.
- **unit** (char 11 to end) — right-aligned and space-padded in the A&D frame
  (`"  g"`, `" kg"`); `"strip": true` trims the padding to a clean unit string.
- **min_length: 14** — a length gate. Lines shorter than this are treated as
  truncated line noise and dropped rather than mis-parsed.

Note the `end` values are exclusive slice bounds, and `unit.end: null` means
"slice to the end of the line" — so a unit of any length after position 11 is
captured and then stripped.

### Header values

```json
"header_values": {
    "stable":   "ST",
    "unstable": "US",
    "overload": "OL"
}
```

The parser compares the extracted header against these to set `is_stable` and
`is_overload` on the reading. `is_stable` is the flag the pipeline uses to
decide which readings are pushed downstream — only stable weighments are sent to
the automation layer (see `architecture.md`).

### Commands and output modes

The config also documents the A&D command set (`Q` immediate query, `S` query on
stability, `R` continuous stream, `T` tare, `Z` zero, `ESC` to cancel a stream)
and the instrument's transmission modes (continuous, stability-triggered,
polled, key-press). The serial reader's `send_command()` uses these to drive the
instrument — for example the GUI's tare button sends `Z`.

## What the parser produces

For each valid line, `ProtocolParser.parse()` returns a structured reading:

```python
{
    "header": "ST",
    "weight": 1.234,
    "unit": "g",
    "is_stable": True,
    "is_overload": False,
    "raw": "ST,+001.234   g"
}
```

The serial reader attaches `device_id` (from `app_config.json`) before handing
the reading to the pipeline. Malformed lines — too short, non-numeric weight,
missing fields — return `None` and are skipped, so line noise never becomes a
false weighment.

## Adding a new instrument

Supporting a different instrument (Mettler Toledo MT-SICS, Ohaus, Sartorius SBI,
or any fixed-position ASCII device) is a configuration task:

1. **Create** `config/protocols/<name>.json` following the same structure:
   `protocol_name`, `serial_settings`, `packet_format.fields` (character
   positions for that instrument's frame), `header_values`, and optionally
   `commands`.
2. **Set** the field positions to match the new instrument's frame. Consult the
   instrument's communication manual for its exact ASCII format and line
   discipline.
3. **Point** `app_config.json` at it: `"serial": { "protocol": "<name>" }`.
4. **Validate** against the instrument (or its manufacturer software, as A&D was
   validated against RsWeight) before relying on it.

No parser code changes. The parser reads whatever positions and headers the new
config defines.

### Scope note

The current parser handles **fixed-position ASCII** frames, which covers the A&D
family and many industrial scales. Instruments using a fundamentally different
scheme — delimited/tokenized fields rather than fixed positions, or a binary
protocol — would need a parser extension, not just a config entry. That is a
designed-for seam (a new parser strategy behind the same interface), not part of
the delivered v1. The honest boundary: config-only extension covers
fixed-position ASCII instruments; other schemes are a code extension at a
defined seam.
