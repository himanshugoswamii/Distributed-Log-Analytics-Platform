"""
Shared Kafka producer configuration constants.
Import these in any service that needs to produce to Kafka.
"""

PRODUCER_CONFIG = {
    "acks": "all",
    "retries": 3,
    "batch_size": 32768,        # 32 KB batches
    "linger_ms": 10,            # small linger for throughput
    "buffer_memory": 67108864,  # 64 MB buffer
    "compression_type": "lz4",  # fast compression
    "max_request_size": 1048576,
}

TOPIC_LOG_EVENTS = "log-events"
TOPIC_ANOMALY_ALERTS = "anomaly-alerts"
