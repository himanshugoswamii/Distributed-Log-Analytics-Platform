import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';

const tooltipStyle = {
  backgroundColor: '#1e2235',
  border: '1px solid #2a2f45',
  borderRadius: '8px',
  padding: '8px 12px',
  fontSize: '0.8rem',
  color: '#e4e6f0',
};

export default function VolumeChart({ data }) {
  if (!data || data.length === 0) {
    return <div style={{ color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>No volume data yet</div>;
  }

  const formatted = data.map((d) => ({
    ...d,
    label: d.minute ? d.minute.slice(11, 16) : '',
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={formatted} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="volumeGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2f45" />
        <XAxis dataKey="label" tick={{ fill: '#8b8fa3', fontSize: 11 }} tickLine={false} />
        <YAxis tick={{ fill: '#8b8fa3', fontSize: 11 }} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={tooltipStyle} />
        <Area
          type="monotone"
          dataKey="count"
          stroke="#3b82f6"
          strokeWidth={2}
          fill="url(#volumeGrad)"
          animationDuration={300}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
