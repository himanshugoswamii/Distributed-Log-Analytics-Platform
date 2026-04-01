import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const COLORS = {
  INFO: '#3b82f6',
  WARN: '#eab308',
  ERROR: '#f97316',
  CRITICAL: '#ef4444',
};

const tooltipStyle = {
  backgroundColor: '#1e2235',
  border: '1px solid #2a2f45',
  borderRadius: '8px',
  padding: '8px 12px',
  fontSize: '0.8rem',
  color: '#e4e6f0',
};

export default function SeverityChart({ data }) {
  if (!data || Object.keys(data).length === 0) {
    return <div style={{ color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>No severity data</div>;
  }

  const chartData = Object.entries(data)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }));

  if (chartData.length === 0) {
    return <div style={{ color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>No logs yet</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={80}
          dataKey="value"
          paddingAngle={3}
          animationDuration={300}
        >
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={COLORS[entry.name] || '#666'} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
        <Legend
          wrapperStyle={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}
          iconType="circle"
          iconSize={8}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
