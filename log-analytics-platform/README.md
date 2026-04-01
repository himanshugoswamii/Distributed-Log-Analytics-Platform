# Distributed Log Analytics Platform

A production-grade distributed log analytics system that ingests, processes, stores, and visualizes structured log events from 10 microservice simulators at 1,000+ events/sec throughput.

## Architecture

```
┌─────────────────────┐
│  10 Log Simulators  │  (Python, 100-120 events/sec each)
│  auth, payments,    │
│  orders, inventory, │
│  users, notifs,     │
│  gateway, search,   │
│  analytics, email   │
└────────┬────────────┘
         │ Kafka Producer (lz4 compressed, batched)
         ▼
┌─────────────────────┐
│   Apache Kafka      │  Topic: "log-events" (6 partitions)
│   + Zookeeper       │  Topic: "anomaly-alerts" (3 partitions)
└────┬───────────┬────┘
     │           │
     ▼           ▼
┌─────────┐  ┌──────────────────┐
│  Spark  │  │ Anomaly Service  │  (Independent FastAPI container)
│  Struct │  │ Isolation Forest │
│ Stream  │  │ scikit-learn     │
└────┬────┘  └──────────────────┘
     │         ▲ HTTP POST /score_batch
     │         │ (from Spark foreachBatch)
     ▼
┌─────────────────────┐
│  Apache Cassandra   │  Partition key: (service_name, date)
│  log_analytics      │  TimeWindowCompactionStrategy
│  keyspace           │  7-day TTL on logs, 30-day on alerts
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  REST API (FastAPI)  │  Sub-200ms queries via partition key
│  Port 8000          │  WebSocket streams for real-time
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  React Dashboard    │  Real-time alerts, volume trends,
│  Port 3000          │  anomaly spike visualization
└─────────────────────┘
```

## Quick Start

```bash
# Clone and start the entire stack
cd log-analytics-platform
docker-compose up --build

# Wait ~90 seconds for all services to initialize:
#   Zookeeper → Kafka → Cassandra → Schema init → Simulators → Spark → API → Dashboard

# Access points:
#   Dashboard:        http://localhost:3000
#   REST API:         http://localhost:8000/docs
#   Anomaly Service:  http://localhost:8001/docs
#   Spark UI:         http://localhost:8080
```

## Architecture Decisions

### Why Kafka over REST ingestion?

1. **Decoupling**: Producers and consumers operate independently. Simulators don't need to know about Spark or Cassandra.
2. **Backpressure handling**: At 1,000+ events/sec, direct REST would require the receiving service to keep up in real time. Kafka buffers bursts and allows consumers to process at their own pace.
3. **Replay capability**: Kafka retains messages (24h by default). If Spark crashes, it resumes from its last committed offset — zero data loss.
4. **Fan-out**: Multiple consumers (Spark, Anomaly Service, API WebSocket) can independently read from the same topic without duplicating ingestion logic.
5. **Ordering guarantees**: Partitioning by service_name ensures per-service ordering while enabling parallel consumption across partitions.

### Why Cassandra over PostgreSQL?

1. **Write throughput**: Cassandra handles 1,000+ writes/sec on a single node with minimal latency. PostgreSQL would require write-ahead log flushing, MVCC overhead, and index updates that bottleneck at this rate.
2. **Partition key design**: The composite key `(service_name, date)` gives O(1) partition lookups. Each partition contains one service's logs for one day — exactly the query pattern the dashboard needs.
3. **Time-series optimization**: `TimeWindowCompactionStrategy` is purpose-built for time-series data. It groups SSTables by time window and drops expired data without full compaction.
4. **TTL**: Built-in TTL (7 days for logs, 30 days for alerts) automatically expires old data with zero application logic.
5. **Horizontal scaling**: Adding nodes scales linearly. PostgreSQL would require sharding extensions (Citus) or application-level partitioning.
6. **Clustering order**: `CLUSTERING ORDER BY (timestamp DESC)` means "latest logs first" queries require no sorting — they read sequentially from the start of the partition.

### Why is the Anomaly Service isolated?

1. **Independent scaling**: Anomaly detection is CPU-bound (Isolation Forest scoring). Isolating it means you can scale it horizontally without affecting log ingestion or query serving.
2. **Model lifecycle**: The ML model can be retrained and redeployed independently. Rolling updates to the anomaly model don't require restarting the API or Spark.
3. **Failure isolation**: If the anomaly service crashes or overloads, log ingestion and querying continue uninterrupted. Spark catches the HTTP error and continues processing.
4. **Technology flexibility**: The anomaly service could be replaced with a different ML framework (PyTorch, TensorFlow) or a cloud ML service without touching any other component.
5. **Resource isolation**: scikit-learn's Isolation Forest uses NumPy operations that benefit from dedicated CPU/memory allocation without competing with JVM-based Spark or Cassandra.

