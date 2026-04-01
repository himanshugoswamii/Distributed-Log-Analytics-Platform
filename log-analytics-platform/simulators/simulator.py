"""
Log event simulator — produces structured log events to Kafka at a configurable rate.
Each instance represents one microservice emitting realistic log data.
"""

import json
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

SERVICE_NAME = os.environ.get("SERVICE_NAME", "unknown-service")
KAFKA_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "log-events")
EVENTS_PER_SECOND = int(os.environ.get("EVENTS_PER_SECOND", "100"))

LOG_LEVELS = ["INFO", "WARN", "ERROR", "CRITICAL"]
LOG_WEIGHTS = [0.70, 0.20, 0.08, 0.02]

MESSAGE_TEMPLATES = {
    "auth-service": {
        "INFO": [
            "User {user_id} logged in successfully",
            "Token refreshed for user {user_id}",
            "Password validation passed for user {user_id}",
            "Session created: {session_id}",
        ],
        "WARN": [
            "Failed login attempt for user {user_id} — attempt {attempt}/5",
            "Token nearing expiry for user {user_id}",
            "Rate limit approaching for IP {ip}",
        ],
        "ERROR": [
            "Authentication failed: invalid credentials for {user_id}",
            "Token verification failed: {error}",
            "OAuth provider timeout after {latency}ms",
        ],
        "CRITICAL": [
            "Auth database connection pool exhausted",
            "JWT signing key rotation failed",
        ],
    },
    "payments-service": {
        "INFO": [
            "Payment processed: ${amount} for order {order_id}",
            "Refund initiated: ${amount} for order {order_id}",
            "Payment method verified for user {user_id}",
        ],
        "WARN": [
            "Payment retry #{attempt} for order {order_id}",
            "Slow payment gateway response: {latency}ms",
            "Duplicate payment detected for order {order_id}",
        ],
        "ERROR": [
            "Payment declined: insufficient funds for order {order_id}",
            "Payment gateway error: {error}",
            "Charge-back received for order {order_id}",
        ],
        "CRITICAL": [
            "Payment gateway unreachable — circuit breaker open",
            "Fraud detection system offline",
        ],
    },
    "orders-service": {
        "INFO": [
            "Order {order_id} created by user {user_id}",
            "Order {order_id} status changed to {status}",
            "Inventory reserved for order {order_id}",
        ],
        "WARN": [
            "Order {order_id} item back-ordered",
            "Shipping estimate delayed for order {order_id}",
        ],
        "ERROR": [
            "Order {order_id} failed: {error}",
            "Inventory reservation timeout for order {order_id}",
        ],
        "CRITICAL": [
            "Order processing pipeline stalled — queue depth {depth}",
        ],
    },
}

DEFAULT_TEMPLATES = {
    "INFO": [
        "Request processed in {latency}ms",
        "Health check passed",
        "Cache hit ratio: {ratio}%",
        "Connection established to {dependency}",
        "Background job completed: {job_id}",
    ],
    "WARN": [
        "High memory usage: {memory}%",
        "Response time elevated: {latency}ms",
        "Retry attempt #{attempt} for operation {op}",
        "Connection pool utilization at {ratio}%",
    ],
    "ERROR": [
        "Request failed with status {status_code}: {error}",
        "Database query timeout after {latency}ms",
        "Unhandled exception: {error}",
    ],
    "CRITICAL": [
        "Service health check failed — restarting",
        "Memory limit exceeded: {memory}MB",
        "Deadlock detected in connection pool",
    ],
}

ERRORS = [
    "ConnectionResetError", "TimeoutError", "ValueError",
    "IOError", "RuntimeError", "PermissionDenied",
]
STATUSES = ["processing", "shipped", "delivered", "cancelled"]
DEPENDENCIES = ["redis", "postgres", "elasticsearch", "s3", "rabbitmq"]

shutdown = False


