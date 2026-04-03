// Server-rendered operations dashboard with live stats, distributions, and top-vessel activity.
import Link from 'next/link';

const apiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

type StatsResponse = {
  total_cases?: number | null;
  by_status?: Record<string, number> | null;
  alerts_by_type?: Record<string, number> | null;
  total_alerts?: number | null;
  total_vessels?: number | null;
  avg_confidence?: number | null;
  false_positive_rate?: number | null;
  top_vessels?: Array<{
    mmsi?: string | number | null;
    vessel_name?: string | null;
    alert_count?: number | null;
  }> | null;
};

const COLORS = {
  bg: '#f5f5f5',
  panel: '#1a1a1a',
  border: '#e0e0e0',
  accent: '#D94436',
  text: '#ffffff',
  secondary: '#999999',
  tertiary: '#999999',
};

function labelize(value?: string | null) {
  if (!value) {
    return 'Unknown';
  }

  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatNumber(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '0';
  }

  return new Intl.NumberFormat('en-US').format(value);
}

function formatPercent(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '0%';
  }

  return `${value.toFixed(1)}%`;
}

function formatText(value?: string | number | null) {
  if (value === null || value === undefined) {
    return '—';
  }

  const text = String(value).trim();
  return text.length > 0 ? text : '—';
}

function outlinedButtonStyle(): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '10px 14px',
    borderRadius: '8px',
    background: 'transparent',
    border: `1px solid ${COLORS.accent}`,
    color: COLORS.accent,
    textDecoration: 'none',
    fontSize: '12px',
    fontWeight: 700,
    letterSpacing: '0.04em',
  };
}

async function getStats() {
  const response = await fetch(`${apiUrl}/stats`, { cache: 'no-store' });

  if (!response.ok) {
    throw new Error(`Failed to fetch stats (${response.status})`);
  }

  return (await response.json()) as StatsResponse;
}

