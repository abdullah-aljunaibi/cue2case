import Link from 'next/link';

const apiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

type CaseItem = {
  id?: string;
  title?: string | null;
  vessel_name?: string | null;
  mmsi?: string | null;
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
  zone_context?: Record<string, unknown> | null;
};

type SearchParams = { status?: string; sort?: string };

function getSeverity(rank: number | null | undefined): { label: string; color: string; bg: string } {
  const r = rank ?? 0;
  if (r >= 1.4) return { label: 'CRITICAL', color: '#fca5a5', bg: '#7f1d1d' };
  if (r >= 1.0) return { label: 'HIGH', color: '#fdba74', bg: '#7c2d12' };
  if (r >= 0.6) return { label: 'MEDIUM', color: '#fde68a', bg: '#713f12' };
  return { label: 'LOW', color: '#86efac', bg: '#14532d' };
}

function getStatusStyle(status: string | null | undefined): { color: string; bg: string } {
  switch (status) {
    case 'new': return { color: '#93c5fd', bg: '#1e3a5f' };
    case 'in_review': return { color: '#fde68a', bg: '#713f12' };
    case 'escalated': return { color: '#fca5a5', bg: '#7f1d1d' };
    case 'resolved': return { color: '#86efac', bg: '#14532d' };
    case 'dismissed': return { color: '#94a3b8', bg: '#1e293b' };
    default: return { color: '#94a3b8', bg: '#1e293b' };
  }
}

function formatTime(value?: string | null) {
  if (!value) return '—';
  const d = new Date(value);
  if (isNaN(d.getTime())) return '—';
  return d.toISOString().slice(11, 16) + ' UTC';
}

function formatDate(value?: string | null) {
  if (!value) return '—';
  const d = new Date(value);
  if (isNaN(d.getTime())) return '—';
  return d.toISOString().slice(0, 10);
}

