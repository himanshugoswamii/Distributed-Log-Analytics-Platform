import React, { useState } from 'react';

const tableContainer = {
  overflowX: 'auto',
  maxHeight: '420px',
  overflowY: 'auto',
};

const tableStyle = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '0.8rem',
};

const thStyle = {
  position: 'sticky',
  top: 0,
  background: 'var(--bg-card)',
  padding: '8px 10px',
  textAlign: 'left',
  fontWeight: 600,
  color: 'var(--text-muted)',
  fontSize: '0.7rem',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  borderBottom: '1px solid var(--border)',
  zIndex: 1,
};

const tdStyle = {
  padding: '6px 10px',
  borderBottom: '1px solid var(--border)',
  color: 'var(--text-secondary)',
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: '0.75rem',
  whiteSpace: 'nowrap',
};

const SEVERITY_COLORS = {
  INFO: 'var(--severity-info)',
  WARN: 'var(--severity-warn)',
  ERROR: 'var(--severity-error)',
  CRITICAL: 'var(--severity-critical)',
};

function SeverityBadge({ level }) {
  const color = SEVERITY_COLORS[level] || 'var(--text-muted)';
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: '4px',
        fontSize: '0.7rem',
        fontWeight: 600,
        color,
        background: `${color}15`,
        border: `1px solid ${color}30`,
      }}
    >
      {level}
    </span>
  );
}

export default function LogTable({ logs, realtimeLogs = [] }) {
  const [showRealtime, setShowRealtime] = useState(true);
  const combined = showRealtime
    ? [...realtimeLogs.slice(0, 50), ...logs].slice(0, 200)
    : logs;

  return (
    <>
      <div style={{ marginBottom: '8px' }}>
        <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showRealtime}
            onChange={(e) => setShowRealtime(e.target.checked)}
            style={{ marginRight: '6px' }}
          />
          Show real-time stream
        </label>
        <span style={{ marginLeft: '12px', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
          {combined.length} entries
        </span>
      </div>
      <div style={tableContainer}>
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Timestamp</th>
              <th style={thStyle}>Level</th>
              <th style={thStyle}>Service</th>
              <th style={thStyle}>Message</th>
            </tr>
          </thead>
          <tbody>
            {combined.map((log, i) => (
              <tr
                key={log.log_id || i}
                style={{
                  background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-hover)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)')}
              >
                <td style={tdStyle}>
                  {log.timestamp ? String(log.timestamp).slice(11, 23) : '—'}
                </td>
                <td style={tdStyle}>
                  <SeverityBadge level={log.log_level} />
                </td>
                <td style={{ ...tdStyle, color: 'var(--accent-blue)' }}>{log.service_name}</td>
                <td style={{ ...tdStyle, whiteSpace: 'normal', maxWidth: '500px', wordBreak: 'break-word' }}>
                  {log.message}
                </td>
              </tr>
            ))}
            {combined.length === 0 && (
              <tr>
                <td colSpan={4} style={{ ...tdStyle, textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                  No logs available
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