export default async function DashboardPage() {
  let stats: StatsResponse | null = null;
  let error = '';

  try {
    stats = await getStats();
  } catch (err) {
    error = err instanceof Error ? err.message : 'Failed to fetch stats';
  }

  const byStatus = stats?.by_status || {};
  const alertsByType = stats?.alerts_by_type || {};
  const topVessels = Array.isArray(stats?.top_vessels) ? stats?.top_vessels : [];

  const openCases = (byStatus.new || 0) + (byStatus.in_review || 0);
  const escalatedCases = byStatus.escalated || 0;

  const statusEntries = Object.entries(byStatus).sort((a, b) => b[1] - a[1]);
  const alertEntries = Object.entries(alertsByType).sort((a, b) => b[1] - a[1]);
  const largestStatusCount = statusEntries[0]?.[1] || 0;
  const largestAlertCount = alertEntries[0]?.[1] || 0;

  return (
    <main
      style={{
        minHeight: '100vh',
        background: COLORS.bg,
        color: COLORS.text,
        padding: '24px',
        fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
      }}
    >
      <div style={{ maxWidth: '1400px', margin: '0 auto', display: 'grid', gap: '16px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <Link href="/" style={outlinedButtonStyle()}>
              ← Back to queue
            </Link>
          </div>
          <div style={{ color: COLORS.tertiary, fontSize: '12px' }}>Ops overview</div>
        </div>

        <section
          style={{
            background: COLORS.panel,
            border: `1px solid ${COLORS.border}`,
            borderRadius: '12px',
            padding: '20px',
            display: 'grid',
            gap: '10px',
          }}
        >
          <div style={{ color: COLORS.secondary, fontSize: '12px', letterSpacing: '0.14em', textTransform: 'uppercase' }}>
            Cue2Case
          </div>
          <div style={{ fontSize: '34px', fontWeight: 700, lineHeight: 1.05 }}>OPERATIONS DASHBOARD</div>
          <div style={{ color: COLORS.tertiary, fontSize: '13px', maxWidth: '60rem' }}>
            Live operational snapshot of case load, alert patterns, and the highest-activity vessels.
          </div>
        </section>

        {error ? (
          <section
            style={{
              background: COLORS.panel,
              border: `1px solid ${COLORS.accent}`,
              borderRadius: '12px',
              padding: '16px',
              color: COLORS.text,
            }}
          >
            <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '6px' }}>Unable to load dashboard</div>
            <div style={{ color: COLORS.secondary, fontSize: '13px' }}>{error}</div>
          </section>
        ) : null}

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '12px',
          }}
        >
          {[
            { label: 'Total Cases', value: formatNumber(stats?.total_cases) },
            { label: 'Open', value: formatNumber(openCases) },
            { label: 'Escalated', value: formatNumber(escalatedCases) },
            { label: 'FP Rate', value: formatPercent(stats?.false_positive_rate) },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                background: COLORS.panel,
                border: `1px solid ${COLORS.border}`,
                borderRadius: '12px',
                padding: '16px',
              }}
            >
              <div
                style={{
                  color: COLORS.tertiary,
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                  marginBottom: '8px',
                }}
              >
                {item.label}
              </div>
              <div style={{ color: COLORS.text, fontSize: '28px', fontWeight: 700 }}>{item.value}</div>
            </div>
          ))}
        </section>

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '16px',
            alignItems: 'start',
          }}
        >
          <div
            style={{
              background: COLORS.panel,
              border: `1px solid ${COLORS.border}`,
              borderRadius: '12px',
              padding: '18px',
              display: 'grid',
              gap: '14px',
            }}
          >
            <div>
              <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '4px' }}>Alerts by type</div>
              <div style={{ color: COLORS.secondary, fontSize: '12px' }}>
                Relative volume across alert categories.
              </div>
            </div>

            {alertEntries.length ? (
              <div style={{ display: 'grid', gap: '10px' }}>
                {alertEntries.map(([type, count]) => {
                  const width = largestAlertCount > 0 ? Math.max((count / largestAlertCount) * 100, 8) : 0;
                  return (
                    <div key={type} style={{ display: 'grid', gap: '6px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '12px' }}>
                        <span style={{ color: COLORS.text }}>{labelize(type)}</span>
                        <span style={{ color: COLORS.secondary }}>{formatNumber(count)}</span>
                      </div>
                      <div
                        style={{
                          height: '14px',
                          background: COLORS.bg,
                          border: `1px solid ${COLORS.border}`,
                          borderRadius: '999px',
                          overflow: 'hidden',
                        }}
                      >
                        <div style={{ width: `${width}%`, height: '100%', background: COLORS.accent }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div style={{ color: COLORS.tertiary, fontSize: '13px' }}>No alert data available.</div>
            )}
          </div>

          <div
            style={{
              background: COLORS.panel,
              border: `1px solid ${COLORS.border}`,
              borderRadius: '12px',
              padding: '18px',
              display: 'grid',
              gap: '14px',
            }}
          >
            <div>
              <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '4px' }}>Cases by status</div>
              <div style={{ color: COLORS.secondary, fontSize: '12px' }}>
                Current distribution of investigation workflow states.
              </div>
            </div>

            {statusEntries.length ? (
              <div style={{ display: 'grid', gap: '10px' }}>
                {statusEntries.map(([status, count]) => {
                  const width = largestStatusCount > 0 ? Math.max((count / largestStatusCount) * 100, 8) : 0;
                  return (
                    <div key={status} style={{ display: 'grid', gap: '6px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '12px' }}>
                        <span style={{ color: COLORS.text }}>{labelize(status)}</span>
                        <span style={{ color: COLORS.secondary }}>{formatNumber(count)}</span>
                      </div>
                      <div
                        style={{
                          height: '14px',
                          background: COLORS.bg,
                          border: `1px solid ${COLORS.border}`,
                          borderRadius: '999px',
                          overflow: 'hidden',
                        }}
                      >
                        <div style={{ width: `${width}%`, height: '100%', background: COLORS.accent }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div style={{ color: COLORS.tertiary, fontSize: '13px' }}>No case-status data available.</div>
            )}
          </div>
        </section>

        <section
          style={{
            background: COLORS.panel,
            border: `1px solid ${COLORS.border}`,
            borderRadius: '12px',
            padding: '18px',
            display: 'grid',
            gap: '12px',
            overflowX: 'auto',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'baseline' }}>
            <div style={{ fontSize: '16px', fontWeight: 700 }}>Top 10 vessels</div>
            <div style={{ color: COLORS.secondary, fontSize: '12px' }}>{topVessels.length} vessels</div>
          </div>

          {topVessels.length ? (
            <div style={{ minWidth: '720px' }}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '80px 160px 1fr 140px',
                  gap: '10px',
                  padding: '10px 12px',
                  borderBottom: `1px solid ${COLORS.border}`,
                  color: COLORS.tertiary,
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                }}
              >
                <span>Rank</span>
                <span>MMSI</span>
                <span>Vessel</span>
                <span>Alert Count</span>
              </div>
              {topVessels.map((vessel, index) => {
                const mmsi = vessel.mmsi !== null && vessel.mmsi !== undefined ? String(vessel.mmsi) : '';
                return (
                  <div
                    key={`${mmsi || 'unknown'}-${index}`}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '80px 160px 1fr 140px',
                      gap: '10px',
                      padding: '12px',
                      borderBottom: `1px solid ${COLORS.border}`,
                      alignItems: 'center',
                    }}
                  >
                    <span style={{ color: COLORS.secondary }}>{index + 1}</span>
                    {mmsi ? (
                      <Link href={`/vessels/${mmsi}`} style={{ color: COLORS.accent, textDecoration: 'none', fontWeight: 700 }}>
                        {mmsi}
                      </Link>
                    ) : (
                      <span style={{ color: COLORS.secondary }}>—</span>
                    )}
                    <span style={{ color: COLORS.text, fontWeight: 700 }}>{formatText(vessel.vessel_name || 'Unknown vessel')}</span>
                    <span style={{ color: COLORS.secondary }}>{formatNumber(vessel.alert_count)}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ color: COLORS.tertiary, fontSize: '13px' }}>No vessel activity available.</div>
          )}
        </section>
      </div>
    </main>
  );
}
