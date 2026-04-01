// Server-rendered Cue2Case map staging page that summarizes case markers without a map library.
import Link from 'next/link';

const apiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://localhost:8000';

type MapCaseItem = {
  case_id?: string | number | null;
  id?: string | number | null;
  title?: string | null;
  anomaly_score?: number | null;
  priority?: number | string | null;
  mmsi?: string | number | null;
  vessel_name?: string | null;
  lon?: number | string | null;
  lat?: number | string | null;
};

type MapCasesResponse = MapCaseItem[] | { items?: MapCaseItem[] | null };

function asCases(payload: MapCasesResponse): MapCaseItem[] {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (payload && Array.isArray(payload.items)) {
    return payload.items;
  }

  return [];
}

function formatText(value?: string | null) {
  return value && value.trim().length > 0 ? value : '—';
}

function formatScore(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }

  return value.toFixed(3);
}

function parseCoordinate(value?: number | string | null) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }

  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function formatCoordinate(value: number | null) {
  if (value === null) {
    return '—';
  }

  return value.toFixed(4);
}

async function getMapCases() {
  const endpoint = `${apiUrl}/map/cases`;
  const response = await fetch(endpoint, { cache: 'no-store' });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as MapCasesResponse;
  return asCases(payload);
}

export default async function MapPage() {
  let cases: MapCaseItem[] = [];
  let errorMessage: string | null = null;

  try {
    cases = await getMapCases();
  } catch (error) {
    errorMessage =
      error instanceof Error ? error.message : 'Unknown error while loading map cases.';
  }

  const normalizedCases = cases.map((item) => {
    const lon = parseCoordinate(item.lon);
    const lat = parseCoordinate(item.lat);
    const caseId = item.case_id ?? item.id ?? null;

    return {
      ...item,
      caseId,
      lon,
      lat,
      hasCoordinates: lon !== null && lat !== null,
    };
  });

  const totalMarkers = normalizedCases.length;
  const markersWithCoordinates = normalizedCases.filter((item) => item.hasCoordinates);
  const missingCoordinatesCount = totalMarkers - markersWithCoordinates.length;
  const previewMarkers = markersWithCoordinates.slice(0, 10);

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
      <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
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
          <h1 style={{ margin: '0 0 0.4rem', fontSize: '2rem' }}>Cue2Case Map View</h1>
          <p style={{ margin: 0, color: '#475569', fontSize: '1rem' }}>
            Spatial case staging view
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
              Unable to load map cases
            </div>
            <div style={{ fontSize: '0.95rem' }}>
              {errorMessage}. Check API availability and configuration.
            </div>
          </section>
        ) : null}

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 0.9fr)',
            gap: '1.5rem',
            alignItems: 'start',
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #dbe3f0',
              borderRadius: '16px',
              padding: '1.25rem',
              boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
            }}
          >
            <div style={{ marginBottom: '1rem' }}>
              <h2 style={{ margin: '0 0 0.3rem', fontSize: '1.25rem' }}>Case markers</h2>
              <p style={{ margin: 0, color: '#64748b', fontSize: '0.92rem' }}>
                Case-level marker candidates from the spatial API payload.
              </p>
            </div>

            {normalizedCases.length === 0 ? (
              <div
                style={{
                  border: '1px dashed #cbd5e1',
                  borderRadius: '14px',
                  padding: '1.5rem',
                  textAlign: 'center',
                  color: '#475569',
                  backgroundColor: '#f8fafc',
                }}
              >
                No map cases available right now.
              </div>
            ) : (
              <div style={{ display: 'grid', gap: '0.85rem' }}>
                {normalizedCases.map((item, index) => {
                  const key = item.caseId ?? `${item.title ?? 'marker'}-${index}`;

                  return (
                    <article
                      key={key}
                      style={{
                        border: '1px solid #e2e8f0',
                        borderRadius: '14px',
                        padding: '1rem',
                        backgroundColor: '#f8fafc',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          gap: '0.75rem',
                          alignItems: 'flex-start',
                          flexWrap: 'wrap',
                          marginBottom: '0.75rem',
                        }}
                      >
                        <div>
                          <h3 style={{ margin: '0 0 0.3rem', fontSize: '1.05rem' }}>
                            {formatText(item.title)}
                          </h3>
                          <div style={{ color: '#475569', fontSize: '0.92rem' }}>
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
                            padding: '0.3rem 0.7rem',
                            fontSize: '0.82rem',
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
                          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                          gap: '0.75rem',
                          marginBottom: '0.85rem',
                        }}
                      >
                        <div
                          style={{
                            padding: '0.75rem',
                            backgroundColor: '#ffffff',
                            border: '1px solid #e2e8f0',
                            borderRadius: '12px',
                          }}
                        >
                          <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.2rem' }}>
                            Priority
                          </div>
                          <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>
                            {item.priority ?? '—'}
                          </div>
                        </div>
                        <div
                          style={{
                            padding: '0.75rem',
                            backgroundColor: '#ffffff',
                            border: '1px solid #e2e8f0',
                            borderRadius: '12px',
                          }}
                        >
                          <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.2rem' }}>
                            Coordinates
                          </div>
                          <div style={{ fontSize: '0.95rem', fontWeight: 600 }}>
                            {item.hasCoordinates
                              ? `${formatCoordinate(item.lon)}, ${formatCoordinate(item.lat)}`
                              : 'No coordinates'}
                          </div>
                        </div>
                      </div>

                      {item.caseId !== null ? (
                        <Link
                          href={`/cases/${item.caseId}`}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            color: '#1d4ed8',
                            fontSize: '0.92rem',
                            fontWeight: 700,
                            textDecoration: 'none',
                          }}
                        >
                          Open case →
                        </Link>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gap: '1rem' }}>
            <section
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #dbe3f0',
                borderRadius: '16px',
                padding: '1.25rem',
                boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
              }}
            >
              <h2 style={{ margin: '0 0 0.8rem', fontSize: '1.25rem' }}>Map canvas placeholder</h2>
              <div
                style={{
                  minHeight: '280px',
                  border: '2px dashed #94a3b8',
                  borderRadius: '16px',
                  backgroundColor: '#f8fafc',
                  padding: '1.25rem',
                  display: 'grid',
                  alignContent: 'start',
                  gap: '0.85rem',
                }}
              >
                <div style={{ fontSize: '2rem', fontWeight: 700 }}>{totalMarkers}</div>
                <div style={{ color: '#334155', lineHeight: 1.6 }}>
                  <div>Total marker count: {totalMarkers}</div>
                  <div>Count with coordinates: {markersWithCoordinates.length}</div>
                  <div>Count missing coordinates: {missingCoordinatesCount}</div>
                </div>
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: '12px',
                    backgroundColor: '#e0f2fe',
                    border: '1px solid #bae6fd',
                    color: '#0f172a',
                    fontWeight: 600,
                  }}
                >
                  Leaflet/Mapbox layer goes here next.
                </div>
              </div>
            </section>

            <section
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #dbe3f0',
                borderRadius: '16px',
                padding: '1.25rem',
                boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
              }}
            >
              <h2 style={{ margin: '0 0 0.8rem', fontSize: '1.1rem' }}>Top coordinates</h2>
              {previewMarkers.length === 0 ? (
                <div
                  style={{
                    border: '1px dashed #cbd5e1',
                    borderRadius: '12px',
                    padding: '1rem',
                    color: '#475569',
                    backgroundColor: '#f8fafc',
                  }}
                >
                  No coordinate-bearing markers available yet.
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.92rem' }}>
                    <thead>
                      <tr style={{ textAlign: 'left', color: '#475569' }}>
                        <th style={{ padding: '0 0 0.75rem', borderBottom: '1px solid #e2e8f0' }}>
                          Title
                        </th>
                        <th style={{ padding: '0 0 0.75rem', borderBottom: '1px solid #e2e8f0' }}>
                          Vessel
                        </th>
                        <th style={{ padding: '0 0 0.75rem', borderBottom: '1px solid #e2e8f0' }}>
                          Lon
                        </th>
                        <th style={{ padding: '0 0 0.75rem', borderBottom: '1px solid #e2e8f0' }}>
                          Lat
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewMarkers.map((item, index) => (
                        <tr key={item.caseId ?? `coord-${index}`}>
                          <td style={{ padding: '0.75rem 0', borderBottom: '1px solid #f1f5f9' }}>
                            {formatText(item.title)}
                          </td>
                          <td style={{ padding: '0.75rem 0', borderBottom: '1px solid #f1f5f9' }}>
                            {formatText(item.vessel_name)}
                          </td>
                          <td style={{ padding: '0.75rem 0', borderBottom: '1px solid #f1f5f9' }}>
                            {formatCoordinate(item.lon)}
                          </td>
                          <td style={{ padding: '0.75rem 0', borderBottom: '1px solid #f1f5f9' }}>
                            {formatCoordinate(item.lat)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
