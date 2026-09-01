# ==============================================================================
# weighlink/listener/protocol_parser.py
# Config-driven serial protocol parser for industrial weighing instruments.
# Reads field positions and header values from a JSON protocol definition,
# so adding a new instrument protocol is a config entry, not a code change.
# ==============================================================================

import json
import os


class ProtocolParser:
    """
    Parses raw ASCII serial lines into structured weighment dicts
    using field positions defined in a protocol JSON config file.
    
    The parser is stateless — each call to parse() is independent.
    Protocol config is loaded once at init and reused for every parse.
    """

    def __init__(self, protocol_config_path):
        """
        Load and validate the protocol config JSON.
        
        Args:
            protocol_config_path: Absolute or relative path to the protocol
                                  JSON file (e.g. config/protocols/a_and_d.json)
        """
        if not os.path.exists(protocol_config_path):
            raise FileNotFoundError(
                f"Protocol config not found: {protocol_config_path}"
            )

        with open(protocol_config_path, 'r') as f:
            self._config = json.load(f)

        # Extract frequently-used config sections into instance vars
        # to avoid repeated dict lookups on every parse call
        self._fields = self._config["packet_format"]["fields"]
        self._min_length = self._config["packet_format"]["min_length"]
        self._headers = self._config["header_values"]
        self._protocol_name = self._config["protocol_name"]

    @property
    def protocol_name(self):
        """Human-readable protocol name from the config file."""
        return self._protocol_name

    @property
    def serial_settings(self):
        """
        Returns serial port config dict matching pyserial parameter names.
        Translates config-file string values (e.g. "even") to pyserial constants.
        """
        raw = self._config["serial_settings"]

        # Map config string values to pyserial constants
        parity_map = {
            "none": "N",
            "even": "E",
            "odd": "O"
        }

        return {
            "baudrate": raw["baudrate"],
            "bytesize": raw["bytesize"],
            "parity": parity_map.get(raw["parity"], "E"),
            "stopbits": raw["stopbits"],
            "timeout": raw["timeout_seconds"]
        }

    def parse(self, raw_line):
        """
        Parse a single raw serial line into a structured dict.
        
        Args:
            raw_line: bytes object as received from serial.readline()
        
        Returns:
            dict with keys: header, weight, unit, is_stable, is_overload, raw
            None if the line is too short, garbled, or unparseable
        """
        # Decode ASCII, ignoring non-ASCII bytes from line noise
        try:
            decoded = raw_line.decode('ascii', errors='ignore').strip()
        except Exception:
            return None

        # Length gate — reject truncated or empty transmissions
        if len(decoded) < self._min_length:
            return None

        # Extract fields using config-defined positions
        try:
            header_cfg = self._fields["header"]
            weight_cfg = self._fields["weight"]
            unit_cfg = self._fields["unit"]

            header = decoded[header_cfg["start"]:header_cfg["end"]]
            weight_raw = decoded[weight_cfg["start"]:weight_cfg["end"]]
            
            # Unit field: end=null in config means slice to end of string
            unit_end = unit_cfg.get("end")
            unit = decoded[unit_cfg["start"]:unit_end]
            if unit_cfg.get("strip", False):
                unit = unit.strip()

            # Parse weight string to float
            weight = float(weight_raw)

        except (IndexError, ValueError, KeyError):
            # Garbled packet — field extraction or float conversion failed
            return None

        # Classify stability and overload from header value
        is_stable = (header == self._headers.get("stable", "ST"))
        is_overload = (header == self._headers.get("overload", "OL"))

        return {
            "header": header,
            "weight": weight,
            "unit": unit,
            "is_stable": is_stable,
            "is_overload": is_overload,
            "raw": decoded
        }
