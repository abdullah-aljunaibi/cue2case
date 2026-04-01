// Server-rendered Cue2Case queue page with dense analyst triage, filters, and sorting.
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
  rank_score?: number | null;
  confidence_score?: number | null;
  priority?: number | null;
  status?: string | null;
  evidence_count?: number | null;
  summary?: string | null;
  recommended_action?: string | null;
  start_observed_at?: string | null;
  end_observed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type CasesResponse = CaseItem[] | { items?: CaseItem[] | null };

type SearchParams = {
  status?: string;
  severity?: string;
  sort?: string;
};

type Severity = 'Critical' | 'High' | 'Medium' | 'Low';

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
    return '—';
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  return (
    new Intl.DateTimeFormat('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'UTC',
    }).format(date) + ' UTC'
  );
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

function normalizeText(value?: string | null) {
  return value && value.trim().length > 0 ? value.trim() : '';
}

function getSeverity(rankScore?: number | null): Severity {
  const score = typeof rankScore === 'number' && !Number.isNaN(rankScore) ? rankScore : 0;

  if (score >= 1.2) {
    return 'Critical';
  }

  if (score >= 0.9) {
    return 'High';
  }

  if (score >= 0.6) {
    return 'Medium';
  }

  return 'Low';
}

function getSeverityStyles(severity: Severity) {
  switch (severity) {
    case 'Critical':
      return { backgroundColor: '#fee2e2', borderColor: '#fca5a5', color: '#991b1b' };
    case 'High':
      return { backgroundColor: '#ffedd5', borderColor: '#fdba74', color: '#9a3412' };
    case 'Medium':
      return { backgroundColor: '#fef3c7', borderColor: '#fcd34d', color: '#92400e' };
    default:
      return { backgroundColor: '#e0f2fe', borderColor: '#7dd3fc', color: '#075985' };
  }
}

function getDetectorSummary(item: CaseItem) {
  const title = normalizeText(item.title);
  const summary = normalizeText(item.summary);
  const source = summary || title;

  if (!source) {
    return 'No detector summary available';
  }

  return source.length > 120 ? `${source.slice(0, 117)}...` : source;
}

function getTimeWindow(item: CaseItem) {
  const start = formatUtcDate(item.start_observed_at);
  const end = formatUtcDate(item.end_observed_at);

  if (start === '—' && end === '—') {
    return '—';
  }

  return `${start} → ${end}`;
}

async function getCases() {
  const endpoint = `${apiUrl}/cases?limit=50&offset=0`;

  const response = await fetch(endpoint, { cache: 'no-store' });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as CasesResponse;
  return asCases(payload);
}

function getStatusOptions(cases: CaseItem[]) {
  return Array.from(
    new Set(
      cases
        .map((item) => normalizeText(item.status))
        .filter((status) => status.length > 0)
    )
  ).sort((left, right) => left.localeCompare(right));
}

function buildHref(status: string, severity: string, sort: string) {
  const params = new URLSearchParams();

  if (status !== 'all') {
    params.set('status', status);
  }

  if (severity !== 'all') {
    params.set('severity', severity);
  }

  if (sort !== 'rank') {
    params.set('sort', sort);
  }

  const query = params.toString();
  return query ? `/?${query}` : '/';
}

