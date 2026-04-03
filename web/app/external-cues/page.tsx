// Server-rendered external cues page that presents recent analyst-facing cue activity.
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

function hasRawPayload(value: unknown) {
  return value !== undefined && value !== null;
}

async function getExternalCues() {
  const endpoint = `${apiUrl}/external-cues?limit=50&offset=0`;
  const response = await fetch(endpoint, { cache: 'no-store' });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as CuesResponse;
  const parsedCues = asCues(payload);
  return Array.isArray(parsedCues) ? parsedCues : [];
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

  const linkedCases = cues.filter(
    (item) => item.case_id !== undefined && item.case_id !== null
  ).length;

  const distinctTypes = new Set(
    cues
      .map((item) => item.cue_type?.trim())
      .filter((value): value is string => Boolean(value))
  ).size;

  return (
    <main
      style={{
        fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
        backgroundColor: '#0c0c0c',
        color: '#ffffff',
        minHeight: '100vh',
        padding: '2rem',
      }}
    >
      <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
        <header
          style={{
            marginBottom: '1.5rem',
            padding: '1.5rem',
            backgroundColor: '#1a1a1a',
            border: '1px solid #2a2a2a',
            borderRadius: '8px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.06)',
          }}
        >
          <Link
            href="/"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              marginBottom: '0.85rem',
              color: '#D94436',
              fontSize: '0.95rem',
              fontWeight: 700,
              textDecoration: 'none',
            }}
          >
            ← Back to queue
          </Link>
          <h1 style={{ margin: '0 0 0.4rem', fontSize: '2rem' }}>External Cues</h1>
          <p style={{ margin: 0, color: '#666666', fontSize: '1rem', maxWidth: '48rem' }}>
            Recent external reporting and detections available for case review.
          </p>
        </header>

        {errorMessage ? (
          <section
            style={{
              marginBottom: '1.5rem',
              padding: '1rem 1.25rem',
              backgroundColor: '#1a1a1a',
              border: '1px solid #D94436',
              borderRadius: '6px',
              color: '#a0a0a0',
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
            { label: 'Linked to a case', value: String(linkedCases) },
            { label: 'With coordinates', value: String(withCoordinates) },
            { label: 'Distinct cue types', value: String(distinctTypes) },
          ].map((metric) => (
            <div
              key={metric.label}
              style={{
                backgroundColor: '#1a1a1a',
                border: '1px solid #2a2a2a',
                borderRadius: '6px',
                padding: '1rem 1.25rem',
                boxShadow: '0 8px 24px rgba(0, 0, 0, 0.04)',
              }}
            >
              <div style={{ fontSize: '0.85rem', color: '#666666', marginBottom: '0.35rem' }}>
                {metric.label}
              </div>
              <div style={{ fontSize: '1.6rem', fontWeight: 700 }}>{metric.value}</div>
            </div>
          ))}
        </section>

        {cues.length === 0 ? (
          <section
            style={{
              backgroundColor: '#1a1a1a',
              border: '1px dashed #2a2a2a',
              borderRadius: '8px',
              padding: '2rem',
              textAlign: 'center',
              color: '#666666',
            }}
          >
            No external cues available right now.
          </section>
        ) : (
          <section style={{ display: 'grid', gap: '1rem' }}>
            {cues.map((item, index) => {
              const key = item.id ?? `${item.cue_type ?? 'cue'}-${index}`;
              const cueType = item.cue_type && item.cue_type.trim().length > 0 ? item.cue_type : 'Unknown type';
              const source = item.source && item.source.trim().length > 0 ? item.source : 'Unspecified source';
              const linkedCase =
                item.case_id !== undefined && item.case_id !== null ? String(item.case_id) : null;

              return (
                <article
                  key={key}
                  style={{
                    backgroundColor: '#1a1a1a',
                    border: '1px solid #2a2a2a',
                    borderRadius: '8px',
                    padding: '1.25rem',
                    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.05)',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '0.75rem',
                      marginBottom: '1rem',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            borderRadius: '999px',
                            padding: '0.3rem 0.65rem',
                            fontSize: '0.8rem',
                            fontWeight: 700,
                            backgroundColor: 'transparent',
                            border: '1px solid #D94436',
                            color: '#D94436',
                          }}
                        >
                          {cueType}
                        </span>
                        <span style={{ color: '#666666', fontSize: '0.95rem' }}>{source}</span>
                      </div>
                      <div style={{ marginTop: '0.55rem', color: '#ffffff', fontSize: '1rem', fontWeight: 700 }}>
                        Observed {formatUtcDate(item.observed_at)}
                      </div>
                    </div>

                    {linkedCase ? (
                      <Link
                        href={`/cases/${linkedCase}`}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.35rem',
                          color: '#D94436',
                          fontSize: '0.95rem',
                          fontWeight: 700,
                          textDecoration: 'none',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Open case {linkedCase} →
                      </Link>
                    ) : (
                      <span style={{ color: '#666666', fontSize: '0.9rem', fontWeight: 600 }}>
                        Not linked to a case
                      </span>
                    )}
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                      gap: '0.75rem',
                      marginBottom: hasRawPayload(item.data) ? '0.9rem' : 0,
                    }}
                  >
                    {[
                      { label: 'Longitude', value: formatCoord(item.lon) },
                      { label: 'Latitude', value: formatCoord(item.lat) },
                      { label: 'Case status', value: linkedCase ? `Linked to case ${linkedCase}` : 'Awaiting triage' },
                      { label: 'Recorded', value: formatUtcDate(item.created_at) },
                    ].map((field) => (
                      <div
                        key={field.label}
                        style={{
                          padding: '0.85rem',
                          backgroundColor: 'transparent',
                          border: '1px solid #2a2a2a',
                          borderRadius: '12px',
                        }}
                      >
                        <div style={{ fontSize: '0.8rem', color: '#666666', marginBottom: '0.3rem' }}>
                          {field.label}
                        </div>
                        <div style={{ fontSize: '0.98rem', fontWeight: 700, color: '#ffffff' }}>
                          {field.value}
                        </div>
                      </div>
                    ))}
                  </div>

                  {hasRawPayload(item.data) ? (
                    <div>
                      <div
                        style={{
                          fontSize: '0.8rem',
                          color: '#a0a0a0',
                          marginBottom: '0.35rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                        }}
                      >
                        Source payload
                      </div>
                      <pre
                        style={{
                          margin: 0,
                          padding: '0.85rem',
                          borderRadius: '12px',
                          border: '1px solid #2a2a2a',
                          backgroundColor: 'transparent',
                          color: '#666666',
                          fontSize: '0.78rem',
                          lineHeight: 1.45,
                          maxHeight: '300px',
                          overflow: 'auto',
                          overflowX: 'auto',
                        }}
                      >
                        {formatJson(item.data)}
                      </pre>
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
