// Server-rendered external cues page that lists ingested cues from the API.
import Link from 'next/link';

type CueItem = {
  id?: string | number;
  source?: string | null;
  cue_type?: string | null;
  observed_at?: string | null;
  lon?: number | null;
  lat?: number | null;
  data?: unknown;
  case_id?: string | number | null;
  created_at?: string | null;
};

type CuesResponse = CueItem[] | { items?: CueItem[] | null };

const apiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

function asCues(payload: CuesResponse): CueItem[] {
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

  return (
    new Intl.DateTimeFormat('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'UTC',
    }).format(date) + ' UTC'
  );
}

function formatCoord(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }

  return value.toFixed(5);
}

function formatJson(value: unknown) {
  if (value === undefined) {
    return '{}';
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '{"error":"Unable to render JSON"}';
  }
}

async function getExternalCues() {
  const endpoint = `${apiUrl}/external-cues?limit=50&offset=0`;
  const response = await fetch(endpoint, { cache: 'no-store' });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as CuesResponse;
  return asCues(payload);
}

export default async function ExternalCuesPage() {
  let cues: CueItem[] = [];
  let errorMessage: string | null = null;

  try {
    cues = await getExternalCues();
  } catch (error) {
    errorMessage =
      error instanceof Error
        ? error.message
        : 'Unknown error while loading external cues.';
  }

  const withCoordinates = cues.filter(
    (item) =>
      typeof item.lon === 'number' &&
      !Number.isNaN(item.lon) &&
      typeof item.lat === 'number' &&
      !Number.isNaN(item.lat)
  ).length;

  const distinctTypes = new Set(
    cues
      .map((item) => item.cue_type?.trim())
      .filter((value): value is string => Boolean(value))
  ).size;

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
          <Link
            href="/"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              marginBottom: '0.85rem',
              color: '#1d4ed8',
              fontSize: '0.95rem',
              fontWeight: 700,
              textDecoration: 'none',
            }}
          >
            ← Back to queue
          </Link>
          <h1 style={{ margin: '0 0 0.4rem', fontSize: '2rem' }}>External Cues</h1>
          <p style={{ margin: 0, color: '#475569', fontSize: '1rem' }}>
            Imagery, tips, RF detections, and other analyst inputs
          </p>
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
              Unable to load external cues
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
            { label: 'Total cues shown', value: String(cues.length) },
            { label: 'With coordinates', value: String(withCoordinates) },
            { label: 'Distinct cue types', value: String(distinctTypes) },
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

        {cues.length === 0 ? (
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
            No external cues available right now.
          </section>
        ) : (
          <section style={{ display: 'grid', gap: '1rem' }}>
            {cues.map((item, index) => {
              const key = item.id ?? `${item.cue_type ?? 'cue'}-${index}`;

              return (
                <article
                  key={key}
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
                      alignItems: 'flex-start',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '0.75rem',
                      marginBottom: '0.85rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          borderRadius: '999px',
                          padding: '0.3rem 0.65rem',
                          fontSize: '0.8rem',
                          fontWeight: 700,
                          backgroundColor: '#eff6ff',
                          border: '1px solid #bfdbfe',
                          color: '#1d4ed8',
                        }}
                      >
                        {item.cue_type && item.cue_type.trim().length > 0
                          ? item.cue_type
                          : 'Unknown type'}
                      </span>
                      <span style={{ color: '#475569', fontSize: '0.95rem' }}>
                        Source: {item.source && item.source.trim().length > 0 ? item.source : '—'}
                      </span>
                    </div>
                    <div style={{ color: '#64748b', fontSize: '0.9rem' }}>
                      Observed: {formatUtcDate(item.observed_at)}
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                      gap: '0.75rem',
                      marginBottom: '0.9rem',
                    }}
                  >
                    {[
                      { label: 'Longitude', value: formatCoord(item.lon) },
                      { label: 'Latitude', value: formatCoord(item.lat) },
                      {
                        label: 'Linked case',
                        value:
                          item.case_id !== undefined && item.case_id !== null
                            ? String(item.case_id)
                            : 'Unlinked',
                      },
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

                  <div>
                    <div style={{ fontSize: '0.85rem', color: '#64748b', marginBottom: '0.35rem' }}>
                      Data
                    </div>
                    <pre
                      style={{
                        margin: 0,
                        padding: '0.9rem',
                        borderRadius: '12px',
                        border: '1px solid #e2e8f0',
                        backgroundColor: '#0b1220',
                        color: '#dbeafe',
                        fontSize: '0.83rem',
                        lineHeight: 1.45,
                        overflowX: 'auto',
                      }}
                    >
                      {formatJson(item.data)}
                    </pre>
                  </div>
                </article>
              );
            })}
          </section>
        )}
      </div>
    </main>
  );
}
