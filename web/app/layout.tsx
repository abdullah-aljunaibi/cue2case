import type { ReactNode } from 'react';
import Link from 'next/link';

export const metadata = {
  title: 'Cue2Case v3 — Maritime Operator Console',
  description: 'Duqm-oriented maritime anomaly triage and case management',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" defer></script>
      </head>
      <body style={{
        margin: 0,
        padding: 0,
        backgroundColor: '#0a0e17',
        color: '#e0e6f0',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        minHeight: '100vh',
      }}>
        <nav style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 20px',
          height: '48px',
          backgroundColor: '#0d1220',
          borderBottom: '1px solid #1a2338',
          fontSize: '13px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <span style={{ fontWeight: 700, fontSize: '15px', color: '#60a5fa', letterSpacing: '0.5px' }}>
              CUE2CASE
            </span>
            <Link href="/" style={{ color: '#94a3b8', textDecoration: 'none' }}>Queue</Link>
            <Link href="/map" style={{ color: '#94a3b8', textDecoration: 'none' }}>Map</Link>
            <Link href="/external-cues" style={{ color: '#94a3b8', textDecoration: 'none' }}>Cues</Link>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ color: '#4ade80', fontSize: '11px' }}>● DUQM PROFILE ACTIVE</span>
            <span style={{ color: '#64748b', fontSize: '11px' }}>OPERATOR: ABDULLAH</span>
          </div>
        </nav>
        <main style={{ padding: '16px 20px' }}>
          {children}
        </main>
      </body>
    </html>
  );
}
