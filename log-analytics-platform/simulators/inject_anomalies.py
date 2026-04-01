"""
Anomaly injection script — produces deliberately anomalous log events
to Kafka topic "log-events" to verify the end-to-end anomaly detection
pipeline (Spark → Isolation Forest → Kafka anomaly-alerts → Dashboard).

Three scenarios:
  1. Sudden burst:   50 CRITICAL logs from one service in < 2 seconds
  2. Error spike:    30 consecutive ERROR logs with extreme response times
  3. Silent service: normal activity → 30s silence → anomalous recovery burst

Run from host:  python inject_anomalies.py
Run in Docker:  KAFKA_BOOTSTRAP_SERVERS=kafka:9092 python inject_anomalies.py
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

KAFKA_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC = "log-events"

SEPARATOR = "=" * 60


def create_producer():
    max_retries = 10
    for attempt in range(1, max_retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVERS.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                batch_size=16384,
                linger_ms=5,
                compression_type="lz4",
            )
            print(f"[inject] Connected to Kafka at {KAFKA_SERVERS}")
            return producer
        except NoBrokersAvailable:
            print(f"[inject] Kafka not ready ({attempt}/{max_retries}), retrying...")
            time.sleep(2)
    print("[inject] FATAL: Could not connect to Kafka")
    sys.exit(1)


def make_event(service_name, log_level, message, response_time_ms):
    """Build a log event dict matching the simulator schema."""
    return {
        "log_id": str(uuid.uuid4()),
        "service_name": service_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_level": log_level,
        "message": message,
        "metadata": json.dumps({
            "host": f"{service_name}-inject",
            "pid": 99999,
            "thread": "anomaly-injector",
            "request_id": str(uuid.uuid4())[:12],
            "response_time_ms": response_time_ms,
        }),
    }


def scenario_sudden_burst(producer):
    """
    Scenario 1 — Sudden burst: one service emits 50 CRITICAL logs in < 2 seconds.

    Feature values crafted to be far outside the Isolation Forest training distribution:
      level_code=3 (CRITICAL), msg_length~200-300, response_time=15000-25000ms
    Training normal: level mostly 0, response_time for CRITICAL ~N(1000, 400)
    """
    print(f"\n{SEPARATOR}")
    print("SCENARIO 1: Sudden Burst — 50 CRITICAL logs in < 2 seconds")
    print(f"{SEPARATOR}")

    service = "payments-service"
    messages = [
        "CIRCUIT BREAKER OPEN — payment gateway completely unreachable, "
        "all downstream requests failing with connection refused errors, "
        "retry queue depth exceeded 50000, manual intervention required immediately, "
        "customer transactions are being dropped silently, revenue impact critical, "
        "failover to backup gateway also failing with TLS handshake timeout",

        "CASCADING FAILURE — database connection pool exhausted across all shards, "
        "every query timing out after 30 seconds, thread pool saturated at 100%, "
        "garbage collection pauses exceeding 15 seconds, heap memory at 98%, "
        "out-of-memory kill imminent, dependent services auth and orders also degrading",

        "FATAL DEADLOCK — transaction manager detected unresolvable deadlock across "
        "payment_transactions and refund_ledger tables, lock wait timeout exceeded 60s, "
        "rollback cascade affecting 2847 in-flight transactions, data consistency at risk, "
        "manual database intervention and possible point-in-time recovery needed",

        "CRITICAL SECURITY ALERT — anomalous transaction pattern detected, "
        "347 high-value transactions from same IP range in 90 seconds, "
        "fraud scoring service unresponsive, rate limiter bypassed via API key rotation, "
        "potential coordinated attack in progress, blocking all transactions from region",

        "INFRASTRUCTURE MELTDOWN — kubernetes pod OOMKilled 12 times in 5 minutes, "
        "horizontal pod autoscaler stuck at maximum replicas, persistent volume claims "
        "failing with storage class provisioner timeout, service mesh sidecar injection "
        "broken, east-west traffic routing through degraded path, SLA breach imminent",
    ]

    start = time.monotonic()
    for i in range(50):
        msg = messages[i % len(messages)]
        event = make_event(service, "CRITICAL", msg, 15000 + (i * 200))
        producer.send(KAFKA_TOPIC, key=service, value=event)

    producer.flush()
    elapsed = time.monotonic() - start

    print(f"  [OK] Injected 50 CRITICAL events from '{service}' in {elapsed:.2f}s")
    print(f"  Features: level=CRITICAL, msg_length~300+, response_time=15000-25000ms")
    print(f"  Expected: all 50 should score well below the -0.15 anomaly threshold")


def scenario_error_spike(producer):
    """
    Scenario 2 — Error spike: 30 consecutive ERROR logs from one service,
    no INFO logs in between. Extreme response times and long messages.

    Feature values: level_code=2 (ERROR), msg_length~250+, response_time=8000-15000ms
    Training normal for ERROR: response_time ~N(500, 200), msg_length ~N(80, 20)
    """
    print(f"\n{SEPARATOR}")
    print("SCENARIO 2: Error Spike — 30 consecutive ERRORs, zero INFO logs")
    print(f"{SEPARATOR}")

    service = "orders-service"
    error_messages = [
        "Order processing pipeline completely stalled — RabbitMQ consumer lag "
        "exceeded 100000 messages, all workers in NACK state, dead letter queue "
        "overflow causing message loss, estimated 15000 orders stuck in pending state, "
        "customer-facing checkout returning 503 for all regions",

        "Inventory reservation system returned CONFLICT for every request in the last "
        "60 seconds, distributed lock service unresponsive, optimistic concurrency "
        "violations on 100% of write attempts, stock levels potentially inconsistent "
        "across 3 data centers, overselling risk is HIGH",

        "Elasticsearch order search index corrupted after failed bulk indexing operation, "
        "mapping conflicts on 47 fields, reindex job failing with circuit_breaking_exception, "
        "customer order history queries returning partial or empty results, "
        "full reindex estimated 4 hours with current cluster health YELLOW",

        "Database replication lag exceeded 45 seconds on read replicas, "
        "read-after-write consistency violations detected on order status updates, "
        "customers seeing stale order states, webhook notifications firing with "
        "incorrect status values, partner API SLA breached",

        "gRPC connection to shipping-service terminated with UNAVAILABLE status, "
        "all 50 retry attempts exhausted, circuit breaker in OPEN state for 300 seconds, "
        "4200 orders awaiting shipping label generation, customer promise dates "
        "will be missed for all affected orders in NA-EAST-1 region",
    ]

    start = time.monotonic()
    for i in range(30):
        msg = error_messages[i % len(error_messages)]
        event = make_event(service, "ERROR", msg, 8000 + (i * 250))
        producer.send(KAFKA_TOPIC, key=service, value=event)
        time.sleep(0.03)

    producer.flush()
    elapsed = time.monotonic() - start

    print(f"  [OK] Injected 30 ERROR events from '{service}' in {elapsed:.2f}s")
    print(f"  Features: level=ERROR, msg_length~300+, response_time=8000-15500ms")
    print(f"  Expected: ERROR + extreme response_time should trigger anomaly scoring")


def scenario_silent_service(producer):
    """
    Scenario 3 — Silent service: a service sends normal logs, goes silent
    for 30 seconds, then resumes with anomalous CRITICAL events indicating
    the service had a catastrophic failure and is recovering.

    The silence itself can't be scored by the Isolation Forest (it scores
    individual events, not absence). But the recovery burst after silence
    contains clearly anomalous events: CRITICAL with extreme response times
    and long messages describing the failure.
    """
    print(f"\n{SEPARATOR}")
    print("SCENARIO 3: Silent Service — normal → 30s silence → anomalous recovery")
    print(f"{SEPARATOR}")

    service = "auth-service"

    print(f"  Phase 1: Sending 10 normal INFO logs from '{service}'...")
    for i in range(10):
        event = make_event(
            service, "INFO",
            f"User usr_{1000+i} logged in successfully",
            30 + (i * 5),
        )
        producer.send(KAFKA_TOPIC, key=service, value=event)
        time.sleep(0.1)
    producer.flush()
    print(f"  [OK] Normal logs sent")

    print(f"  Phase 2: Simulating 30-second silence (no logs from '{service}')...")
    for remaining in range(30, 0, -5):
        print(f"         ... {remaining}s remaining")
        time.sleep(5)
    print(f"  [OK] Silence period complete")

    print(f"  Phase 3: Sending 20 CRITICAL recovery-burst logs...")
    recovery_messages = [
        "SERVICE RESTART — cold boot after unexpected termination, "
        "signal SIGKILL received, core dump generated at /var/crash/auth-20260318.core, "
        "all in-memory session caches lost, approximately 45000 active sessions invalidated, "
        "users will experience forced re-authentication across all platforms, "
        "estimated recovery time 10-15 minutes for full session reconstruction",

        "POST-CRASH RECOVERY — database connection re-establishment failed 8 times, "
        "TCP connection pool rebuild in progress, certificate chain validation timeout "
        "on mutual TLS handshake with vault service, secrets refresh blocked, "
        "JWT signing key unavailable, all token operations returning 500",

        "CACHE RECONSTRUCTION — Redis cluster node failover detected during downtime, "
        "master promoted on shard 3, 2.1 million session keys require re-warming, "
        "current cache hit ratio dropped from 99.2% to 3.4%, database under extreme "
        "read load handling all session lookups directly, query latency 45x normal",

        "REPLICATION CATCH-UP — auth event stream 847293 events behind, "
        "consumer group rebalancing after member timeout, partition reassignment "
        "across 6 partitions, estimated catch-up time 8 minutes at current throughput, "
        "audit trail has 30-second gap that must be investigated for compliance",
    ]

    start = time.monotonic()
    for i in range(20):
        msg = recovery_messages[i % len(recovery_messages)]
        event = make_event(service, "CRITICAL", msg, 20000 + (i * 500))
        producer.send(KAFKA_TOPIC, key=service, value=event)
        time.sleep(0.05)
    producer.flush()
    elapsed = time.monotonic() - start

    print(f"  [OK] Injected 20 CRITICAL recovery events in {elapsed:.2f}s")
    print(f"  Features: level=CRITICAL, msg_length~350+, response_time=20000-30000ms")


def main():
    print(f"{SEPARATOR}")
    print("  ANOMALY INJECTION TOOL")
    print(f"  Kafka: {KAFKA_SERVERS}  |  Topic: {KAFKA_TOPIC}")
    print(f"{SEPARATOR}")

    producer = create_producer()

    scenario_sudden_burst(producer)
    print("\n  Waiting 3 seconds before next scenario...")
    time.sleep(3)

    scenario_error_spike(producer)
    print("\n  Waiting 3 seconds before next scenario...")
    time.sleep(3)

    scenario_silent_service(producer)

    producer.flush()
    producer.close()

    print(f"\n{SEPARATOR}")
    print("  ALL SCENARIOS COMPLETE")
    print(f"{SEPARATOR}")
    print()
    print("  Total injected: 100 anomalous events (50 + 30 + 20)")
    print("  Services affected: payments-service, orders-service, auth-service")
    print()
    print("  Pipeline flow:")
    print("    Kafka log-events → Spark → Anomaly Service → Kafka anomaly-alerts → Dashboard")
    print()
    print("  What to check:")
    print("    1. Anomaly Timeline panel — should show scored events within ~10-15 seconds")
    print("    2. Real-Time Alerts panel — should show live alerts via WebSocket")
    print("    3. docker compose logs anomaly-service — look for 'anomalies detected' lines")
    print()


if __name__ == "__main__":
    main()
