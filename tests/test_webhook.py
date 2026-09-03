# test_webhook.py - throwaway, do not commit
from compliance.weighment import WeighmentRecord
from integration.webhook_pusher import WebhookPusher

pusher = WebhookPusher()
print(f"Webhook URL: {pusher.url}")
print(f"Enabled: {pusher.is_enabled}\n")

reading = {"header": "ST", "weight": 10.0, "unit": "g",
           "is_stable": True, "device_id": "scale_01"}
record = WeighmentRecord.from_reading(reading)
record.record_id = 1

result = pusher.push(record)
print(f"\nPush result: {result}")
print(f"Success count: {pusher.push_count}, Fail count: {pusher.fail_count}")