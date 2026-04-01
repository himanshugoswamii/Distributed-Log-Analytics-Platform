import React from 'react';

const barStyle = {
  display: 'flex',
  gap: '12px',
  marginBottom: '20px',
  flexWrap: 'wrap',
};

const cardStyle = {
  flex: '1 1 160px',
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  padding: '14px 18px',
  boxShadow: 'var(--shadow)',
};

const labelStyle = {
  fontSize: '0.7rem',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: 'var(--text-muted)',
  marginBottom: '4px',
};

const valueStyle = {
  fontSize: '1.5rem',
  fontWeight: 700,
  lineHeight: 1.2,
};

export default function StatsBar({ stats }) {
  const items = [
    { label: 'Logs Queried', value: stats.totalLogs, color: 'var(--accent-blue)' },
    { label: 'Query Time', value: `${stats.queryTime.toFixed(1)}ms`, color: stats.queryTime < 200 ? 'var(--accent-green)' : 'var(--accent-orange)' },
    { label: 'Anomalies', value: stats.anomalyCount, color: stats.anomalyCount > 0 ? 'var(--accent-red)' : 'var(--accent-green)' },
    { label: 'Events/sec', value: stats.eventRate, color: 'var(--accent-purple)' },
    { label: 'Status', value: stats.connected ? 'Connected' : 'Disconnected', color: stats.connected ? 'var(--accent-green)' : 'var(--accent-red)' },
  ];

  return (
    <div style={barStyle}>
      {items.map((item) => (
        <div key={item.label} style={cardStyle}>
          <div style={labelStyle}>{item.label}</div>
          <div style={{ ...valueStyle, color: item.color }}>{item.value}</div>
        </div>
      ))}
    </div>
  );
}
