"""
REST API — FastAPI query service for the log analytics platform.

Endpoints:
  GET  /logs              — filter by service_name, date, severity, time range
  GET  /logs/volume       — aggregated log counts for dashboard charts
  GET  /anomalies         — recent anomaly alerts
  GET  /services          — list known services
  WS   /ws/logs           — real-time log stream via WebSocket
  WS   /ws/anomalies      — real-time anomaly alert stream via WebSocket

Separate from the anomaly-service (which only does scoring).
Target: sub-200ms response times using Cassandra partition-key queries.
"""

import asyncio
import json
import os
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

CASSANDRA_HOST = os.environ.get("CASSANDRA_HOST", "cassandra")
CASSANDRA_PORT = int(os.environ.get("CASSANDRA_PORT", "9042"))
CASSANDRA_KEYSPACE = os.environ.get("CASSANDRA_KEYSPACE", "log_analytics")
ANOMALY_SERVICE_URL = os.environ.get("ANOMALY_SERVICE_URL", "http://anomaly-service:8001")
KAFKA_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

cassandra_session = None
ws_connections_logs: list[WebSocket] = []
ws_connections_anomalies: list[WebSocket] = []

# Thread-safe buffers for Kafka → WebSocket bridge
recent_logs: deque = deque(maxlen=200)
recent_alerts: deque = deque(maxlen=50)
_shutdown_event = threading.Event()

# Throughput tracking — counts every event the Kafka consumer sees
_throughput_counter = 0
_throughput_lock = threading.Lock()
_throughput_rate = 0  # computed events/sec


def connect_cassandra(retries=20):
    for attempt in range(1, retries + 1):
        try:
            cluster = Cluster(
                [CASSANDRA_HOST],
                port=CASSANDRA_PORT,
                load_balancing_policy=DCAwareRoundRobinPolicy(local_dc="dc1"),
                protocol_version=4,
            )
            session = cluster.connect(CASSANDRA_KEYSPACE)
            print(f"[API] Connected to Cassandra at {CASSANDRA_HOST}:{CASSANDRA_PORT}", flush=True)
            return session
        except Exception as e:
            print(f"[API] Cassandra not ready ({attempt}/{retries}): {e}", flush=True)
            time.sleep(5)
    raise RuntimeError("Failed to connect to Cassandra")


def _kafka_log_thread():
    """Blocking Kafka consumer running in a dedicated thread."""
    global _throughput_counter
    from kafka import KafkaConsumer
    from kafka.errors import NoBrokersAvailable

    time.sleep(5)
    consumer = None
    while not _shutdown_event.is_set():
        try:
            if consumer is None:
                consumer = KafkaConsumer(
                    "log-events",
                    bootstrap_servers=KAFKA_SERVERS.split(","),
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset="latest",
                    enable_auto_commit=True,
                    group_id="api-ws-logs",
                    consumer_timeout_ms=1000,
                )
                print("[API] Kafka log consumer connected", flush=True)
            for message in consumer:
                with _throughput_lock:
                    _throughput_counter += 1
                recent_logs.appendleft(message.value)
                if _shutdown_event.is_set():
                    break
        except NoBrokersAvailable:
            print("[API] Kafka not ready for log consumer, retrying...", flush=True)
            time.sleep(5)
        except Exception as e:
            print(f"[API] Kafka log consumer error: {e}", flush=True)
            consumer = None
            time.sleep(3)
    if consumer:
        consumer.close()