export default async function QueuePage(props: { searchParams?: Promise<SearchParams> }) {
  const searchParams = props.searchParams ? await props.searchParams : {};
  const statusFilter = searchParams?.status || '';
  const url = statusFilter
    ? `${apiUrl}/cases/?limit=100&status=${encodeURIComponent(statusFilter)}`
    : `${apiUrl}/cases/?limit=100`;
  const countsUrl = `${apiUrl}/cases/?limit=100`;

  let cases: CaseItem[] = [];
  let allCases: CaseItem[] = [];
  let error = '';
  try {
    const [res, countsRes] = await Promise.all([
      fetch(url, { cache: 'no-store' }),
      fetch(countsUrl, { cache: 'no-store' }),
    ]);

    if (!res.ok) {
      throw new Error(`Failed to fetch cases (${res.status})`);
    }

    if (!countsRes.ok) {
      throw new Error(`Failed to fetch case counts (${countsRes.status})`);
    }

    const [data, countsData] = await Promise.all([res.json(), countsRes.json()]);
    cases = Array.isArray(data) ? data : data.items || [];
    allCases = Array.isArray(countsData) ? countsData : countsData.items || [];
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : 'Failed to fetch cases';
  }

  const counts = {
    all: allCases.length,
    new: allCases.filter(c => c.status === 'new').length,
    in_review: allCases.filter(c => c.status === 'in_review').length,
    escalated: allCases.filter(c => c.status === 'escalated').length,
  };

  const tabs = [
    { key: '', label: 'All', count: counts.all },
    { key: 'new', label: 'New', count: counts.new },
    { key: 'in_review', label: 'In Review', count: counts.in_review },
    { key: 'escalated', label: 'Escalated', count: counts.escalated },
  ];

  const badge = (text: string, color: string, bg: string) => ({
    display: 'inline-block' as const,
    padding: '2px 8px',
    borderRadius: '4px',
    fontSize: '11px',
    fontWeight: 600 as const,
    color,
    backgroundColor: bg,
    letterSpacing: '0.3px',
  });

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <h1 style={{ fontSize: '18px', fontWeight: 700, margin: 0, color: '#e0e6f0' }}>
          Case Queue
        </h1>
        <span style={{ color: '#64748b', fontSize: '12px' }}>
          {cases.length} cases • sorted by rank score
        </span>
      </div>

      {/* Status filter tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '16px' }}>
        {tabs.map(tab => {
          const active = statusFilter === tab.key;
          return (
            <Link
              key={tab.key}
              href={tab.key ? `/?status=${tab.key}` : '/'}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 500,
                textDecoration: 'none',
                color: active ? '#e0e6f0' : '#94a3b8',
                backgroundColor: active ? '#1e3a5f' : '#0f1419',
                border: `1px solid ${active ? '#2563eb' : '#1a2338'}`,
                transition: 'all 0.15s',
              }}
            >
              {tab.label} <span style={{ color: '#64748b', marginLeft: '4px' }}>{tab.count}</span>
            </Link>
          );
        })}
      </div>

      {error && (
        <div style={{ padding: '12px', backgroundColor: '#7f1d1d', borderRadius: '6px', color: '#fca5a5', fontSize: '13px', marginBottom: '12px' }}>
          {error}
        </div>
      )}

      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 100px 80px 90px 80px 60px 90px',
        gap: '8px',
        padding: '8px 12px',
        fontSize: '11px',
        color: '#64748b',
        fontWeight: 600,
        textTransform: 'uppercase' as const,
        letterSpacing: '0.5px',
        borderBottom: '1px solid #1a2338',
      }}>
        <span>Case / Vessel</span>
        <span>Severity</span>
        <span>Rank</span>
        <span>Status</span>
        <span>Evidence</span>
        <span>Time</span>
        <span>Action</span>
      </div>

      {/* Case rows */}
      {cases.map((c) => {
        const sev = getSeverity(c.rank_score);
        const st = getStatusStyle(c.status);
        const rankPct = Math.min(100, ((c.rank_score ?? 0) / 2) * 100);

        return (
          <Link
            key={c.id}
            href={`/cases/${c.id}`}
            style={{ textDecoration: 'none', color: 'inherit' }}
          >
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 100px 80px 90px 80px 60px 90px',
              gap: '8px',
              padding: '10px 12px',
              borderBottom: '1px solid #111827',
              cursor: 'pointer',
              transition: 'background-color 0.1s',
              alignItems: 'center',
            }}
              onMouseEnter={undefined}
            >
              {/* Case / Vessel */}
              <div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#e0e6f0', marginBottom: '2px' }}>
                  {c.title || 'Untitled Case'}
                </div>
                <div style={{ fontSize: '11px', color: '#64748b' }}>
                  {c.vessel_name || 'Unknown'} • MMSI {c.mmsi || '—'}
                </div>
              </div>

              {/* Severity */}
              <div>
                <span style={badge(sev.label, sev.color, sev.bg)}>{sev.label}</span>
              </div>

              {/* Rank bar */}
              <div>
                <div style={{ fontSize: '12px', fontWeight: 600, color: sev.color, marginBottom: '2px' }}>
                  {(c.rank_score ?? 0).toFixed(2)}
                </div>
                <div style={{ height: '3px', backgroundColor: '#1a2338', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${rankPct}%`, backgroundColor: sev.color, borderRadius: '2px' }} />
                </div>
              </div>

              {/* Status */}
              <div>
                <span style={badge((c.status || 'new').replace('_', ' ').toUpperCase(), st.color, st.bg)}>
                  {(c.status || 'new').replace('_', ' ').toUpperCase()}
                </span>
              </div>

              {/* Evidence */}
              <div style={{ fontSize: '12px', color: '#94a3b8', textAlign: 'center' }}>
                {c.evidence_count ?? 0}
              </div>

              {/* Time */}
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                {formatTime(c.start_observed_at)}
              </div>

              {/* Action hint */}
              <div style={{ fontSize: '11px', color: '#60a5fa' }}>
                Open →
              </div>
            </div>
          </Link>
        );
      })}

      {cases.length === 0 && !error && (
        <div style={{ textAlign: 'center', padding: '40px', color: '#64748b', fontSize: '14px' }}>
          No cases found{statusFilter ? ` with status "${statusFilter}"` : ''}.
        </div>
      )}
    </div>
  );
}
