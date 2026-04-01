import React from 'react';

const panelStyle = {
  maxHeight: '220px',
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: '6px',
};

const alertStyle = {
  background: 'rgba(239, 68, 68, 0.08)',
  border: '1px solid rgba(239, 68, 68, 0.25)',
  borderRadius: '8px',
  padding: '10px 12px',
  fontSize: '0.8rem',
};

const alertHeader = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: '4px',
};

const serviceTag = {
  fontFamily: "'JetBrains Mono', monospace",
  fontWeight: 600,
  color: 'var(--accent-red)',
  fontSize: '0.75rem',
};

const timeTag = {
  color: 'var(--text-muted)',
  fontSize: '0.7rem',
};

const messageStyle = {
  color: 'var(--text-secondary)',
  fontSize: '0.75rem',
  lineHeight: 1.4,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const scoreStyle = {
  color: 'var(--accent-orange)',
  fontSize: '0.7rem',
  fontFamily: "'JetBrains Mono', monospace",
};

export default function AlertPanel({ alerts }) {
  if (!alerts || alerts.length === 0) {
    return (
      <div style={{ color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>
        No real-time alerts
      </div>
    );
  }

  return (
    <div style={panelStyle}>
      {alerts.slice(0, 20).map((alert, i) => (
        <div key={alert.alert_id || i} style={alertStyle}>
          <div style={alertHeader}>
            <span style={serviceTag}>{alert.service_name}</span>
            <span style={timeTag}>
              {alert.timestamp ? alert.timestamp.slice(11, 19) : ''}
            </span>
          </div>
          <div style={messageStyle}>{alert.message}</div>
          <div style={scoreStyle}>score: {alert.anomaly_score?.toFixed(4)}</div>
        </div>
      ))}
    </div>
  );
}