def _persist_anomaly_to_cassandra(alert):
    """Write an anomaly alert to Cassandra so GET /anomalies can return it."""
    if cassandra_session is None:
        return
    try:
        ts_str = alert.get("timestamp", "")
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        alert_date = ts.date()
        alert_id = UUID(alert["alert_id"])

        cql = (
            "INSERT INTO anomaly_alerts "
            "(service_name, alert_date, timestamp, alert_id, anomaly_score, "
            "log_level, message, metadata) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        )
        cassandra_session.execute(cql, [
            alert.get("service_name", "unknown"),
            alert_date,
            ts,
            alert_id,
            float(alert.get("anomaly_score", 0.0)),
            alert.get("log_level", "UNKNOWN"),
            alert.get("message", ""),
            alert.get("metadata", "{}"),
        ])
    except Exception as e:
        print(f"[API] Failed to persist anomaly to Cassandra: {e}", flush=True)


def _kafka_anomaly_thread():
    """Blocking Kafka consumer running in a dedicated thread."""
    from kafka import KafkaConsumer
    from kafka.errors import NoBrokersAvailable

    time.sleep(5)
    consumer = None
    while not _shutdown_event.is_set():
        try:
            if consumer is None:
                consumer = KafkaConsumer(
                    "anomaly-alerts",
                    bootstrap_servers=KAFKA_SERVERS.split(","),
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    auto_offset_reset="latest",
                    enable_auto_commit=True,
                    group_id="api-ws-anomalies",
                    consumer_timeout_ms=1000,
                )
                print("[API] Kafka anomaly consumer connected", flush=True)
            for message in consumer:
                alert = message.value
                recent_alerts.appendleft(alert)
                _persist_anomaly_to_cassandra(alert)
                if _shutdown_event.is_set():
                    break
        except NoBrokersAvailable:
            print("[API] Kafka not ready for anomaly consumer, retrying...", flush=True)
            time.sleep(5)
        except Exception as e:
            print(f"[API] Kafka anomaly consumer error: {e}", flush=True)
            consumer = None
            time.sleep(3)
    if consumer:
        consumer.close()


def _throughput_tracker_thread():
    """Computes events/sec every second from the raw counter."""
    global _throughput_counter, _throughput_rate
    while not _shutdown_event.is_set():
        with _throughput_lock:
            snapshot = _throughput_counter
            _throughput_counter = 0
        _throughput_rate = snapshot
        time.sleep(1)


async def _ws_broadcaster():
    """Async task that reads from thread-safe deques and pushes to WebSocket clients."""
    log_cursor = 0
    alert_cursor = 0
    while True:
        # Push new log events to WebSocket clients
        while len(recent_logs) > 0 and log_cursor < len(recent_logs):
            try:
                event = recent_logs[0]
            except IndexError:
                break
            dead = []
            for ws in ws_connections_logs:
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in ws_connections_logs:
                    ws_connections_logs.remove(ws)
            # Pop the sent item
            try:
                recent_logs.pop()
            except IndexError:
                pass
            break

        # Push new anomaly alerts to WebSocket clients
        while len(recent_alerts) > 0:
            try:
                alert = recent_alerts.pop()
            except IndexError:
                break
            dead = []
            for ws in ws_connections_anomalies:
                try:
                    await ws.send_json(alert)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in ws_connections_anomalies:
                    ws_connections_anomalies.remove(ws)

        await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cassandra_session
    cassandra_session = await asyncio.to_thread(connect_cassandra)

    log_thread = threading.Thread(target=_kafka_log_thread, daemon=True)
    anomaly_thread = threading.Thread(target=_kafka_anomaly_thread, daemon=True)
    throughput_thread = threading.Thread(target=_throughput_tracker_thread, daemon=True)
    log_thread.start()
    anomaly_thread.start()
    throughput_thread.start()

    broadcaster_task = asyncio.create_task(_ws_broadcaster())

    print("[API] REST API started successfully", flush=True)
    yield

    _shutdown_event.set()
    broadcaster_task.cancel()


app = FastAPI(
    title="Log Analytics REST API",
    description="Query logs, anomalies, and real-time streams",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "cassandra": cassandra_session is not None,
    }


@app.get("/throughput")
async def throughput():
    """Real-time system throughput measured from the Kafka consumer."""
    return {
        "events_per_second": _throughput_rate,
    }


@app.get("/logs")
async def get_logs(
    service_name: str = Query(..., description="Service name"),
    log_date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to today"),
    severity: Optional[str] = Query(None, description="Filter by log level"),
    start_time: Optional[str] = Query(None, description="Start time ISO format"),
    end_time: Optional[str] = Query(None, description="End time ISO format"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Query logs by service, date, severity, and time range. Uses partition key for sub-200ms reads."""
    t0 = time.monotonic()

    if log_date:
        query_date = log_date
    else:
        query_date = date.today().isoformat()

    if severity:
        cql = (
            "SELECT log_level, log_date, timestamp, log_id, service_name, message, metadata "
            "FROM logs_by_severity WHERE log_level = %s AND log_date = %s LIMIT %s"
        )
        params = [severity.upper(), query_date, limit]
        stmt = SimpleStatement(cql, fetch_size=limit)
        rows = await asyncio.to_thread(cassandra_session.execute, stmt, params)
        results = []
        for row in rows:
            if row.service_name == service_name:
                results.append(_row_to_dict(row))
                if len(results) >= limit:
                    break
    else:
        cql = (
            "SELECT service_name, log_date, timestamp, log_id, log_level, message, metadata "
            "FROM logs WHERE service_name = %s AND log_date = %s"
        )
        params = [service_name, query_date]

        if start_time and end_time:
            cql += " AND timestamp >= %s AND timestamp <= %s"
            params.extend([start_time, end_time])
        elif start_time:
            cql += " AND timestamp >= %s"
            params.append(start_time)
        elif end_time:
            cql += " AND timestamp <= %s"
            params.append(end_time)

        cql += f" LIMIT {limit}"
        stmt = SimpleStatement(cql, fetch_size=limit)
        rows = await asyncio.to_thread(cassandra_session.execute, stmt, params)
        results = [_row_to_dict(row) for row in rows]

    elapsed_ms = (time.monotonic() - t0) * 1000
    return {
        "count": len(results),
        "query_time_ms": round(elapsed_ms, 2),
        "logs": results,
    }


@app.get("/logs/volume")
async def get_log_volume(
    service_name: str = Query(...),
    log_date: Optional[str] = Query(None),
    hours: int = Query(6, ge=1, le=48),
):
    """Get log volume trends for dashboard visualization."""
    if not log_date:
        log_date = date.today().isoformat()

    cql = (
        "SELECT service_name, log_date, timestamp, log_level "
        "FROM logs WHERE service_name = %s AND log_date = %s LIMIT 10000"
    )
    stmt = SimpleStatement(cql, fetch_size=5000)
    rows = await asyncio.to_thread(cassandra_session.execute, stmt, [service_name, log_date])

    volume = {}
    severity_counts = {"INFO": 0, "WARN": 0, "ERROR": 0, "CRITICAL": 0}
    for row in rows:
        minute_key = row.timestamp.strftime("%Y-%m-%d %H:%M") if row.timestamp else "unknown"
        volume[minute_key] = volume.get(minute_key, 0) + 1
        if row.log_level in severity_counts:
            severity_counts[row.log_level] += 1

    sorted_volume = [{"minute": k, "count": v} for k, v in sorted(volume.items())]

    return {
        "service_name": service_name,
        "log_date": log_date,
        "volume": sorted_volume[-360:],
        "severity_distribution": severity_counts,
    }


@app.get("/anomalies")
async def get_anomalies(
    service_name: Optional[str] = Query(None),
    log_date: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Get recent anomaly alerts."""
    if not log_date:
        log_date = date.today().isoformat()

    if service_name:
        cql = (
            "SELECT service_name, alert_date, timestamp, alert_id, anomaly_score, "
            "log_level, message, metadata FROM anomaly_alerts "
            "WHERE service_name = %s AND alert_date = %s LIMIT %s"
        )
        params = [service_name, log_date, limit]
        rows = await asyncio.to_thread(cassandra_session.execute, SimpleStatement(cql, fetch_size=limit), params)
        results = [_alert_to_dict(r) for r in rows]
    else:
        services = _get_known_services()
        all_alerts = []
        for svc in services:
            cql = (
                "SELECT service_name, alert_date, timestamp, alert_id, anomaly_score, "
                "log_level, message, metadata FROM anomaly_alerts "
                "WHERE service_name = %s AND alert_date = %s LIMIT %s"
            )
            rows = await asyncio.to_thread(
                cassandra_session.execute,
                SimpleStatement(cql, fetch_size=limit), [svc, log_date, limit]
            )
            all_alerts.extend([_alert_to_dict(r) for r in rows])
        all_alerts.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return {"count": len(all_alerts[:limit]), "anomalies": all_alerts[:limit]}

    return {"count": len(results), "anomalies": results}


@app.get("/services")
async def list_services():
    """List known services (the 10 simulator service names)."""
    return {
        "services": _get_known_services()
    }


@app.get("/anomaly-service/health")
async def anomaly_service_proxy_health():
    """Proxy health check to the anomaly detection service."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{ANOMALY_SERVICE_URL}/health", timeout=5.0)
            return resp.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}


# ── WebSocket endpoints ──────────────────────────────────

@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    ws_connections_logs.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ws_connections_logs:
            ws_connections_logs.remove(websocket)


@app.websocket("/ws/anomalies")
async def ws_anomalies(websocket: WebSocket):
    await websocket.accept()
    ws_connections_anomalies.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ws_connections_anomalies:
            ws_connections_anomalies.remove(websocket)


# ── Helpers ──────────────────────────────────────────────

def _get_known_services():
    return [
        "auth-service", "payments-service", "orders-service",
        "inventory-service", "users-service", "notifications-service",
        "gateway-service", "search-service", "analytics-service",
        "email-service",
    ]


def _row_to_dict(row):
    return {
        "service_name": getattr(row, "service_name", None),
        "log_date": str(getattr(row, "log_date", "")),
        "timestamp": str(getattr(row, "timestamp", "")),
        "log_id": str(getattr(row, "log_id", "")),
        "log_level": getattr(row, "log_level", None),
        "message": getattr(row, "message", None),
        "metadata": getattr(row, "metadata", None),
    }


def _alert_to_dict(row):
    return {
        "service_name": getattr(row, "service_name", None),
        "alert_date": str(getattr(row, "alert_date", "")),
        "timestamp": str(getattr(row, "timestamp", "")),
        "alert_id": str(getattr(row, "alert_id", "")),
        "anomaly_score": getattr(row, "anomaly_score", None),
        "log_level": getattr(row, "log_level", None),
        "message": getattr(row, "message", None),
        "metadata": getattr(row, "metadata", None),
    }
