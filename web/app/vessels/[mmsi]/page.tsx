// Server-rendered vessel 360° detail page with OKB styling, linked cases, alerts, cues, and vessel stats.
import Link from 'next/link';

const apiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

const COLORS = {
  bg: '#f5f5f5',
  panel: '#ffffff',
  border: '#e0e0e0',
  accent: '#D94436',
  text: '#1a1a1a',
  secondary: '#666666',
  tertiary: '#999999',
};

type VesselRecord = {
  name?: string | null;
  vessel_name?: string | null;
  mmsi?: string | number | null;
  type?: string | null;
  vessel_type?: string | null;
  length?: number | null;
  width?: number | null;
  first_seen?: string | null;
  last_seen?: string | null;
};

type CaseItem = {
  id?: string | number | null;
  title?: string | null;
  status?: string | null;
  anomaly_score?: number | null;
  rank_score?: number | null;
  start_observed_at?: string | null;
};

type AlertItem = {
  alert_type?: string | null;
  severity?: number | null;
  observed_at?: string | null;
  explanation?: string | null;
};

type TrackItem = {
  id?: string | number | null;
};

type ExternalCueItem = {
  id?: string | number | null;
  cue_type?: string | null;
  source?: string | null;
  data?: Record<string, unknown> | null;
};

type VesselStats = {
  total_cases?: number | null;
  total_alerts?: number | null;
  total_positions?: number | null;
  first_seen?: string | null;
  last_seen?: string | null;
};

type VesselResponse = {
  vessel?: VesselRecord | null;
  cases?: CaseItem[] | null;
  alerts?: AlertItem[] | null;
  tracks?: TrackItem[] | null;
  external_cues?: ExternalCueItem[] | null;
  stats?: VesselStats | null;
};

function formatText(value?: string | number | null) {
  if (value === null || value === undefined) {
    return '—';
  }

  const text = String(value).trim();
  return text.length > 0 ? text : '—';
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '—';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  return `${date.toISOString().slice(0, 10)} ${date.toISOString().slice(11, 16)} UTC`;
}

function formatNumber(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }

  return new Intl.NumberFormat('en-US').format(value);
}

function formatScore(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }

  return value.toFixed(3);
}

function labelize(value?: string | null) {
  if (!value) {
    return 'Unknown';
  }

  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getAlertType(alert: AlertItem) {
  return alert.alert_type || 'unknown';
}

function getAlertTimestamp(alert: AlertItem) {
  return alert.observed_at || null;
}

function getSeverityColor(severity?: string | number | null) {
  const num = typeof severity === 'number' ? severity : parseFloat(String(severity ?? '0'));
  if (num >= 0.8) return COLORS.accent;
  if (num >= 0.5) return '#1a1a1a';
  return COLORS.secondary;
}

function outlinedButtonStyle(): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '10px 14px',
    borderRadius: '8px',
    background: 'transparent',
    border: '1px solid #D94436',
    color: COLORS.accent,
    textDecoration: 'none',
    fontSize: '12px',
    fontWeight: 700,
    letterSpacing: '0.04em',
  };
}

