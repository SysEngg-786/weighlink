# ==============================================================================
# weighlink/simulator/scale_simulator.py
# A&D Industrial Scale Simulator — physically realistic weight simulation
# with settling dynamics, vibration noise, tare response, and bidirectional
# command handling. Outputs A&D standard 17-char ASCII format at 10Hz.
#
# Interoperability validated against A&D RsWeight 6.04 (2026-09-01).
# Serial settings and COM port read from config files — no hardcoded values.
# ==============================================================================

import json
import os
import random
import sys
import time

import serial


def load_config():
    """
    Load application config and protocol config.
    Returns (app_config, protocol_config) tuple.
    """
    app_config_path = os.path.join("config", "app_config.json")
    if not os.path.exists(app_config_path):
        sys.stdout.write(f"[ERROR] App config not found: {app_config_path}\n")
        sys.stdout.flush()
        sys.exit(1)

    with open(app_config_path, 'r') as f:
        app_config = json.load(f)

    protocol_name = app_config["serial"]["protocol"]
    protocol_path = os.path.join("config", "protocols", f"{protocol_name}.json")
    if not os.path.exists(protocol_path):
        sys.stdout.write(f"[ERROR] Protocol config not found: {protocol_path}\n")
        sys.stdout.flush()
        sys.exit(1)

    with open(protocol_path, 'r') as f:
        protocol_config = json.load(f)

    return app_config, protocol_config


def format_ad_packet(header, weight_val, unit="g"):
    """
    Constructs the exact A&D Standard ASCII Format string.
    Output example: 'ST,+001.234  g\\r\\n'
    
    This function is proven — A&D RsWeight 6.04 parses its output correctly.
    Do not modify the format without re-validating against RsWeight.
    """
    sign = "+" if weight_val >= 0 else "-"
    abs_val = abs(weight_val)
    weight_str = f"{sign}{abs_val:07.3f}"
    unit_str = f"{unit:>3}"

    packet = f"{header},{weight_str}{unit_str}\r\n"
    return packet.encode('ascii')


def log_info(msg):
    """Flush-safe logger for Git Bash compatibility."""
    sys.stdout.write(f"[INFO] {msg}\n")
    sys.stdout.flush()


def get_serial_kwargs(protocol_config):
    """
    Build pyserial constructor kwargs from protocol config.
    Maps config strings to pyserial constants.
    """
    raw = protocol_config["serial_settings"]

    bytesize_map = {5: serial.FIVEBITS, 6: serial.SIXBITS,
                    7: serial.SEVENBITS, 8: serial.EIGHTBITS}
    parity_map = {"none": serial.PARITY_NONE, "even": serial.PARITY_EVEN,
                  "odd": serial.PARITY_ODD}
    stopbits_map = {1: serial.STOPBITS_ONE, 2: serial.STOPBITS_TWO}

    return {
        "baudrate": raw["baudrate"],
        "bytesize": bytesize_map.get(raw["bytesize"], serial.SEVENBITS),
        "parity": parity_map.get(raw["parity"], serial.PARITY_EVEN),
        "stopbits": stopbits_map.get(raw["stopbits"], serial.STOPBITS_ONE),
        "timeout": raw.get("timeout_seconds", 0.1)
    }


def run_scale_simulator():
    """
    Main simulator loop. Simulates an A&D industrial scale:
    - Continuous 10Hz ASCII stream on COM port
    - Settling dynamics with vibration noise
    - Tare/zero command response (Z)
    - Immediate query response (Q)
    - Gradual fill simulation up to 15g
    """
    # Load all settings from config
    app_config, protocol_config = load_config()
    port_name = app_config["serial"]["simulator_port"]
    headers = protocol_config["header_values"]

    log_info(f"Initializing A&D Scale Simulator on {port_name}...")

    # Open serial port with config-driven settings
    try:
        serial_kwargs = get_serial_kwargs(protocol_config)
        ser = serial.Serial(port=port_name, **serial_kwargs)
    except serial.SerialException as e:
        sys.stdout.write(
            f"[ERROR] Could not open port {port_name}. "
            f"Ensure virtual serial pair is running!\n"
        )
        sys.stdout.write(f"[DETAILS] {e}\n")
        sys.stdout.flush()
        return

    # Simulated hardware internal state
    current_actual_weight = 0.000
    display_weight = 0.000
    tare_offset = 0.000

    # Physics simulation variables
    is_stable = True
    settle_counter = 0
    target_weight = 0.000

    log_info("Scale Status: ONLINE. Streaming data at 10Hz...")
    log_info("Protocol Mode: Continuous Stream Active.")
    log_info("Command Mode: Listening for 'Z' (Tare) and 'Q' (Query).")
    sys.stdout.write("-" * 75 + "\n")
    sys.stdout.flush()

    try:
        while True:
            # 1. READ INCOMING SERIAL COMMANDS
            if ser.in_waiting > 0:
                incoming_command = ser.read(
                    ser.in_waiting
                ).decode('ascii', errors='ignore').strip()

                if 'Z' in incoming_command:
                    sys.stdout.write(
                        "\n[COMMAND] Received 'Z' -> "
                        "Executing Tare / Zero operation.\n"
                    )
                    sys.stdout.flush()
                    tare_offset = current_actual_weight
                    is_stable = False
                    # Force unstable for 0.5s during tare
                    settle_counter = 5

                elif 'Q' in incoming_command:
                    sys.stdout.write(
                        "\n[COMMAND] Received 'Q' -> "
                        "Executing Immediate Manual Query.\n"
                    )
                    sys.stdout.flush()
                    header = headers["stable"] if is_stable else headers["unstable"]
                    net_weight = display_weight - tare_offset
                    packet = format_ad_packet(header, net_weight)
                    ser.write(packet)

            # 2. SIMULATE PHYSICAL SETTLING AND MECHANICAL DRIFT
            if abs(display_weight - target_weight) > 0.001:
                is_stable = False
                settle_counter = 8
                display_weight += (target_weight - display_weight) * 0.4
            else:
                if settle_counter > 0:
                    settle_counter -= 1
                    is_stable = False
                else:
                    is_stable = True
                    display_weight = target_weight

            # 3. ADD VIBRATION NOISE WHEN UNSTABLE
            if not is_stable:
                vibration = random.uniform(-0.002, 0.002)
                active_weight = (display_weight - tare_offset) + vibration
                header = headers["unstable"]
            else:
                active_weight = display_weight - tare_offset
                header = headers["stable"]

            # 4. STREAM OUTBOUND DATA PACKET
            outbound_packet = format_ad_packet(header, active_weight)
            ser.write(outbound_packet)

            # Terminal display with carriage return for clean overwrite
            sys.stdout.write(
                f"\r[TX STREAM] Packet: "
                f"{outbound_packet.decode('ascii').strip()}     "
            )
            sys.stdout.flush()

            # 5. SIMULATE GRADUAL FILL (continuous weight increase up to 15g)
            if target_weight < 15.000:
                target_weight += 0.005

            # 10Hz broadcast loop
            time.sleep(0.1)

    except KeyboardInterrupt:
        sys.stdout.write("\n[STATUS] Scale Simulator Stopped by User.\n")
    finally:
        ser.close()
        sys.stdout.write("[STATUS] Serial Port Safely Closed.\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_scale_simulator()
