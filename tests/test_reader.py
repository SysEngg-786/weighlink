# test_reader.py - debug version
from listener.serial_reader import SerialReader

def on_reading(data):
    print(f"[{data['header']}] {data['weight']:+08.3f} {data['unit']} "
          f"stable={data['is_stable']} device={data['device_id']}")

reader = SerialReader()
reader.on_reading(on_reading)

# Debug: patch the read loop to show raw bytes
original_parse = reader.parser.parse
def debug_parse(raw_line):
    print(f"[RAW] {repr(raw_line)}")
    result = original_parse(raw_line)
    if result is None:
        print("[PARSE] Rejected")
    return result
reader._parser.parse = debug_parse

reader.connect()
input("Press Enter to stop...\n")
reader.disconnect()