## Project Structure

```
/log-analytics-platform
  /simulators             # 10 microservice log producers
    simulator.py          # Configurable log event generator
    Dockerfile
    requirements.txt
  /kafka                  # Kafka configuration references
    producer_config.py    # Shared producer settings
    consumer_config.py    # Shared consumer settings
  /spark-processor        # Spark Structured Streaming job
    processor.py          # Kafka → Cassandra pipeline + anomaly scoring
    Dockerfile
  /anomaly-service        # Isolation Forest FastAPI microservice
    app.py                # FastAPI scoring endpoints
    train_model.py        # Model training on simulated normal data
    Dockerfile
    requirements.txt
  /api                    # Query REST API
    app.py                # FastAPI with Cassandra queries + WebSocket
    Dockerfile
    requirements.txt
  /dashboard              # React frontend
    src/
      App.js              # Main dashboard layout
      api.js              # REST + WebSocket client
      components/         # Header, StatsBar, Charts, LogTable, AlertPanel
    Dockerfile
    nginx.conf
  /infra                  # Infrastructure configs
    cassandra-schema.cql  # Keyspace + table definitions
    cassandra-init.sh
    docker-compose.yml    # Full stack orchestration (alternate location)
  docker-compose.yml      # Root-level compose file
  README.md
```

## Cassandra Schema

The schema uses a composite partition key `(service_name, log_date)` optimized for the most common query pattern: "show me logs for service X on date Y".

| Table | Partition Key | Clustering | Purpose |
|-------|-------------|------------|---------|
| `logs` | `(service_name, log_date)` | `timestamp DESC, log_id` | Primary log storage |
| `logs_by_severity` | `(log_level, log_date)` | `timestamp DESC, log_id` | Severity-filtered queries |
| `anomaly_alerts` | `(service_name, alert_date)` | `timestamp DESC, alert_id` | Detected anomalies |
| `log_volume` | `(service_name, log_date)` | `minute DESC` | Aggregated counters for trends |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/logs?service_name=...&log_date=...&severity=...&limit=100` | Query logs |
| `GET` | `/logs/volume?service_name=...` | Log volume trends |
| `GET` | `/anomalies?service_name=...` | Anomaly alerts |
| `GET` | `/services` | List all services |
| `GET` | `/health` | API health check |
| `WS` | `/ws/logs` | Real-time log stream |
| `WS` | `/ws/anomalies` | Real-time anomaly alerts |

### Anomaly Service Endpoints (port 8001)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/score` | Score single log event |
| `POST` | `/score_batch` | Score batch of events |
| `GET` | `/model/info` | Model metadata |
| `GET` | `/health` | Service health |

## Load Testing

### Verify 1,000+ events/sec throughput

```bash
# Start the stack
docker-compose up --build -d

# Wait for initialization
sleep 90

# Check simulator throughput via Kafka consumer group lag
docker exec kafka kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --group spark-log-processor

# Direct throughput measurement: count messages produced in 10 seconds
docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 --topic log-events --time -1

# Wait 10 seconds, then run again and compute the difference
sleep 10

docker exec kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 --topic log-events --time -1

# The difference divided by 10 = events/sec (target: 1,000+)
# Expected: ~1,020 events/sec (sum of all 10 simulators)
```

### Verify sub-200ms API response

```bash
# Query logs for a specific service
curl -w "\n%{time_total}s\n" \
  "http://localhost:8000/logs?service_name=auth-service&limit=100"

# Benchmark with repeated requests
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{time_total}\n" \
    "http://localhost:8000/logs?service_name=auth-service&limit=100"
done | awk '{sum+=$1; count++} END {print "Average:", sum/count*1000, "ms"}'
```

### Run the Python load test script

```bash
python infra/load_test.py
```

## Deployment (AWS EC2 / DigitalOcean)

### Minimum Requirements
- 4 vCPUs, 8 GB RAM (for all services on single node)
- 50 GB SSD storage
- Docker and Docker Compose installed

### Steps
```bash
# On the server:
sudo apt update && sudo apt install -y docker.io docker-compose
git clone <repo-url> && cd log-analytics-platform

# Production environment variables
export CASSANDRA_HEAP=1G
export SPARK_WORKER_MEMORY=2G

# Start the stack
docker-compose up --build -d

# Verify all containers are running
docker-compose ps

# Open firewall ports:
#   3000 (dashboard), 8000 (API), 8001 (anomaly service)
```

### Production Considerations
- Use `NetworkTopologyStrategy` with RF=3 for Cassandra
- Add Kafka replication factor of 3 for fault tolerance
- Put nginx/ALB in front of the API for TLS termination
- Set up Prometheus + Grafana for infrastructure monitoring
- Configure log rotation for Docker container logs
