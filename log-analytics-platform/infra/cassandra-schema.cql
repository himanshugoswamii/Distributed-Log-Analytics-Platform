-- Keyspace with SimpleStrategy for single-node dev; switch to NetworkTopologyStrategy for production
CREATE KEYSPACE IF NOT EXISTS log_analytics
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE log_analytics;

-- Primary log table: composite partition key (service_name, log_date) for time-series optimization.
-- Clustering on timestamp DESC gives most-recent-first reads within a partition.
CREATE TABLE IF NOT EXISTS logs (
    service_name text,
    log_date     date,
    timestamp    timestamp,
    log_id       uuid,
    log_level    text,
    message      text,
    metadata     text,
    PRIMARY KEY ((service_name, log_date), timestamp, log_id)
) WITH CLUSTERING ORDER BY (timestamp DESC, log_id ASC)
  AND compaction = {'class': 'TimeWindowCompactionStrategy', 'compaction_window_size': 1, 'compaction_window_unit': 'DAYS'}
  AND default_time_to_live = 604800;  -- 7-day TTL

-- Anomaly alerts detected by isolation forest
CREATE TABLE IF NOT EXISTS anomaly_alerts (
    service_name text,
    alert_date   date,
    timestamp    timestamp,
    alert_id     uuid,
    anomaly_score float,
    log_level    text,
    message      text,
    metadata     text,
    PRIMARY KEY ((service_name, alert_date), timestamp, alert_id)
) WITH CLUSTERING ORDER BY (timestamp DESC, alert_id ASC)
  AND default_time_to_live = 2592000;  -- 30-day TTL

-- Materialized view for filtering by severity across all services on a given date
CREATE TABLE IF NOT EXISTS logs_by_severity (
    log_level    text,
    log_date     date,
    timestamp    timestamp,
    log_id       uuid,
    service_name text,
    message      text,
    metadata     text,
    PRIMARY KEY ((log_level, log_date), timestamp, log_id)
) WITH CLUSTERING ORDER BY (timestamp DESC, log_id ASC)
  AND default_time_to_live = 604800;

-- Aggregated log volume per service per minute for dashboard trends
CREATE TABLE IF NOT EXISTS log_volume (
    service_name text,
    log_date     date,
    minute       timestamp,
    count        counter,
    PRIMARY KEY ((service_name, log_date), minute)
) WITH CLUSTERING ORDER BY (minute DESC);
