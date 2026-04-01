// Server-rendered Cue2Case case detail page with summary, action, and evidence timeline.
import Link from 'next/link';

type EvidenceItem = {
  id?: string | number;
  case_id?: string | number;
  evidence_type?: string | null;
  evidence_ref?: string | null;
  provenance?: string | null;
  created_at?: string | null;
  data?: {
    explanation?: string | null;
    alert_type?: string | null;
    [key: string]: unknown;
  } | null;
};

type CasePayload = {
  id?: string | number;
  title?: string | null;
  vessel_name?: string | null;
  mmsi?: string | number | null;
  anomaly_score?: number | null;
  priority?: number | null;
  status?: string | null;
  summary?: string | null;
  recommended_action?: string | null;
  created_at?: string | null;
  evidence?: EvidenceItem[] | null;
};

const apiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

function formatText(value?: string | null) {
  return value && value.trim().length > 0 ? value : '—';
}

function formatScore(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }

  return value.toFixed(3);
}

function formatUtcDate(value?: string | null) {
  if (!value) {
    return 'Unknown time';
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return 'Invalid date';
  }

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date) + ' UTC';
}

function asEvidence(caseData?: CasePayload | null) {
  return Array.isArray(caseData?.evidence) ? caseData.evidence : [];
}

async function getCase(caseId: string) {
  const endpoint = `${apiUrl}/cases/${encodeURIComponent(caseId)}`;
  const response = await fetch(endpoint, { cache: 'no-store' });

  if (response.status === 404) {
    return { kind: 'not-found' as const };
  }

  if (!response.ok) {
    return {
      kind: 'error' as const,
      message: `API request failed with status ${response.status}`,
    };
  }

  try {
    const payload = (await response.json()) as CasePayload;
    return { kind: 'ok' as const, payload };
  } catch {
    return {
      kind: 'error' as const,
      message: 'API returned invalid JSON for this case',
    };
  }
}

