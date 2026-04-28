"""
Anomaly Detection Microservice — FastAPI + Isolation Forest.

Runs as a completely independent container. Accepts log events via HTTP,
scores them with the pre-trained Isolation Forest model, and publishes
anomaly alerts to Kafka topic "anomaly-alerts".
"""

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from pydantic import BaseModel

MODEL_PATH = os.environ.get("MODEL_PATH", "model/isolation_forest.joblib")
KAFKA_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
ANOMALY_TOPIC = "anomaly-alerts"
SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "-0.15"))

LEVEL_MAP = {"INFO": 0, "WARN": 1, "ERROR": 2, "CRITICAL": 3}

model = None
kafka_producer = None


def init_kafka_producer(retries=15):
    for attempt in range(1, retries + 1):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_SERVERS.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
            print(f"[Anomaly] Kafka producer connected", flush=True)
            return producer
        except NoBrokersAvailable:
            print(f"[Anomaly] Kafka not ready ({attempt}/{retries}), retrying...", flush=True)
            time.sleep(3)
    print("[Anomaly] WARNING: Kafka unavailable — alerts won't be published", flush=True)
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, kafka_producer
    print(f"[Anomaly] Loading model from {MODEL_PATH}", flush=True)
    if os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
        print("[Anomaly] Model loaded successfully", flush=True)
    else:
        print(f"[Anomaly] WARNING: Model not found at {MODEL_PATH}, will return neutral scores", flush=True)
    kafka_producer = init_kafka_producer()
    yield
    if kafka_producer:
        kafka_producer.flush()
        kafka_producer.close()


app = FastAPI(
    title="Anomaly Detection Service",
    description="Isolation Forest-based log anomaly detection",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LogEvent(BaseModel):
    service_name: str
    timestamp: str
    log_level: str
    message: str
    metadata: Optional[str] = "{}"


class BatchRequest(BaseModel):
    events: list[LogEvent]


class AnomalyResult(BaseModel):
    log_event: LogEvent
    anomaly_score: float
    is_anomaly: bool


def extract_features(event: LogEvent) -> np.ndarray:
    level_code = LEVEL_MAP.get(event.log_level.upper(), 0)
    msg_length = len(event.message)

    try:
        meta = json.loads(event.metadata) if event.metadata else {}
        response_time = meta.get("response_time_ms", 50)
    except (json.JSONDecodeError, TypeError):
        response_time = 50

    try:
        ts = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        hour = ts.hour
    except (ValueError, AttributeError):
        hour = 12

    eps = 100  # default assumed rate

    return np.array([[level_code, msg_length, response_time, hour, eps]])


def score_event(event: LogEvent) -> AnomalyResult:
    if model is None:
        return AnomalyResult(log_event=event, anomaly_score=0.0, is_anomaly=False)

    features = extract_features(event)
    score = float(model.decision_function(features)[0])
    is_anomaly = score < SCORE_THRESHOLD

    if is_anomaly and kafka_producer:
        alert = {
            "alert_id": str(uuid4()),
            "service_name": event.service_name,
            "timestamp": event.timestamp,
            "anomaly_score": score,
            "log_level": event.log_level,
            "message": event.message,
            "metadata": event.metadata,
        }
        try:
            kafka_producer.send(ANOMALY_TOPIC, value=alert)
        except Exception:
            pass

    return AnomalyResult(log_event=event, anomaly_score=score, is_anomaly=is_anomaly)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "kafka_connected": kafka_producer is not None,
    }


@app.post("/score", response_model=AnomalyResult)
async def score_single(event: LogEvent):
    return score_event(event)


@app.post("/score_batch", response_model=list[AnomalyResult])
async def score_batch(request: BatchRequest):
    results = []
    anomaly_count = 0
    for event in request.events:
        result = score_event(event)
        results.append(result)
        if result.is_anomaly:
            anomaly_count += 1

    if anomaly_count > 0:
        print(
            f"[Anomaly] Batch: {len(request.events)} events, {anomaly_count} anomalies detected",
            flush=True,
        )
    return results


@app.get("/model/info")
async def model_info():
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "type": "IsolationForest",
        "n_estimators": model.n_estimators,
        "max_samples": model.max_samples,
        "contamination": model.contamination,
        "threshold": SCORE_THRESHOLD,
        "features": [
            "log_level_encoded",
            "message_length",
            "response_time_ms",
            "hour_of_day",
            "events_per_second",
        ],
    }
