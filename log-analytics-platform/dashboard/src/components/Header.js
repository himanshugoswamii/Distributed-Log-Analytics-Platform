import React from 'react';

const headerStyle = {
  background: 'var(--bg-secondary)',
  borderBottom: '1px solid var(--border)',
  padding: '14px 24px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
};

const logoStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
};

const titleStyle = {
  fontSize: '1.15rem',
  fontWeight: 700,
  color: 'var(--text-primary)',
  letterSpacing: '-0.01em',
};

const badgeStyle = {
  fontSize: '0.7rem',
  fontWeight: 600,
  background: 'var(--accent-blue)',
  color: '#fff',
  padding: '2px 8px',
  borderRadius: '20px',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
};

const subtitleStyle = {
  fontSize: '0.8rem',
  color: 'var(--text-muted)',
};

export default function Header() {
  return (
    <header style={headerStyle}>
      <div style={logoStyle}>
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <rect width="28" height="28" rx="6" fill="var(--accent-blue)" />
          <path d="M7 10h14M7 14h10M7 18h12" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <div>
          <div style={titleStyle}>
            Log Analytics Platform <span style={badgeStyle}>Live</span>
          </div>
          <div style={subtitleStyle}>Distributed real-time log monitoring</div>
        </div>
      </div>
    </header>
  );
}
