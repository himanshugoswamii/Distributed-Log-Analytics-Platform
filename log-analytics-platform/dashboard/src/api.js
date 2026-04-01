const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://localhost:8000';

export async function fetchLogs(serviceName, logDate, severity, limit = 100) {
  const params = new URLSearchParams({ service_name: serviceName, limit: String(limit) });
  if (logDate) params.append('log_date', logDate);
  if (severity) params.append('severity', severity);
  const res = await fetch(`${API_BASE}/logs?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchLogVolume(serviceName, logDate) {
  const params = new URLSearchParams({ service_name: serviceName });
  if (logDate) params.append('log_date', logDate);
  const res = await fetch(`${API_BASE}/logs/volume?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchAnomalies(serviceName, logDate, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (serviceName) params.append('service_name', serviceName);
  if (logDate) params.append('log_date', logDate);
  const res = await fetch(`${API_BASE}/anomalies?${params}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchServices() {
  const res = await fetch(`${API_BASE}/services`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function fetchThroughput() {
  const res = await fetch(`${API_BASE}/throughput`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function createLogWebSocket(onMessage) {
  const ws = new WebSocket(`${WS_BASE}/ws/logs`);
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch { /* ignore parse errors */ }
  };
  ws.onerror = () => {};
  ws.onclose = () => {
    setTimeout(() => createLogWebSocket(onMessage), 3000);
  };
  return ws;
}

export function createAnomalyWebSocket(onMessage) {
  const ws = new WebSocket(`${WS_BASE}/ws/anomalies`);
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch { /* ignore parse errors */ }
  };
  ws.onerror = () => {};
  ws.onclose = () => {
    setTimeout(() => createAnomalyWebSocket(onMessage), 3000);
  };
  return ws;
}
