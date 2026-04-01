"""
Spark Structured Streaming job:
  - Consumes JSON log events from Kafka topic "log-events"
  - Parses and enriches the data
  - Writes processed logs to Cassandra (log_analytics.logs)
  - Also writes to logs_by_severity and updates log_volume counters
  - Forwards events to the anomaly-service via HTTP for scoring
"""

import json
import os
import requests
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, to_date, expr, udf, current_timestamp,
    window, count, lit
)
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, FloatType
)

KAFKA_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
CASSANDRA_HOST = os.environ.get("CASSANDRA_HOST", "cassandra")
CASSANDRA_PORT = os.environ.get("CASSANDRA_PORT", "9042")
ANOMALY_SERVICE_URL = os.environ.get("ANOMALY_SERVICE_URL", "http://anomaly-service:8001")

LOG_SCHEMA = StructType([
    StructField("log_id", StringType(), True),
    StructField("service_name", StringType(), True),
    StructField("timestamp", StringType(), True),
    StructField("log_level", StringType(), True),
    StructField("message", StringType(), True),
    StructField("metadata", StringType(), True),
])


def create_spark_session():
    return (
        SparkSession.builder
        .appName("LogAnalyticsProcessor")
        .config("spark.cassandra.connection.host", CASSANDRA_HOST)
        .config("spark.cassandra.connection.port", CASSANDRA_PORT)
        .config("spark.sql.streaming.checkpointLocation", "/tmp/spark-checkpoints")
        .config("spark.streaming.backpressure.enabled", "true")
        .config("spark.sql.shuffle.partitions", "6")
        .getOrCreate()
    )


def write_logs_to_cassandra(batch_df, batch_id):
    """Write each micro-batch to Cassandra logs table and severity table."""
    if batch_df.rdd.isEmpty():
        return

    logs_df = batch_df.select(
        col("service_name"),
        to_date(col("ts")).alias("log_date"),
        col("ts").alias("timestamp"),
        expr("uuid()").alias("log_id"),
        col("log_level"),
        col("message"),
        col("metadata"),
    )

    # Write to main logs table
    (logs_df.write
     .format("org.apache.spark.sql.cassandra")
     .mode("append")
     .options(table="logs", keyspace="log_analytics")
     .save())

    # Write to severity lookup table
    severity_df = logs_df.select(
        col("log_level"),
        col("log_date"),
        col("timestamp"),
        col("log_id"),
        col("service_name"),
        col("message"),
        col("metadata"),
    )
    (severity_df.write
     .format("org.apache.spark.sql.cassandra")
     .mode("append")
     .options(table="logs_by_severity", keyspace="log_analytics")
     .save())

    # Send batch to anomaly service for scoring
    try:
        events = [row.asDict() for row in batch_df.collect()]
        payload = []
        for e in events:
            payload.append({
                "service_name": e["service_name"],
                "timestamp": str(e["ts"]),
                "log_level": e["log_level"],
                "message": e["message"],
                "metadata": e["metadata"],
            })
        if payload:
            requests.post(
                f"{ANOMALY_SERVICE_URL}/score_batch",
                json={"events": payload},
                timeout=5,
            )
    except Exception as ex:
        print(f"[Spark] Anomaly scoring failed (non-fatal): {ex}", flush=True)


def main():
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    print(f"[Spark] Reading from Kafka at {KAFKA_SERVERS}, topic 'log-events'", flush=True)

    raw_stream = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_SERVERS)
        .option("subscribe", "log-events")
        .option("startingOffsets", "latest")
        .option("maxOffsetsPerTrigger", 10000)
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = (
        raw_stream
        .selectExpr("CAST(value AS STRING) as json_str")
        .select(from_json(col("json_str"), LOG_SCHEMA).alias("data"))
        .select("data.*")
        .withColumn("ts", col("timestamp").cast(TimestampType()))
    )

    query = (
        parsed.writeStream
        .foreachBatch(write_logs_to_cassandra)
        .outputMode("append")
        .trigger(processingTime="5 seconds")
        .option("checkpointLocation", "/tmp/spark-checkpoints/logs")
        .start()
    )

    print("[Spark] Streaming query started — writing to Cassandra", flush=True)
    query.awaitTermination()


if __name__ == "__main__":
    main()