export default async function Page({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  let cases: CaseItem[] = [];
  let errorMessage: string | null = null;

  const resolvedSearchParams = (await searchParams) ?? {};
  const selectedStatus = resolvedSearchParams.status?.trim() || 'all';
  const selectedSeverity = resolvedSearchParams.severity?.trim() || 'all';
  const selectedSort = resolvedSearchParams.sort === 'confidence' ? 'confidence' : 'rank';

  try {
    cases = await getCases();
  } catch (error) {
    errorMessage =
      error instanceof Error ? error.message : 'Unknown error while loading cases.';
  }

  const statusOptions = getStatusOptions(cases);

  const filteredCases = cases
    .filter((item) => {
      if (selectedStatus === 'all') {
        return true;
      }

      return normalizeText(item.status).toLowerCase() === selectedStatus.toLowerCase();
    })
    .filter((item) => {
      if (selectedSeverity === 'all') {
        return true;
      }

      return getSeverity(item.rank_score).toLowerCase() === selectedSeverity.toLowerCase();
    })
    .sort((left, right) => {
      const leftValue =
        selectedSort === 'confidence' ? left.confidence_score ?? -1 : left.rank_score ?? -1;
      const rightValue =
        selectedSort === 'confidence' ? right.confidence_score ?? -1 : right.rank_score ?? -1;

      return rightValue - leftValue;
    });

  const totalCases = filteredCases.length;
  const criticalHighCount = filteredCases.filter((item) => {
    const severity = getSeverity(item.rank_score);
    return severity === 'Critical' || severity === 'High';
  }).length;

  const rankedCases = filteredCases.filter(
    (item) => typeof item.rank_score === 'number' && !Number.isNaN(item.rank_score)
  );
  const confidenceCases = filteredCases.filter(
    (item) =>
      typeof item.confidence_score === 'number' && !Number.isNaN(item.confidence_score)
  );

  const averageRank =
    rankedCases.length > 0
      ? rankedCases.reduce((sum, item) => sum + (item.rank_score ?? 0), 0) / rankedCases.length
      : null;
  const averageConfidence =
    confidenceCases.length > 0
      ? confidenceCases.reduce((sum, item) => sum + (item.confidence_score ?? 0), 0) /
        confidenceCases.length
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
      <div style={{ maxWidth: '1440px', margin: '0 auto' }}>
        <header
          style={{
            marginBottom: '1rem',
            padding: '1.25rem 1.5rem',
            backgroundColor: '#ffffff',
            border: '1px solid #dbe3f0',
            borderRadius: '16px',
            boxShadow: '0 8px 24px rgba(15, 23, 42, 0.06)',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              gap: '1rem',
              flexWrap: 'wrap',
              alignItems: 'flex-start',
            }}
          >
            <div>
              <h1 style={{ margin: '0 0 0.35rem', fontSize: '1.9rem' }}>Cue2Case</h1>
              <p style={{ margin: 0, color: '#475569', fontSize: '0.98rem' }}>
                Dense analyst queue for ranked maritime anomaly triage
              </p>
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.9rem',
                flexWrap: 'wrap',
              }}
            >
              <Link
                href="/map"
                style={{
                  color: '#1d4ed8',
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  textDecoration: 'none',
                }}
              >
                Map view →
              </Link>
              <Link
                href="/external-cues"
                style={{
                  color: '#1d4ed8',
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  textDecoration: 'none',
                }}
              >
                External cues →
              </Link>
            </div>
          </div>
          <div style={{ fontSize: '0.85rem', color: '#64748b', marginTop: '0.75rem' }}>
            API URL: {apiUrl} · Queue source sorted by rank score
          </div>
        </header>

        {errorMessage ? (
          <section
            style={{
              marginBottom: '1rem',
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
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '0.75rem',
            marginBottom: '1rem',
          }}
        >
          {[
            { label: 'Total cases shown', value: String(totalCases) },
            { label: 'Critical / High', value: String(criticalHighCount) },
            { label: 'Average rank', value: averageRank === null ? '—' : averageRank.toFixed(3) },
            {
              label: 'Average confidence',
              value: averageConfidence === null ? '—' : averageConfidence.toFixed(3),
            },
          ].map((metric) => (
            <div
              key={metric.label}
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #dbe3f0',
                borderRadius: '14px',
                padding: '0.9rem 1rem',
                boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
              }}
            >
              <div style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: '0.25rem' }}>
                {metric.label}
              </div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{metric.value}</div>
            </div>
          ))}
        </section>

        <section
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid #dbe3f0',
            borderRadius: '16px',
            padding: '1rem',
            marginBottom: '1rem',
            boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
          }}
        >
          <div
            style={{
              display: 'flex',
              gap: '0.75rem',
              flexWrap: 'wrap',
              alignItems: 'center',
            }}
          >
            <span style={{ fontSize: '0.88rem', color: '#475569', fontWeight: 700 }}>Filters:</span>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {[
                { label: 'All status', value: 'all' },
                ...statusOptions.map((status) => ({ label: status, value: status })),
              ].map((option) => {
                const active = selectedStatus.toLowerCase() === option.value.toLowerCase();
                return (
                  <Link
                    key={`status-${option.value}`}
                    href={buildHref(option.value, selectedSeverity, selectedSort)}
                    style={{
                      padding: '0.45rem 0.7rem',
                      borderRadius: '999px',
                      textDecoration: 'none',
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      border: active ? '1px solid #1d4ed8' : '1px solid #cbd5e1',
                      backgroundColor: active ? '#dbeafe' : '#ffffff',
                      color: active ? '#1d4ed8' : '#334155',
                    }}
                  >
                    {option.label}
                  </Link>
                );
              })}
            </div>
          </div>
          <div
            style={{
              display: 'flex',
              gap: '0.75rem',
              flexWrap: 'wrap',
              alignItems: 'center',
              marginTop: '0.75rem',
            }}
          >
            <span style={{ fontSize: '0.88rem', color: '#475569', fontWeight: 700 }}>
              Severity:
            </span>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {['all', 'Critical', 'High', 'Medium', 'Low'].map((severity) => {
                const active = selectedSeverity.toLowerCase() === severity.toLowerCase();
                return (
                  <Link
                    key={`severity-${severity}`}
                    href={buildHref(selectedStatus, severity, selectedSort)}
                    style={{
                      padding: '0.45rem 0.7rem',
                      borderRadius: '999px',
                      textDecoration: 'none',
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      border: active ? '1px solid #1d4ed8' : '1px solid #cbd5e1',
                      backgroundColor: active ? '#dbeafe' : '#ffffff',
                      color: active ? '#1d4ed8' : '#334155',
                    }}
                  >
                    {severity === 'all' ? 'All severity' : severity}
                  </Link>
                );
              })}
            </div>
            <span
              style={{
                fontSize: '0.88rem',
                color: '#475569',
                fontWeight: 700,
                marginLeft: '0.5rem',
              }}
            >
              Sort:
            </span>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {[
                { label: 'Rank', value: 'rank' },
                { label: 'Confidence', value: 'confidence' },
              ].map((sort) => {
                const active = selectedSort === sort.value;
                return (
                  <Link
                    key={`sort-${sort.value}`}
                    href={buildHref(selectedStatus, selectedSeverity, sort.value)}
                    style={{
                      padding: '0.45rem 0.7rem',
                      borderRadius: '999px',
                      textDecoration: 'none',
                      fontSize: '0.85rem',
                      fontWeight: 700,
                      border: active ? '1px solid #0f172a' : '1px solid #cbd5e1',
                      backgroundColor: active ? '#e2e8f0' : '#ffffff',
                      color: '#0f172a',
                    }}
                  >
                    {sort.label}
                  </Link>
                );
              })}
            </div>
          </div>
        </section>

        {filteredCases.length === 0 ? (
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
            No cases match the current filters.
          </section>
        ) : (
          <section
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #dbe3f0',
              borderRadius: '16px',
              overflowX: 'auto',
              boxShadow: '0 10px 30px rgba(15, 23, 42, 0.05)',
            }}
          >
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1220px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', textAlign: 'left' }}>
                  {[
                    'Severity',
                    'Vessel',
                    'MMSI',
                    'Rank',
                    'Confidence',
                    'Detector summary',
                    'Time window',
                    'Status',
                    'Evidence',
                    'Case',
                  ].map((label) => (
                    <th
                      key={label}
                      style={{
                        padding: '0.85rem 0.9rem',
                        borderBottom: '1px solid #dbe3f0',
                        fontSize: '0.78rem',
                        letterSpacing: '0.04em',
                        textTransform: 'uppercase',
                        color: '#64748b',
                      }}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredCases.map((item, index) => {
                  const rowKey = item.id ?? `${item.title ?? 'case'}-${index}`;
                  const severity = getSeverity(item.rank_score);
                  const severityStyles = getSeverityStyles(severity);

                  return (
                    <tr key={rowKey} style={{ borderBottom: '1px solid #e2e8f0' }}>
                      <td style={{ padding: '0.9rem' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            padding: '0.3rem 0.55rem',
                            borderRadius: '999px',
                            fontSize: '0.78rem',
                            fontWeight: 700,
                            border: `1px solid ${severityStyles.borderColor}`,
                            backgroundColor: severityStyles.backgroundColor,
                            color: severityStyles.color,
                          }}
                        >
                          {severity}
                        </span>
                      </td>
                      <td style={{ padding: '0.9rem', fontWeight: 700, color: '#0f172a' }}>
                        {formatText(item.vessel_name)}
                      </td>
                      <td style={{ padding: '0.9rem', color: '#334155' }}>{item.mmsi ?? '—'}</td>
                      <td style={{ padding: '0.9rem', fontVariantNumeric: 'tabular-nums' }}>
                        {formatScore(item.rank_score)}
                      </td>
                      <td style={{ padding: '0.9rem', fontVariantNumeric: 'tabular-nums' }}>
                        {formatScore(item.confidence_score)}
                      </td>
                      <td style={{ padding: '0.9rem', color: '#334155', lineHeight: 1.4 }}>
                        <div style={{ fontWeight: 600, marginBottom: '0.2rem' }}>
                          {formatText(item.title)}
                        </div>
                        <div style={{ fontSize: '0.9rem', color: '#475569' }}>
                          {getDetectorSummary(item)}
                        </div>
                      </td>
                      <td style={{ padding: '0.9rem', color: '#334155', minWidth: '220px' }}>
                        {getTimeWindow(item)}
                      </td>
                      <td style={{ padding: '0.9rem' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            padding: '0.3rem 0.55rem',
                            borderRadius: '999px',
                            fontSize: '0.8rem',
                            fontWeight: 700,
                            backgroundColor: '#f8fafc',
                            border: '1px solid #cbd5e1',
                            color: '#334155',
                          }}
                        >
                          {formatText(item.status)}
                        </span>
                      </td>
                      <td
                        style={{
                          padding: '0.9rem',
                          fontWeight: 700,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {item.evidence_count ?? '—'}
                      </td>
                      <td style={{ padding: '0.9rem' }}>
                        {item.id !== undefined && item.id !== null ? (
                          <Link
                            href={`/cases/${item.id}`}
                            style={{
                              color: '#1d4ed8',
                              fontWeight: 700,
                              textDecoration: 'none',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            Open →
                          </Link>
                        ) : (
                          <span style={{ color: '#94a3b8' }}>—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        )}
      </div>
    </main>
  );
}
