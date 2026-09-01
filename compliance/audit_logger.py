# ==============================================================================
# weighlink/compliance/audit_logger.py
# Audit logger — writes WeighmentRecords to an append-only JSONL file
# with sequential record IDs and SHA-256 hash chain for tamper evidence.
#
# Design:
# - Append-only: no edits, no deletes, no overwrites
# - Each record carries the SHA-256 hash of the previous record
# - A broken hash chain means the log was tampered with
# - One JSONL file per session (timestamped filename)
# - This is lightweight tamper evidence, not cryptographic proof —
#   sufficient for demonstrating the compliance architecture
# ==============================================================================

import hashlib
import json
import os
from datetime import datetime, timezone


class AuditLogger:
    """
    Append-only audit trail for compliant weighment records.
    
    Each record is written as a single JSON line (JSONL format).
    Records carry sequential IDs and a SHA-256 hash chain linking
    each record to its predecessor for tamper evidence.
    """

    def __init__(self, log_dir="data/audit_log"):
        """
        Initialize the audit logger. Creates the log directory if needed
        and opens a new JSONL file for this session.
        
        Args:
            log_dir: Directory where audit log files are stored.
                     Defaults to data/audit_log/ (gitignored).
        """
        # Ensure the log directory exists
        os.makedirs(log_dir, exist_ok=True)

        # Generate session-specific filename with UTC timestamp
        session_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._log_path = os.path.join(
            log_dir, f"audit_{session_ts}.jsonl"
        )

        # Sequential record counter — starts at 1 for each session
        self._next_id = 1

        # Hash chain state — genesis record has no predecessor
        self._prev_hash = "GENESIS"

        # Track record count for external queries
        self._record_count = 0

    @property
    def log_path(self):
        """Path to the current session's audit log file."""
        return self._log_path

    @property
    def record_count(self):
        """Number of records written in this session."""
        return self._record_count

    def log(self, record):
        """
        Write a WeighmentRecord to the audit log.
        
        Assigns a sequential record_id, computes the hash chain link,
        and appends the record as a single JSON line.
        
        Args:
            record: WeighmentRecord instance (modified in place with
                    record_id and prev_hash)
        
        Returns:
            The same WeighmentRecord with record_id and prev_hash set.
        """
        # Assign sequential ID
        record.record_id = self._next_id

        # Link to previous record via hash chain
        record.prev_hash = self._prev_hash

        # Serialize to JSON for writing and hashing
        record_json = record.to_json()

        # Compute SHA-256 hash of this record (becomes prev_hash for next)
        record_hash = hashlib.sha256(record_json.encode('utf-8')).hexdigest()

        # Append to JSONL file — one complete JSON object per line
        with open(self._log_path, 'a', encoding='utf-8') as f:
            f.write(record_json + "\n")

        # Advance chain state
        self._prev_hash = record_hash
        self._next_id += 1
        self._record_count += 1

        return record

    @staticmethod
    def verify_chain(log_path):
        """
        Verify the hash chain integrity of an existing audit log file.
        
        Reads every record, recomputes the hash chain, and checks that
        each record's prev_hash matches the computed hash of its
        predecessor. A mismatch means the log was tampered with.
        
        Args:
            log_path: Path to the JSONL audit log file to verify.
        
        Returns:
            tuple: (is_valid: bool, record_count: int, error_msg: str or None)
        """
        if not os.path.exists(log_path):
            return False, 0, f"File not found: {log_path}"

        prev_hash = "GENESIS"
        record_count = 0

        with open(log_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return False, record_count, (
                        f"Line {line_num}: invalid JSON"
                    )

                # Check that this record's prev_hash matches expected
                stored_prev_hash = record.get("prev_hash", "")
                if stored_prev_hash != prev_hash:
                    return False, record_count, (
                        f"Line {line_num} (record_id={record.get('record_id')}): "
                        f"hash chain broken. "
                        f"Expected prev_hash={prev_hash[:16]}..., "
                        f"found={stored_prev_hash[:16]}..."
                    )

                # Recompute hash of this record for the next check
                # Must use the exact JSON string as stored
                prev_hash = hashlib.sha256(
                    line.encode('utf-8')
                ).hexdigest()

                record_count += 1

        return True, record_count, None
