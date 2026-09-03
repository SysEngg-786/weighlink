# ==============================================================================
# weighlink/test_push.py
# Standalone test: build one WeighmentRecord and push it through WebhookPusher
# to the live n8n endpoint. Proves the real code path (not curl) end-to-end.
#
# Run from the project root (where config/app_config.json lives):
#     python test_push.py
# ==============================================================================

from compliance.weighment import WeighmentRecord
from integration.webhook_pusher import WebhookPusher


def main():
    # Build one FAIL record (out-of-tolerance) so we exercise both the store
    # path and the Slack alert branch in a single push.
    record = WeighmentRecord(
        weight=77.7,                 # out of range -> FAIL
        unit="kg",
        header="ST",
        is_stable=True,
        device_id="PUSHER-TEST",
        operator_id="OP_PUSHER",
        lot_ref="LOT_PUSHER",
        tolerance_result="FAIL",
        tolerance_min=10.0,
        tolerance_max=15.0,
        record_id=1,
        prev_hash="pushertest",
    )
    # timestamp auto-fills to current UTC via __post_init__

    # Load config (reads config/app_config.json by default) and push.
    pusher = WebhookPusher()

    print(f"Webhook enabled : {pusher.is_enabled}")
    print(f"Target URL      : {pusher.url}")
    print("Pushing record...")

    ok = pusher.push(record)

    print(f"Push result     : {'SUCCESS' if ok else 'FAILED'}")
    print(f"Push count      : {pusher.push_count}")
    print(f"Fail count      : {pusher.fail_count}")


if __name__ == "__main__":
    main()