export default async function CaseDetailPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  const result = await getCase(caseId);

  const pageStyle = {
    fontFamily: 'Arial, sans-serif',
    backgroundColor: '#f3f6fb',
    color: '#0f172a',
    minHeight: '100vh',
    padding: '2rem',
  } as const;

  const cardStyle = {
    backgroundColor: '#ffffff',
    border: '1px solid #dbe3f0',
    borderRadius: '16px',
    padding: '1.5rem',
    boxShadow: '0 8px 24px rgba(15, 23, 42, 0.06)',
  } as const;

  return (
    <main style={pageStyle}>
      <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
        <div style={{ marginBottom: '1rem' }}>
          <Link
            href="/"
            style={{
              color: '#1d4ed8',
              textDecoration: 'none',
              fontWeight: 700,
              fontSize: '0.95rem',
            }}
          >
            ← Back to queue
          </Link>
        </div>

        {result.kind === 'not-found' ? (
          <section
            style={{
              ...cardStyle,
              textAlign: 'center',
              color: '#475569',
              padding: '2.5rem 1.5rem',
            }}
          >
            <h1 style={{ margin: '0 0 0.5rem', fontSize: '1.8rem', color: '#0f172a' }}>
              Case not found
            </h1>
            <p style={{ margin: 0, lineHeight: 1.6 }}>
              No investigation case exists for ID {caseId}.
            </p>
          </section>
        ) : result.kind === 'error' ? (
          <section
            style={{
              ...cardStyle,
              backgroundColor: '#fff1f2',
              border: '1px solid #fecdd3',
              color: '#9f1239',
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
              Unable to load case detail
            </div>
            <div style={{ fontSize: '0.95rem' }}>
              {result.message}. Check API availability and configuration.
            </div>
          </section>
        ) : (
          (() => {
            const caseData = result.payload;
            const evidence = asEvidence(caseData);

            return (
              <div style={{ display: 'grid', gap: '1rem' }}>
                <section style={cardStyle}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: '1rem',
                      flexWrap: 'wrap',
                      marginBottom: '1rem',
                    }}
                  >
                    <div>
                      <h1 style={{ margin: '0 0 0.35rem', fontSize: '2rem' }}>
                        {formatText(caseData.title)}
                      </h1>
                      <div style={{ color: '#475569', fontSize: '1rem' }}>
                        {caseData.vessel_name ? `${caseData.vessel_name} · ` : ''}
                        MMSI: {caseData.mmsi ?? '—'}
                      </div>
                    </div>
                    <div
                      style={{
                        backgroundColor: '#eff6ff',
                        border: '1px solid #bfdbfe',
                        color: '#1d4ed8',
                        borderRadius: '999px',
                        padding: '0.45rem 0.8rem',
                        fontSize: '0.9rem',
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Score {formatScore(caseData.anomaly_score)}
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                      gap: '0.75rem',
                    }}
                  >
                    {[
                      { label: 'Priority', value: caseData.priority ?? '—' },
                      { label: 'Status', value: formatText(caseData.status) },
                      { label: 'Created', value: formatUtcDate(caseData.created_at) },
                    ].map((field) => (
                      <div
                        key={field.label}
                        style={{
                          padding: '0.85rem',
                          backgroundColor: '#f8fafc',
                          border: '1px solid #e2e8f0',
                          borderRadius: '12px',
                        }}
                      >
                        <div style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: '0.25rem' }}>
                          {field.label}
                        </div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>{field.value}</div>
                      </div>
                    ))}
                  </div>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '0.4rem' }}>
                    Summary
                  </div>
                  <p style={{ margin: 0, lineHeight: 1.7, color: '#334155' }}>
                    {formatText(caseData.summary)}
                  </p>
                </section>

                <section style={cardStyle}>
                  <div style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '0.4rem' }}>
                    Recommended action
                  </div>
                  <p style={{ margin: 0, lineHeight: 1.7, color: '#334155' }}>
                    {formatText(caseData.recommended_action)}
                  </p>
                </section>

                <section style={cardStyle}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: '1rem',
                      flexWrap: 'wrap',
                      marginBottom: '1rem',
                    }}
                  >
                    <div>
                      <h2 style={{ margin: 0, fontSize: '1.35rem' }}>Evidence timeline</h2>
                      <div style={{ marginTop: '0.25rem', color: '#64748b', fontSize: '0.9rem' }}>
                        Ordered chronologically in UTC
                      </div>
                    </div>
                    <div style={{ color: '#475569', fontSize: '0.9rem', fontWeight: 600 }}>
                      {evidence.length} item{evidence.length === 1 ? '' : 's'}
                    </div>
                  </div>

                  {evidence.length === 0 ? (
                    <div
                      style={{
                        padding: '1.25rem',
                        textAlign: 'center',
                        color: '#475569',
                        backgroundColor: '#f8fafc',
                        border: '1px dashed #cbd5e1',
                        borderRadius: '12px',
                      }}
                    >
                      No evidence has been attached to this case yet.
                    </div>
                  ) : (
                    <div style={{ display: 'grid', gap: '0.9rem' }}>
                      {evidence.map((item, index) => {
                        const alertType =
                          item.data && typeof item.data.alert_type === 'string'
                            ? item.data.alert_type
                            : null;
                        const explanation =
                          item.data && typeof item.data.explanation === 'string'
                            ? item.data.explanation
                            : null;

                        return (
                          <article
                            key={item.id ?? `${item.evidence_type ?? 'evidence'}-${index}`}
                            style={{
                              padding: '1rem',
                              backgroundColor: '#f8fafc',
                              border: '1px solid #e2e8f0',
                              borderRadius: '14px',
                            }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'flex-start',
                                gap: '0.75rem',
                                flexWrap: 'wrap',
                                marginBottom: '0.75rem',
                              }}
                            >
                              <div>
                                <div
                                  style={{
                                    fontSize: '1rem',
                                    fontWeight: 700,
                                    color: '#0f172a',
                                    marginBottom: '0.25rem',
                                  }}
                                >
                                  {formatText(item.evidence_type)}
                                </div>
                                <div style={{ color: '#475569', fontSize: '0.92rem' }}>
                                  Provenance: {formatText(item.provenance)}
                                </div>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                                {alertType ? (
                                  <span
                                    style={{
                                      display: 'inline-flex',
                                      alignItems: 'center',
                                      borderRadius: '999px',
                                      padding: '0.25rem 0.55rem',
                                      fontSize: '0.75rem',
                                      fontWeight: 700,
                                      color: '#1d4ed8',
                                      backgroundColor: '#dbeafe',
                                      border: '1px solid #bfdbfe',
                                    }}
                                  >
                                    {alertType}
                                  </span>
                                ) : null}
                                <div style={{ color: '#64748b', fontSize: '0.85rem' }}>
                                  {formatUtcDate(item.created_at)}
                                </div>
                              </div>
                            </div>

                            {explanation ? (
                              <p style={{ margin: 0, lineHeight: 1.7, color: '#334155' }}>
                                {explanation}
                              </p>
                            ) : null}
                          </article>
                        );
                      })}
                    </div>
                  )}
                </section>
              </div>
            );
          })()
        )}
      </div>
    </main>
  );
}
