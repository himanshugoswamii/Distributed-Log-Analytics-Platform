import React from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ZAxis,
} from 'recharts';

const tooltipStyle = {
  backgroundColor: '#1e2235',
  border: '1px solid #2a2f45',
  borderRadius: '8px',
  padding: '8px 12px',
  fontSize: '0.8rem',
  color: '#e4e6f0',
};

function CustomTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0].payload;
  return (
    <div style={tooltipStyle}>
      <div><strong>{d.service_name}</strong></div>
      <div>Score: {d.anomaly_score?.toFixed(4)}</div>
      <div>Level: {d.log_level}</div>
      <div style={{ fontSize: '0.7rem', color: '#8b8fa3', marginTop: 4 }}>
        {d.timestamp}
      </div>
    </div>
  );
}

export default function AnomalyTimeline({ anomalies }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>
        No anomalies detected
      </div>
    );
  }

  const data = anomalies.map((a, i) => ({
    ...a,
    idx: i,
    score: Math.abs(a.anomaly_score || 0),
    time: a.timestamp ? a.timestamp.slice(11, 19) : String(i),
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2f45" />
        <XAxis dataKey="time" tick={{ fill: '#8b8fa3', fontSize: 11 }} tickLine={false} name="Time" />
        <YAxis dataKey="score" tick={{ fill: '#8b8fa3', fontSize: 11 }} tickLine={false} axisLine={false} name="Score" />
        <ZAxis range={[40, 200]} />
        <Tooltip content={<CustomTooltip />} />
        <Scatter data={data} fill="#ef4444" fillOpacity={0.7} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
