// Server-rendered Cue2Case landing page that fetches and displays the ranked case queue.
import Link from 'next/link';

const apiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

type CaseItem = {
  id?: string | number;
  title?: string | null;
  vessel_name?: string | null;
  mmsi?: string | number | null;
  anomaly_score?: number | null;
  priority?: number | null;
  status?: string | null;
  evidence_count?: number | null;
  summary?: string | null;
  recommended_action?: string | null;
  created_at?: string | null;
};

type CasesResponse = CaseItem[] | { items?: CaseItem[] | null };

function asCases(payload: CasesResponse): CaseItem[] {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (payload && Array.isArray(payload.items)) {
    return payload.items;
  }

  return [];
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

function formatScore(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }

  return value.toFixed(3);
}

function formatText(value?: string | null) {
  return value && value.trim().length > 0 ? value : '—';
}

async function getCases() {
  const endpoint = `${apiUrl}/cases?limit=25&offset=0`;

  const response = await fetch(endpoint, { cache: 'no-store' });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as CasesResponse;
  return asCases(payload);
}

export default async function Page() {
  let cases: CaseItem[] = [];
  let errorMessage: string | null = null;

  try {
    cases = await getCases();
  } catch (error) {
    errorMessage =
      error instanceof Error ? error.message : 'Unknown error while loading cases.';
  }

  const totalCases = cases.length;
  const highPriorityCount = cases.filter((item) => (item.priority ?? 0) >= 3).length;
  const scoredCases = cases.filter(
    (item) => typeof item.anomaly_score === 'number' && !Number.isNaN(item.anomaly_score)
  );
  const averageScore =
    scoredCases.length > 0
      ? scoredCases.reduce((sum, item) => sum + (item.anomaly_score ?? 0), 0) /
        scoredCases.length
      : null;

  return (
    <main
      style={{
        fontFamily: 'Arial, sans-serif',
        backgroundColor: '#f3f6fb',
        color: '#0f172a',
        minHeight: '100vh',
        padding: '2rem',
      }}
    >
      <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
        <header
          style={{
            marginBottom: '1.5rem',
            padding: '1.5rem',
            backgroundColor: '#ffffff',
            border: '1px solid #dbe3f0',
            borderRadius: '16px',
            boxShadow: '0 8px 24px rgba(15, 23, 42, 0.06)',
          }}
        >
          <h1 style={{ margin: '0 0 0.5rem', fontSize: '2rem' }}>Cue2Case</h1>
          <p style={{ margin: '0 0 0.75rem', color: '#475569', fontSize: '1rem' }}>
            Case-first maritime anomaly triage
          </p>
          <div style={{ fontSize: '0.875rem', color: '#64748b' }}>
            API URL: {apiUrl} · Case count: {totalCases}
          </div>
        </header>

        {errorMessage ? (
          <section
            style={{
              marginBottom: '1.5rem',
              padding: '1rem 1.25rem',
              backgroundColor: '#fff1f2',
              border: '1px solid #fecdd3',
              borderRadius: '14px',
              color: '#9f1239',
              boxShadow: '0 4px 12px rgba(159, 18, 57, 0.08)',
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
              Unable to load case queue
            </div>
            <div style={{ fontSize: '0.95rem' }}>
              {errorMessage}. Check API availability and configuration.
            </div>
          </section>
        ) : null}

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '1rem',
            marginBottom: '1.5rem',
          }}
        >
          {[
            { label: 'Total cases shown', value: String(totalCases) },
            { label: 'High priority', value: String(highPriorityCount) },
            {
              label: 'Average anomaly score',
              value: averageScore === null ? '—' : averageScore.toFixed(3),
            },
          ].map((metric) => (
            <div
              key={metric.label}
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #dbe3f0',
                borderRadius: '14px',
                padding: '1rem 1.25rem',
                boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
              }}
            >
              <div style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '0.35rem' }}>
                {metric.label}
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700 }}>{metric.value}</div>
            </div>
          ))}
        </section>

        {cases.length === 0 ? (
          <section
            style={{
              backgroundColor: '#ffffff',
              border: '1px dashed #cbd5e1',
              borderRadius: '16px',
              padding: '2rem',
              textAlign: 'center',
              color: '#475569',
            }}
          >
            No cases available right now.
          </section>
        ) : (
          <section style={{ display: 'grid', gap: '1rem' }}>
            {cases.map((item, index) => {
              const cardKey = item.id ?? `${item.title ?? 'case'}-${index}`;

              return (
                <article
                  key={cardKey}
                  style={{
                    backgroundColor: '#ffffff',
                    border: '1px solid #dbe3f0',
                    borderRadius: '16px',
                    padding: '1.25rem',
                    boxShadow: '0 10px 30px rgba(15, 23, 42, 0.05)',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: '1rem',
                      flexWrap: 'wrap',
                      marginBottom: '0.85rem',
                    }}
                  >
                    <div>
                      <h2 style={{ margin: '0 0 0.35rem', fontSize: '1.25rem' }}>
                        {formatText(item.title)}
                      </h2>
                      <div style={{ color: '#475569', fontSize: '0.95rem' }}>
                        {item.vessel_name ? `${item.vessel_name} · ` : ''}
                        MMSI: {item.mmsi ?? '—'}
                      </div>
                    </div>
                    <div
                      style={{
                        backgroundColor: '#eff6ff',
                        border: '1px solid #bfdbfe',
                        color: '#1d4ed8',
                        borderRadius: '999px',
                        padding: '0.35rem 0.7rem',
                        fontSize: '0.85rem',
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Score {formatScore(item.anomaly_score)}
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                      gap: '0.75rem',
                      marginBottom: '1rem',
                    }}
                  >
                    {[
                      { label: 'Priority', value: item.priority ?? '—' },
                      { label: 'Status', value: formatText(item.status) },
                      { label: 'Evidence', value: item.evidence_count ?? '—' },
                      { label: 'Created', value: formatUtcDate(item.created_at) },
                    ].map((field) => (
                      <div
                        key={field.label}
                        style={{
                          padding: '0.75rem',
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

                  <div style={{ marginBottom: '0.9rem' }}>
                    <div style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '0.25rem' }}>
                      Summary
                    </div>
                    <p style={{ margin: 0, lineHeight: 1.6, color: '#334155' }}>
                      {formatText(item.summary)}
                    </p>
                  </div>

                  <div>
                    <div style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '0.25rem' }}>
                      Recommended action
                    </div>
                    <p style={{ margin: 0, lineHeight: 1.6, color: '#334155' }}>
                      {formatText(item.recommended_action)}
                    </p>
                  </div>

                  {item.id !== undefined && item.id !== null ? (
                    <div style={{ marginTop: '1rem' }}>
                      <Link
                        href={`/cases/${item.id}`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.35rem',
                          padding: '0.8rem 1rem',
                          borderRadius: '12px',
                          backgroundColor: '#0f172a',
                          color: '#ffffff',
                          fontSize: '0.95rem',
                          fontWeight: 700,
                          textDecoration: 'none',
                          boxShadow: '0 8px 24px rgba(15, 23, 42, 0.14)',
                        }}
                      >
                        Open case →
                      </Link>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </section>
        )}
      </div>
    </main>
  );
}
