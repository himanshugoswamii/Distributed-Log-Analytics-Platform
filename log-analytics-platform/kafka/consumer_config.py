"""
Shared Kafka consumer configuration constants.
Import these in any service that needs to consume from Kafka.
"""

CONSUMER_CONFIG = {
    "auto_offset_reset": "latest",
    "enable_auto_commit": True,
    "auto_commit_interval_ms": 5000,
    "max_poll_records": 500,
    "fetch_max_bytes": 52428800,  # 50 MB
    "session_timeout_ms": 30000,
    "heartbeat_interval_ms": 10000,
}

TOPIC_LOG_EVENTS = "log-events"
TOPIC_ANOMALY_ALERTS = "anomaly-alerts"
