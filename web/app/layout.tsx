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
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" defer crossOrigin="anonymous"></script>
        <script
          dangerouslySetInnerHTML={{
            __html: `window.__leafletFailed = false; setTimeout(function () { if (!window.L) { window.__leafletFailed = true; } }, 3000);`,
          }}
        />
      </head>
      <body style={{
        margin: 0,
        padding: 0,
        backgroundColor: '#f5f5f5',
        color: '#ffffff',
        fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
        minHeight: '100vh',
      }}>
        <nav style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 20px',
          height: '48px',
          backgroundColor: '#f5f5f5',
          borderBottom: '1px solid #e0e0e0',
          fontSize: '13px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <span style={{ fontWeight: 700, fontSize: '15px', color: '#D94436', letterSpacing: '0.5px' }}>
              CUE2CASE
            </span>
            <Link href="/" style={{ color: '#999999', textDecoration: 'none' }}>Queue</Link>
            <Link href="/map" style={{ color: '#999999', textDecoration: 'none' }}>Map</Link>
            <Link href="/external-cues" style={{ color: '#999999', textDecoration: 'none' }}>Cues</Link>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ color: '#D94436', fontSize: '11px' }}>● DUQM PROFILE ACTIVE</span>
            <span style={{ color: '#999999', fontSize: '11px' }}>OPERATOR: ABDULLAH</span>
          </div>
        </nav>
        <main style={{ padding: '16px 20px' }}>
          {children}
        </main>
      </body>
    </html>
  );
}
