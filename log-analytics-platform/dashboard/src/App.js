import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchLogs, fetchLogVolume, fetchAnomalies, fetchServices,
  fetchThroughput, createLogWebSocket, createAnomalyWebSocket,
} from './api';
import Header from './components/Header';
import StatsBar from './components/StatsBar';
import VolumeChart from './components/VolumeChart';
import SeverityChart from './components/SeverityChart';
import AnomalyTimeline from './components/AnomalyTimeline';
import LogTable from './components/LogTable';
import AlertPanel from './components/AlertPanel';
import './App.css';

const SERVICES = [
  'auth-service', 'payments-service', 'orders-service',
  'inventory-service', 'users-service', 'notifications-service',
  'gateway-service', 'search-service', 'analytics-service',
  'email-service',
];

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

export default function App() {
  const [selectedService, setSelectedService] = useState(SERVICES[0]);
  const [selectedDate, setSelectedDate] = useState(todayStr());
  const [severityFilter, setSeverityFilter] = useState('');
  const [logs, setLogs] = useState([]);
  const [volume, setVolume] = useState([]);
  const [severityDist, setSeverityDist] = useState({});
  const [anomalies, setAnomalies] = useState([]);
  const [realtimeLogs, setRealtimeLogs] = useState([]);
  const [realtimeAlerts, setRealtimeAlerts] = useState([]);
  const [queryTime, setQueryTime] = useState(0);
  const [connected, setConnected] = useState(false);
  const [eventRate, setEventRate] = useState(0);

  const loadData = useCallback(async () => {
    try {
      const [logRes, volRes, anomRes] = await Promise.all([
        fetchLogs(selectedService, selectedDate, severityFilter || undefined),
        fetchLogVolume(selectedService, selectedDate),
        fetchAnomalies(selectedService, selectedDate),
      ]);
      setLogs(logRes.logs || []);
      setQueryTime(logRes.query_time_ms || 0);
      setVolume(volRes.volume || []);
      setSeverityDist(volRes.severity_distribution || {});
      setAnomalies(anomRes.anomalies || []);
      setConnected(true);
    } catch {
      setConnected(false);
    }
  }, [selectedService, selectedDate, severityFilter]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  useEffect(() => {
    const logWs = createLogWebSocket((event) => {
      setRealtimeLogs((prev) => [event, ...prev].slice(0, 200));
    });

    const anomalyWs = createAnomalyWebSocket((alert) => {
      setRealtimeAlerts((prev) => [alert, ...prev].slice(0, 50));
    });

    const throughputInterval = setInterval(async () => {
      try {
        const data = await fetchThroughput();
        setEventRate(data.events_per_second || 0);
      } catch { /* API not ready yet */ }
    }, 1000);

    return () => {
      logWs.close();
      anomalyWs.close();
      clearInterval(throughputInterval);
    };
  }, []);

  const stats = {
    totalLogs: logs.length,
    queryTime,
    anomalyCount: anomalies.length,
    eventRate,
    connected,
  };

  return (
    <div className="app">
      <Header />
      <main className="main">
        <div className="controls">
          <div className="control-group">
            <label>Service</label>
            <select value={selectedService} onChange={(e) => setSelectedService(e.target.value)}>
              {SERVICES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="control-group">
            <label>Date</label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
            />
          </div>
          <div className="control-group">
            <label>Severity</label>
            <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
              <option value="">All</option>
              <option value="INFO">INFO</option>
              <option value="WARN">WARN</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>
          <button className="btn-refresh" onClick={loadData}>Refresh</button>
        </div>

        <StatsBar stats={stats} />

        <div className="charts-row">
          <div className="chart-card wide">
            <h3>Log Volume Trend</h3>
            <VolumeChart data={volume} />
          </div>
          <div className="chart-card narrow">
            <h3>Severity Distribution</h3>
            <SeverityChart data={severityDist} />
          </div>
        </div>

        <div className="charts-row">
          <div className="chart-card wide">
            <h3>Anomaly Timeline</h3>
            <AnomalyTimeline anomalies={anomalies} />
          </div>
          <div className="chart-card narrow">
            <h3>Real-time Alerts</h3>
            <AlertPanel alerts={realtimeAlerts} />
          </div>
        </div>

        <div className="log-section">
          <h3>Recent Logs — {selectedService}</h3>
          <LogTable logs={logs} realtimeLogs={realtimeLogs.filter(l => l.service_name === selectedService)} />
        </div>
      </main>
    </div>
  );
}