def handle_signal(signum, frame):
    global shutdown
    shutdown = True


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def random_ip():
    return f"{random.randint(10, 192)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def fill_template(template: str) -> str:
    replacements = {
        "{user_id}": f"usr_{random.randint(1000, 9999)}",
        "{session_id}": str(uuid.uuid4())[:8],
        "{order_id}": f"ord_{random.randint(10000, 99999)}",
        "{ip}": random_ip(),
        "{attempt}": str(random.randint(1, 5)),
        "{latency}": str(random.randint(5, 5000)),
        "{error}": random.choice(ERRORS),
        "{amount}": f"{random.uniform(1.0, 999.99):.2f}",
        "{status}": random.choice(STATUSES),
        "{status_code}": str(random.choice([400, 401, 403, 404, 500, 502, 503])),
        "{memory}": str(random.randint(70, 99)),
        "{ratio}": str(random.randint(50, 99)),
        "{dependency}": random.choice(DEPENDENCIES),
        "{job_id}": f"job_{random.randint(100, 9999)}",
        "{op}": random.choice(["db_write", "cache_refresh", "api_call", "file_sync"]),
        "{depth}": str(random.randint(1000, 50000)),
    }
    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result


def generate_log_event() -> dict:
    level = random.choices(LOG_LEVELS, weights=LOG_WEIGHTS, k=1)[0]
    templates = MESSAGE_TEMPLATES.get(SERVICE_NAME, DEFAULT_TEMPLATES).get(
        level, DEFAULT_TEMPLATES[level]
    )
    message = fill_template(random.choice(templates))

    return {
        "log_id": str(uuid.uuid4()),
        "service_name": SERVICE_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_level": level,
        "message": message,
        "metadata": json.dumps({
            "host": f"{SERVICE_NAME}-{random.randint(1, 3)}",
            "pid": random.randint(1, 65535),
            "thread": f"worker-{random.randint(1, 16)}",
            "request_id": str(uuid.uuid4())[:12],
            "response_time_ms": random.randint(1, 2000) if level != "INFO" else random.randint(1, 200),
        }),
    }


def create_producer() -> KafkaProducer:
    """Create Kafka producer with retries for startup race conditions."""
    max_retries = 30
    for attempt in range(1, max_retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVERS.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                batch_size=32768,
                linger_ms=10,
                buffer_memory=67108864,
                compression_type="lz4",
            )
            print(f"[{SERVICE_NAME}] Connected to Kafka at {KAFKA_SERVERS}", flush=True)
            return producer
        except NoBrokersAvailable:
            print(
                f"[{SERVICE_NAME}] Kafka not ready (attempt {attempt}/{max_retries}), retrying in 3s...",
                flush=True,
            )
            time.sleep(3)
    print(f"[{SERVICE_NAME}] FATAL: Could not connect to Kafka", flush=True)
    sys.exit(1)


def main():
    producer = create_producer()
    interval = 1.0 / EVENTS_PER_SECOND
    total_sent = 0
    batch_start = time.monotonic()

    print(
        f"[{SERVICE_NAME}] Producing {EVENTS_PER_SECOND} events/sec to topic '{KAFKA_TOPIC}'",
        flush=True,
    )

    try:
        while not shutdown:
            event = generate_log_event()
            producer.send(
                KAFKA_TOPIC,
                key=SERVICE_NAME,
                value=event,
            )
            total_sent += 1

            if total_sent % 1000 == 0:
                elapsed = time.monotonic() - batch_start
                rate = 1000 / elapsed if elapsed > 0 else 0
                print(
                    f"[{SERVICE_NAME}] Sent {total_sent} events — current rate: {rate:.0f} events/sec",
                    flush=True,
                )
                batch_start = time.monotonic()

            # Pace the output to target events/sec
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush()
        producer.close()
        print(f"[{SERVICE_NAME}] Shutdown — total events sent: {total_sent}", flush=True)


if __name__ == "__main__":
    main()
