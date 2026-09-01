# ==============================================================================
# weighlink/listener/serial_reader.py
# Serial stream reader for industrial weighing instruments.
# Opens a COM port using config-driven settings, reads continuously,
# and dispatches parsed readings via a callback function.
# Runs headless (no GUI) — the controller GUI imports this module.
# ==============================================================================

import json
import os
import threading
import time

import serial

from listener.protocol_parser import ProtocolParser


# --------------------------------------------------------------------------
# Mapping helpers: translate config-file strings to pyserial constants
# --------------------------------------------------------------------------
BYTESIZE_MAP = {
    5: serial.FIVEBITS,
    6: serial.SIXBITS,
    7: serial.SEVENBITS,
    8: serial.EIGHTBITS
}

PARITY_MAP = {
    "N": serial.PARITY_NONE,
    "E": serial.PARITY_EVEN,
    "O": serial.PARITY_ODD
}

STOPBITS_MAP = {
    1: serial.STOPBITS_ONE,
    2: serial.STOPBITS_TWO
}


class SerialReader:
    """
    Connects to a serial instrument, reads the data stream continuously,
    parses each line using ProtocolParser, and dispatches parsed readings
    to a registered callback function.
    
    Designed to run in a background thread so the calling application
    (GUI or headless service) remains responsive.
    """

    def __init__(self, app_config_path="config/app_config.json"):
        """
        Load application and protocol configs. Does NOT open the port yet —
        call connect() explicitly to establish the serial connection.
        
        Args:
            app_config_path: Path to the main application config JSON.
        """
        # Load application-level config
        if not os.path.exists(app_config_path):
            raise FileNotFoundError(
                f"App config not found: {app_config_path}"
            )

        with open(app_config_path, 'r') as f:
            self._app_config = json.load(f)

        # Resolve protocol config path from app config
        protocol_name = self._app_config["serial"]["protocol"]
        protocol_path = os.path.join(
            "config", "protocols", f"{protocol_name}.json"
        )

        # Initialize the protocol parser
        self._parser = ProtocolParser(protocol_path)

        # Serial connection state
        self._port_name = self._app_config["serial"]["listener_port"]
        self._serial_conn = None
        self._is_running = False
        self._read_thread = None

        # Callback for parsed readings — set via on_reading()
        self._reading_callback = None

        # Device identity from config
        self._device_id = self._app_config.get("device", {}).get(
            "device_id", "unknown"
        )

    @property
    def port_name(self):
        """The configured COM port name."""
        return self._port_name

    @property
    def device_id(self):
        """Device identifier from config."""
        return self._device_id

    @property
    def is_connected(self):
        """True if the serial port is open and the read loop is running."""
        return self._is_running and self._serial_conn and self._serial_conn.is_open

    @property
    def parser(self):
        """Expose the protocol parser for external use (e.g. command formatting)."""
        return self._parser

    def on_reading(self, callback):
        """
        Register a callback that fires on every successfully parsed reading.
        
        The callback receives one argument: a dict with keys
        header, weight, unit, is_stable, is_overload, raw, device_id.
        
        Args:
            callback: callable(reading_dict)
        """
        self._reading_callback = callback

    def connect(self):
        """
        Open the serial port and start the background read loop.
        
        Returns:
            True if connection succeeded, False otherwise.
        
        Raises:
            serial.SerialException if the port cannot be opened.
        """
        if self._is_running:
            return True

        # Build pyserial kwargs from protocol config
        settings = self._parser.serial_settings

        self._serial_conn = serial.Serial(
            port=self._port_name,
            baudrate=settings["baudrate"],
            bytesize=BYTESIZE_MAP.get(settings["bytesize"], serial.SEVENBITS),
            parity=PARITY_MAP.get(settings["parity"], serial.PARITY_EVEN),
            stopbits=STOPBITS_MAP.get(settings["stopbits"], serial.STOPBITS_ONE),
            timeout=settings.get("timeout", 0.5)
        )

        self._is_running = True

        # Start the read loop in a daemon thread so it dies with the main process
        self._read_thread = threading.Thread(
            target=self._read_loop, daemon=True
        )
        self._read_thread.start()

        return True

    def disconnect(self):
        """Stop the read loop and close the serial port."""
        self._is_running = False

        if self._serial_conn and self._serial_conn.is_open:
            self._serial_conn.close()

        # Wait for the read thread to exit cleanly
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)

        self._serial_conn = None

    def send_command(self, command_str):
        """
        Send a command string to the connected instrument.
        Appends CR+LF terminator as required by A&D protocol.
        
        Args:
            command_str: Single character command (e.g. 'Z' for tare,
                        'Q' for query, 'S' for stability query)
        """
        if self._serial_conn and self._serial_conn.is_open:
            self._serial_conn.write(f"{command_str}\n".encode('ascii'))

    def _read_loop(self):
        """
        Continuous background loop: read serial lines, parse, dispatch.
        Runs until disconnect() sets _is_running to False.
        """
        while self._is_running:
            if not (self._serial_conn and self._serial_conn.is_open):
                break

            try:
                # Read one complete line (terminated by LF)
                raw_line = self._serial_conn.readline()

                if not raw_line:
                    # Timeout with no data — loop back
                    continue

                # Parse the raw bytes through the protocol parser
                parsed = self._parser.parse(raw_line)

                if parsed is None:
                    # Garbled or too-short packet — skip
                    continue

                # Attach device identity to the reading
                parsed["device_id"] = self._device_id

                # Dispatch to registered callback
                if self._reading_callback:
                    self._reading_callback(parsed)

            except serial.SerialException as e:
                # Port error (cable pulled, device reset) — stop cleanly
                print(f"[SerialReader] Port error: {e}")
                break

            except Exception as e:
                # Unexpected error — log and continue rather than crash
                print(f"[SerialReader] Read error: {e}")
                continue

            # Small sleep to prevent CPU spin on fast streams
            time.sleep(0.01)

        self._is_running = False