export default async function VesselDetailPage({ params }: { params: Promise<{ mmsi: string }> }) {
  const { mmsi } = await params;

  let payload: VesselResponse | null = null;
  let error = '';

  try {
    const response = await fetch(`${apiUrl}/vessels/${encodeURIComponent(mmsi)}`, { cache: 'no-store' });

    if (!response.ok) {
      throw new Error(`Failed to fetch vessel (${response.status})`);
    }

    payload = (await response.json()) as VesselResponse;
  } catch (err) {
    error = err instanceof Error ? err.message : 'Failed to fetch vessel';
  }

  const vessel = payload?.vessel || null;
  const cases = Array.isArray(payload?.cases) ? payload?.cases : [];
  const alerts = Array.isArray(payload?.alerts) ? payload?.alerts : [];
  const tracks = Array.isArray(payload?.tracks) ? payload?.tracks : [];
  const externalCues = Array.isArray(payload?.external_cues) ? payload?.external_cues : [];
  const stats = payload?.stats || {};

  const vesselName = vessel?.name || vessel?.vessel_name || `Vessel ${mmsi}`;
  const totalCases = stats.total_cases ?? cases.length;
  const totalAlerts = stats.total_alerts ?? alerts.length;
  const totalPositions = stats.total_positions ?? tracks.length;
  const firstSeen = stats.first_seen || vessel?.first_seen || null;
  const lastSeen = stats.last_seen || vessel?.last_seen || null;

  const sortedAlerts = [...alerts].sort((a, b) => {
    const aTime = getAlertTimestamp(a);
    const bTime = getAlertTimestamp(b);
    const aValue = aTime ? new Date(aTime).getTime() : 0;
    const bValue = bTime ? new Date(bTime).getTime() : 0;
    return aValue - bValue;
  });

  const alertTypeCounts = sortedAlerts.reduce<Record<string, number>>((acc, alert) => {
    const key = getAlertType(alert);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const alertTypeEntries = Object.entries(alertTypeCounts).sort((a, b) => b[1] - a[1]);
  const largestAlertBucket = alertTypeEntries[0]?.[1] || 0;

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
          }}
        >
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <Link href="/" style={outlinedButtonStyle()}>
              ← Back to queue
            </Link>
            <Link href="/map" style={outlinedButtonStyle()}>
              View on map
            </Link>
          </div>
          <div style={{ color: COLORS.tertiary, fontSize: '12px', alignSelf: 'center' }}>
            Vessel 360° profile
          </div>
        </div>

        <section
          style={{
            background: COLORS.panel,
            border: `1px solid ${COLORS.border}`,
            borderRadius: '12px',
            padding: '20px',
            display: 'grid',
            gap: '12px',
          }}
        >
          <div style={{ color: COLORS.secondary, fontSize: '12px', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
            Vessel profile
          </div>
          <div style={{ fontSize: '34px', fontWeight: 700, lineHeight: 1.1 }}>{formatText(vesselName)}</div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: '10px',
            }}
          >
            {[
              { label: 'MMSI', value: formatText(vessel?.mmsi ?? mmsi) },
              { label: 'Type', value: formatText(vessel?.type || vessel?.vessel_type) },
              { label: 'Length', value: vessel?.length ? `${vessel.length}m` : '—' },
              { label: 'Width', value: vessel?.width ? `${vessel.width}m` : '—' },
            ].map((item) => (
              <div
                key={item.label}
                style={{
                  padding: '12px',
                  borderRadius: '10px',
                  background: COLORS.bg,
                  border: `1px solid ${COLORS.border}`,
                }}
              >
                <div style={{ fontSize: '11px', color: COLORS.tertiary, marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  {item.label}
                </div>
                <div style={{ fontSize: '16px', color: COLORS.text, fontWeight: 700 }}>{item.value}</div>
              </div>
            ))}
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
            <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '6px' }}>Unable to load vessel detail</div>
            <div style={{ color: COLORS.secondary, fontSize: '13px' }}>{error}</div>
          </section>
        ) : (
          <>
            <section
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '12px',
              }}
            >
              {[
                { label: 'Total cases', value: formatNumber(totalCases) },
                { label: 'Total alerts', value: formatNumber(totalAlerts) },
                { label: 'Total positions', value: formatNumber(totalPositions) },
                { label: 'First seen', value: formatDateTime(firstSeen) },
                { label: 'Last seen', value: formatDateTime(lastSeen) },
              ].map((item) => (
                <div
                  key={item.label}
                  style={{
                    background: COLORS.panel,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: '12px',
                    padding: '14px',
                  }}
                >
                  <div style={{ color: COLORS.tertiary, fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '6px' }}>
                    {item.label}
                  </div>
                  <div style={{ color: COLORS.text, fontSize: '18px', fontWeight: 700, wordBreak: 'break-word' }}>{item.value}</div>
                </div>
              ))}
            </section>

            <section
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
                <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '4px' }}>Alert type breakdown</div>
                <div style={{ color: COLORS.secondary, fontSize: '12px' }}>
                  Distribution of alerts returned for this vessel.
                </div>
              </div>

              {alertTypeEntries.length ? (
                <div style={{ display: 'grid', gap: '10px' }}>
                  {alertTypeEntries.map(([type, count]) => {
                    const width = largestAlertBucket > 0 ? Math.max((count / largestAlertBucket) * 100, 8) : 0;
                    return (
                      <div key={type} style={{ display: 'grid', gap: '6px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '12px' }}>
                          <span style={{ color: COLORS.text }}>{labelize(type)}</span>
                          <span style={{ color: COLORS.secondary }}>{count}</span>
                        </div>
                        <div style={{ height: '14px', background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: '999px', overflow: 'hidden' }}>
                          <div style={{ width: `${width}%`, height: '100%', background: COLORS.accent }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ color: COLORS.tertiary, fontSize: '13px' }}>No alerts available for breakdown.</div>
              )}
            </section>

            <section
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 2fr) minmax(320px, 1fr)',
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
                  overflowX: 'auto',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'baseline', marginBottom: '12px', flexWrap: 'wrap' }}>
                  <div style={{ fontSize: '16px', fontWeight: 700 }}>Linked cases</div>
                  <div style={{ color: COLORS.secondary, fontSize: '12px' }}>{cases.length} cases</div>
                </div>

                {cases.length ? (
                  <div style={{ minWidth: '760px' }}>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '110px 1.8fr 120px 120px 120px 150px',
                        gap: '10px',
                        padding: '10px 12px',
                        borderBottom: `1px solid ${COLORS.border}`,
                        color: COLORS.tertiary,
                        fontSize: '11px',
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                      }}
                    >
                      <span>ID</span>
                      <span>Title</span>
                      <span>Status</span>
                      <span>Anomaly</span>
                      <span>Rank</span>
                      <span>Created</span>
                    </div>
                    {cases.map((item, index) => {
                      const caseId = item.id ?? `row-${index}`;
                      return item.id ? (
                        <Link
                          key={String(caseId)}
                          href={`/cases/${item.id}`}
                          style={{ textDecoration: 'none', color: 'inherit' }}
                        >
                          <div
                            style={{
                              display: 'grid',
                              gridTemplateColumns: '110px 1.8fr 120px 120px 120px 150px',
                              gap: '10px',
                              padding: '12px',
                              borderBottom: `1px solid ${COLORS.border}`,
                              alignItems: 'center',
                              background: 'transparent',
                            }}
                          >
                            <span style={{ color: COLORS.accent }}>{formatText(item.id)}</span>
                            <span style={{ color: COLORS.text, fontWeight: 700 }}>{formatText(item.title)}</span>
                            <span style={{ color: COLORS.secondary }}>{labelize(item.status)}</span>
                            <span style={{ color: COLORS.text }}>{formatScore(item.anomaly_score)}</span>
                            <span style={{ color: COLORS.text }}>{formatScore(item.rank_score)}</span>
                            <span style={{ color: COLORS.secondary }}>{formatDateTime(item.start_observed_at)}</span>
                          </div>
                        </Link>
                      ) : (
                        <div
                          key={String(caseId)}
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '110px 1.8fr 120px 120px 120px 150px',
                            gap: '10px',
                            padding: '12px',
                            borderBottom: `1px solid ${COLORS.border}`,
                            alignItems: 'center',
                          }}
                        >
                          <span style={{ color: COLORS.secondary }}>{formatText(item.id)}</span>
                          <span style={{ color: COLORS.text, fontWeight: 700 }}>{formatText(item.title)}</span>
                          <span style={{ color: COLORS.secondary }}>{labelize(item.status)}</span>
                          <span style={{ color: COLORS.text }}>{formatScore(item.anomaly_score)}</span>
                          <span style={{ color: COLORS.text }}>{formatScore(item.rank_score)}</span>
                          <span style={{ color: COLORS.secondary }}>{formatDateTime(item.start_observed_at)}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ color: COLORS.tertiary, fontSize: '13px' }}>No linked cases found for this vessel.</div>
                )}
              </div>

              <div style={{ display: 'grid', gap: '16px' }}>
                <section
                  style={{
                    background: COLORS.panel,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: '12px',
                    padding: '18px',
                    display: 'grid',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', alignItems: 'baseline' }}>
                    <div style={{ fontSize: '16px', fontWeight: 700 }}>Alerts timeline</div>
                    <div style={{ color: COLORS.secondary, fontSize: '12px' }}>{sortedAlerts.length} alerts</div>
                  </div>

                  {sortedAlerts.length ? (
                    sortedAlerts.map((alert, index) => (
                      <div key={`${getAlertType(alert)}-${index}`} style={{ display: 'grid', gridTemplateColumns: '24px 1fr', gap: '10px' }}>
                        <div style={{ display: 'grid', justifyItems: 'center' }}>
                          <div style={{ width: '10px', height: '10px', borderRadius: '999px', background: COLORS.accent, marginTop: '6px' }} />
                          {index < sortedAlerts.length - 1 ? <div style={{ width: '1px', minHeight: '42px', background: COLORS.border }} /> : null}
                        </div>
                        <div style={{ paddingBottom: '8px' }}>
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '6px' }}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                padding: '4px 8px',
                                borderRadius: '999px',
                                border: `1px solid ${COLORS.accent}`,
                                color: COLORS.accent,
                                fontSize: '11px',
                                textTransform: 'uppercase',
                                letterSpacing: '0.08em',
                              }}
                            >
                              {labelize(getAlertType(alert))}
                            </span>
                            <span style={{ color: getSeverityColor(alert.severity), fontSize: '12px', fontWeight: 700 }}>
                              {labelize(formatText(alert.severity))}
                            </span>
                          </div>
                          <div style={{ color: COLORS.text, fontWeight: 700, marginBottom: '4px' }}>
                            {formatText(alert.explanation)}
                          </div>
                          <div style={{ color: COLORS.secondary, fontSize: '12px' }}>{formatDateTime(getAlertTimestamp(alert))}</div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ color: COLORS.tertiary, fontSize: '13px' }}>No alerts available for this vessel.</div>
                  )}
                </section>

                <section
                  style={{
                    background: COLORS.panel,
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: '12px',
                    padding: '18px',
                    display: 'grid',
                    gap: '12px',
                  }}
                >
                  <div style={{ fontSize: '16px', fontWeight: 700 }}>External cues</div>
                  {externalCues.length ? (
                    externalCues.map((cue, index) => (
                      <div
                        key={String(cue.id ?? index)}
                        style={{
                          padding: '12px',
                          borderRadius: '10px',
                          border: `1px solid ${COLORS.border}`,
                          background: COLORS.bg,
                          display: 'grid',
                          gap: '6px',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
                          <span style={{ color: COLORS.accent, fontSize: '12px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                            {labelize(cue.cue_type)}
                          </span>
                          <span style={{ color: COLORS.secondary, fontSize: '12px' }}>{formatText(cue.source)}</span>
                        </div>
                        <div style={{ color: COLORS.text, fontSize: '13px', lineHeight: 1.5 }}>{formatText(cue.data ? JSON.stringify(cue.data) : null)}</div>
                      </div>
                    ))
                  ) : (
                    <div style={{ color: COLORS.tertiary, fontSize: '13px' }}>No external cues attached to this vessel.</div>
                  )}
                </section>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
