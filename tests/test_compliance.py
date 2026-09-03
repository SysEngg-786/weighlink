# test_compliance.py - throwaway, do not commit
from compliance.weighment import WeighmentRecord
from compliance.tolerance_engine import ToleranceEngine
from compliance.audit_logger import AuditLogger

# Simulated readings - one PASS, one FAIL, one unstable
readings = [
    {"header": "ST", "weight": 10.0, "unit": "g", "is_stable": True, "device_id": "scale_01"},
    {"header": "ST", "weight": 15.0, "unit": "g", "is_stable": True, "device_id": "scale_01"},
    {"header": "US", "weight": 5.5,  "unit": "g", "is_stable": False, "device_id": "scale_01"},
]

engine = ToleranceEngine("config/tolerances/demo_product.json")
logger = AuditLogger()

print(f"Tolerance profile: {engine.profile_name}")
print(f"Audit log: {logger.log_path}\n")

for r in readings:
    record = WeighmentRecord.from_reading(r)
    engine.evaluate(record)
    logger.log(record)
    print(f"#{record.record_id} weight={record.weight} "
          f"result={record.tolerance_result} "
          f"hash={record.prev_hash[:16]}...")

# Verify the chain
valid, count, err = AuditLogger.verify_chain(logger.log_path)
print(f"\nChain verification: valid={valid}, records={count}, error={err}")