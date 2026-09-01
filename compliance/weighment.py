# ==============================================================================
# weighlink/compliance/weighment.py
# WeighmentRecord — structured data object for a single compliant weighment.
# Carries all fields required for audit trail, tolerance evaluation, and
# downstream integration (webhook, ERP, reporting).
# ==============================================================================

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class WeighmentRecord:
    """
    A single compliant weighment record.
    
    Created from a parsed serial reading (listener output) enriched with
    compliance metadata (tolerance result, operator, lot, audit chain).
    
    Every field is present from creation — no partial records. Fields that
    are not yet populated carry explicit defaults (e.g. 'OP_UNSET') rather
    than None, so downstream consumers never need null-checking.
    """

    # --- Source data (from serial reader) ---
    weight: float                          # Parsed weight value
    unit: str                              # Measurement unit (g, kg, lb)
    header: str                            # Raw header (ST, US, OL)
    is_stable: bool                        # True only for stable readings
    device_id: str                         # Device identifier from config

    # --- Compliance metadata ---
    timestamp: str = ""                    # ISO 8601 UTC, set at creation
    operator_id: str = "OP_UNSET"          # Manual entry in v1; seam for auth
    lot_ref: str = "LOT_UNSET"             # Manual entry in v1; seam for ERP
    tolerance_result: str = "NO_RULE"      # PASS, FAIL, or NO_RULE
    tolerance_min: float = 0.0             # From tolerance config (0 if no rule)
    tolerance_max: float = 0.0             # From tolerance config (0 if no rule)

    # --- Audit chain ---
    record_id: int = 0                     # Sequential, set by audit logger
    prev_hash: str = ""                    # SHA-256 of previous record, set by audit logger

    def __post_init__(self):
        """Set timestamp to current UTC if not already provided."""
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        """Convert to plain dict for JSON serialization."""
        return asdict(self)

    def to_json(self):
        """Serialize to JSON string for webhook POST and audit log."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_reading(cls, reading, operator_id="OP_UNSET", lot_ref="LOT_UNSET"):
        """
        Factory method: create a WeighmentRecord from a parsed serial reading dict.
        
        Args:
            reading: dict from SerialReader callback with keys
                     header, weight, unit, is_stable, device_id
            operator_id: current operator identifier
            lot_ref: current lot/batch reference
        
        Returns:
            WeighmentRecord with source fields populated, compliance fields
            at defaults (tolerance engine fills them next).
        """
        return cls(
            weight=reading["weight"],
            unit=reading["unit"],
            header=reading["header"],
            is_stable=reading["is_stable"],
            device_id=reading["device_id"],
            operator_id=operator_id,
            lot_ref=lot_ref
        )
