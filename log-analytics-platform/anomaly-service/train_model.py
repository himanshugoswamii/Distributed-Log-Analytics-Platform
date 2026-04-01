"""
Train an Isolation Forest model on simulated "normal" log data.
The model learns typical log patterns so it can flag anomalies in production.

Features extracted from each log event:
  1. log_level_encoded: ordinal encoding (INFO=0, WARN=1, ERROR=2, CRITICAL=3)
  2. message_length: character count of the log message
  3. response_time_ms: extracted from metadata
  4. hour_of_day: 0-23
  5. events_per_second: simulated throughput bucket

Run: python train_model.py
Output: model/isolation_forest.joblib
"""

import json
import os
import random
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib

SEED = 42
NUM_SAMPLES = 50000
MODEL_DIR = "model"
MODEL_PATH = os.path.join(MODEL_DIR, "isolation_forest.joblib")

LEVEL_MAP = {"INFO": 0, "WARN": 1, "ERROR": 2, "CRITICAL": 3}

random.seed(SEED)
np.random.seed(SEED)


def generate_normal_features(n: int) -> np.ndarray:
    """Generate feature vectors representing normal log behavior."""
    features = []
    for _ in range(n):
        # Normal distribution: mostly INFO/WARN logs
        level_weights = [0.70, 0.20, 0.08, 0.02]
        level = random.choices(list(LEVEL_MAP.values()), weights=level_weights, k=1)[0]

        msg_length = int(np.random.normal(80, 20))
        msg_length = max(10, min(msg_length, 300))

        # Normal response times: most under 200ms, some up to 500ms
        if level == 0:  # INFO
            response_time = abs(np.random.normal(50, 30))
        elif level == 1:  # WARN
            response_time = abs(np.random.normal(150, 50))
        elif level == 2:  # ERROR
            response_time = abs(np.random.normal(500, 200))
        else:  # CRITICAL
            response_time = abs(np.random.normal(1000, 400))

        hour = random.randint(0, 23)

        # Normal event rate: 80-120 events/sec per service
        eps = abs(np.random.normal(100, 15))

        features.append([level, msg_length, response_time, hour, eps])

    return np.array(features)


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)

    print(f"Generating {NUM_SAMPLES} normal training samples...")
    X_train = generate_normal_features(NUM_SAMPLES)

    print("Training Isolation Forest...")
    model = IsolationForest(
        n_estimators=200,
        max_samples="auto",
        contamination=0.05,
        max_features=1.0,
        random_state=SEED,
        n_jobs=-1,
    )
    model.fit(X_train)

    # Verify on training data
    scores = model.decision_function(X_train)
    predictions = model.predict(X_train)
    anomaly_rate = (predictions == -1).sum() / len(predictions)
    print(f"Training anomaly rate: {anomaly_rate:.2%}")
    print(f"Score range: [{scores.min():.4f}, {scores.max():.4f}]")

    joblib.dump(model, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
