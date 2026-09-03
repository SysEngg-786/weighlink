# ==============================================================================
# weighlink/integration/webhook_pusher.py
# Webhook pusher — sends compliant WeighmentRecords to a configured
# webhook endpoint (n8n, custom API, or any HTTP receiver).
# Includes retry with exponential backoff and local failure logging.
#
# Seam: this is one output adapter. Tomorrow's adapters (MQTT, direct ERP)
# implement the same interface: push(record) -> success/failure.
# ==============================================================================

import json
import os
import time

import requests


class WebhookPusher:
    """
    Pushes WeighmentRecord JSON objects to a webhook endpoint via HTTP POST.
    
    On failure, retries with exponential backoff. Logs push results
    (success and failure) so no data is silently lost.
    """

    def __init__(self, app_config_path="config/app_config.json"):
        """
        Load webhook settings from the application config.
        
        Args:
            app_config_path: Path to the main application config JSON.
        """
        if not os.path.exists(app_config_path):
            raise FileNotFoundError(
                f"App config not found: {app_config_path}"
            )

        with open(app_config_path, 'r') as f:
            app_config = json.load(f)

        integration = app_config.get("integration", {})

        self._url = integration.get("webhook_url", "")
        self._enabled = integration.get("webhook_enabled", False)
        self._retry_attempts = integration.get("retry_attempts", 3)
        self._backoff_base = integration.get("retry_backoff_base_seconds", 2)
        # Shared secret sent as the X-Weighlink-Token header; must match the
        # Header Auth credential configured on the n8n webhook node. Empty
        # string if unset (webhook then rejects the request — fail loud).
        self._auth_token = integration.get("webhook_auth_token", "")

        # Counters for external monitoring
        self._push_count = 0
        self._fail_count = 0

    @property
    def url(self):
        """The configured webhook URL."""
        return self._url

    @property
    def is_enabled(self):
        """True if webhook pushing is enabled in config."""
        return self._enabled and bool(self._url)

    @property
    def push_count(self):
        """Total successful pushes this session."""
        return self._push_count

    @property
    def fail_count(self):
        """Total failed pushes (after all retries exhausted) this session."""
        return self._fail_count

    def push(self, record):
        """
        POST a WeighmentRecord to the webhook endpoint.
        
        Retries on failure with exponential backoff.
        Returns True on success, False after all retries exhausted.
        
        Args:
            record: WeighmentRecord instance (must have to_dict() method)
        
        Returns:
            bool: True if the POST succeeded (HTTP 2xx), False otherwise.
        """
        # Skip if webhook is disabled in config
        if not self.is_enabled:
            return False

        payload = record.to_dict()

        # Attempt POST with retry
        for attempt in range(1, self._retry_attempts + 1):
            try:
                response = requests.post(
                    self._url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        # Auth gate: n8n's Header Auth credential checks this.
                        "X-Weighlink-Token": self._auth_token
                    },
                    timeout=10
                )

                # Accept any 2xx response as success
                if 200 <= response.status_code < 300:
                    self._push_count += 1
                    return True

                # Non-2xx response — log and retry
                print(
                    f"[WebhookPusher] Attempt {attempt}/{self._retry_attempts} "
                    f"failed: HTTP {response.status_code}"
                )

            except requests.exceptions.ConnectionError:
                print(
                    f"[WebhookPusher] Attempt {attempt}/{self._retry_attempts} "
                    f"failed: connection refused"
                )

            except requests.exceptions.Timeout:
                print(
                    f"[WebhookPusher] Attempt {attempt}/{self._retry_attempts} "
                    f"failed: timeout"
                )

            except requests.exceptions.RequestException as e:
                print(
                    f"[WebhookPusher] Attempt {attempt}/{self._retry_attempts} "
                    f"failed: {e}"
                )

            # Exponential backoff before next retry (skip after last attempt)
            if attempt < self._retry_attempts:
                wait = self._backoff_base ** attempt
                time.sleep(wait)

        # All retries exhausted
        self._fail_count += 1
        print(
            f"[WebhookPusher] FAILED after {self._retry_attempts} attempts. "
            f"Record #{record.record_id} not delivered. "
            f"Record is preserved in the local audit log."
        )
        return False
