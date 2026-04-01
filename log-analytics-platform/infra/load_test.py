"""
Load test script to verify:
  1. Simulator throughput reaches 1,000+ events/sec combined
  2. REST API responds in sub-200ms
  3. Anomaly service is responsive

Usage: python infra/load_test.py
Requirements: pip install requests kafka-python
"""

import json
import sys
import time
import statistics
import requests
from kafka import KafkaConsumer, TopicPartition

API_URL = "http://localhost:8000"
ANOMALY_URL = "http://localhost:8001"
KAFKA_SERVERS = "localhost:29092"

SERVICES = [
    "auth-service", "payments-service", "orders-service",
    "inventory-service", "users-service", "notifications-service",
    "gateway-service", "search-service", "analytics-service",
    "email-service",
]


def test_kafka_throughput(duration_sec=10):
    print(f"\n{'='*60}")
    print(f" KAFKA THROUGHPUT TEST ({duration_sec}s measurement window)")
    print(f"{'='*60}")

    consumer = KafkaConsumer(
        bootstrap_servers=[KAFKA_SERVERS],
        auto_offset_reset="latest",
        enable_auto_commit=False,
        consumer_timeout_ms=1000,
    )

    partitions = consumer.partitions_for_topic("log-events")
    if not partitions:
        print("ERROR: Topic 'log-events' not found")
        return False

    tps = [TopicPartition("log-events", p) for p in partitions]
    consumer.assign(tps)

    # Get initial offsets
    end_offsets_start = consumer.end_offsets(tps)
    total_start = sum(end_offsets_start.values())

    print(f"  Partitions: {len(partitions)}")
    print(f"  Starting offset total: {total_start}")
    print(f"  Measuring for {duration_sec} seconds...")

    time.sleep(duration_sec)

    end_offsets_end = consumer.end_offsets(tps)
    total_end = sum(end_offsets_end.values())
    consumer.close()

    messages_produced = total_end - total_start
    rate = messages_produced / duration_sec

    print(f"  Ending offset total: {total_end}")
    print(f"  Messages produced: {messages_produced}")
    print(f"  Throughput: {rate:.0f} events/sec")

    passed = rate >= 1000
    print(f"  Result: {'PASS' if passed else 'FAIL'} (target: >= 1,000 events/sec)")
    return passed


def test_api_latency(num_requests=30):
    print(f"\n{'='*60}")
    print(f" REST API LATENCY TEST ({num_requests} requests)")
    print(f"{'='*60}")

    latencies = []
    errors = 0

    for service in SERVICES[:3]:
        for _ in range(num_requests // 3):
            try:
                start = time.monotonic()
                resp = requests.get(
                    f"{API_URL}/logs",
                    params={"service_name": service, "limit": 100},
                    timeout=5,
                )
                elapsed = (time.monotonic() - start) * 1000
                if resp.status_code == 200:
                    latencies.append(elapsed)
                    data = resp.json()
                    reported_time = data.get("query_time_ms", 0)
                else:
                    errors += 1
            except Exception as e:
                errors += 1

    if latencies:
        avg = statistics.mean(latencies)
        p50 = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        max_lat = max(latencies)

        print(f"  Successful requests: {len(latencies)}")
        print(f"  Errors: {errors}")
        print(f"  Average latency: {avg:.1f} ms")
        print(f"  P50 latency:     {p50:.1f} ms")
        print(f"  P95 latency:     {p95:.1f} ms")
        print(f"  P99 latency:     {p99:.1f} ms")
        print(f"  Max latency:     {max_lat:.1f} ms")

        passed = p95 < 200
        print(f"  Result: {'PASS' if passed else 'FAIL'} (target: P95 < 200ms)")
        return passed
    else:
        print(f"  No successful requests (errors: {errors})")
        return False


def test_anomaly_service():
    print(f"\n{'='*60}")
    print(f" ANOMALY SERVICE TEST")
    print(f"{'='*60}")

    try:
        health = requests.get(f"{ANOMALY_URL}/health", timeout=5)
        print(f"  Health: {health.json()}")
    except Exception as e:
        print(f"  Health check failed: {e}")
        return False

    test_event = {
        "service_name": "auth-service",
        "timestamp": "2024-01-01T12:00:00Z",
        "log_level": "ERROR",
        "message": "Authentication failed: invalid credentials for usr_9999",
        "metadata": json.dumps({"response_time_ms": 5000, "host": "auth-1"}),
    }

    try:
        start = time.monotonic()
        resp = requests.post(f"{ANOMALY_URL}/score", json=test_event, timeout=5)
        elapsed = (time.monotonic() - start) * 1000
        result = resp.json()

        print(f"  Single score latency: {elapsed:.1f} ms")
        print(f"  Anomaly score: {result.get('anomaly_score', 'N/A')}")
        print(f"  Is anomaly: {result.get('is_anomaly', 'N/A')}")

        # Batch test
        batch = {"events": [test_event] * 50}
        start = time.monotonic()
        resp = requests.post(f"{ANOMALY_URL}/score_batch", json=batch, timeout=10)
        elapsed = (time.monotonic() - start) * 1000
        print(f"  Batch (50 events) latency: {elapsed:.1f} ms")

        print(f"  Result: PASS")
        return True
    except Exception as e:
        print(f"  Scoring failed: {e}")
        return False


def test_volume_endpoint():
    print(f"\n{'='*60}")
    print(f" LOG VOLUME ENDPOINT TEST")
    print(f"{'='*60}")

    try:
        start = time.monotonic()
        resp = requests.get(
            f"{API_URL}/logs/volume",
            params={"service_name": "auth-service"},
            timeout=5,
        )
        elapsed = (time.monotonic() - start) * 1000
        data = resp.json()

        print(f"  Latency: {elapsed:.1f} ms")
        print(f"  Volume data points: {len(data.get('volume', []))}")
        print(f"  Severity dist: {data.get('severity_distribution', {})}")
        print(f"  Result: PASS")
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print(" DISTRIBUTED LOG ANALYTICS PLATFORM — LOAD TEST")
    print("=" * 60)

    results = {}

    results["Kafka throughput"] = test_kafka_throughput()
    results["API latency"] = test_api_latency()
    results["Anomaly service"] = test_anomaly_service()
    results["Volume endpoint"] = test_volume_endpoint()

    print(f"\n{'='*60}")
    print(" SUMMARY")
    print(f"{'='*60}")
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test_name}")

    all_passed = all(results.values())
    print(f"\n  Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
