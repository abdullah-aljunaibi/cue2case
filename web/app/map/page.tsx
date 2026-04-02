// Client-rendered Cue2Case map page for browsing mapped cases and vessel tracks.
'use client';

import 'leaflet/dist/leaflet.css';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';

const apiUrl =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
    ? 'https://cue2case-api.bxb-om.com'
    : 'http://localhost:8000');

type MapCaseItem = {
  case_id?: string | number | null;
  id?: string | number | null;
  title?: string | null;
  anomaly_score?: number | null;
  rank_score?: number | null;
  confidence_score?: number | null;
  priority?: number | string | null;
  status?: string | null;
  mmsi?: string | number | null;
  vessel_name?: string | null;
  lon?: number | string | null;
  lat?: number | string | null;
};

type NormalizedMapCase = MapCaseItem & {
  caseId: string | number | null;
  lon: number | null;
  lat: number | null;
  hasCoordinates: boolean;
};

type MapCasesResponse = MapCaseItem[] | { items?: MapCaseItem[] | null };

type GeoJsonLineString = {
  type?: string;
  coordinates?: number[][];
};

type TrackItem = {
  id?: string | number | null;
  geometry?: GeoJsonLineString | null;
};

type LeafletModule = any;

type MarkerRegistry = Map<string, any>;

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

function getCaseKey(item: { caseId: string | number | null; mmsi?: string | number | null }, index = 0) {
  if (item.caseId !== null) {
    return `case-${item.caseId}`;
  }

  if (item.mmsi !== null && item.mmsi !== undefined) {
    return `mmsi-${item.mmsi}`;
  }

  return `row-${index}`;
}

function getCaseLabel(item: MapCaseItem) {
  if (item.vessel_name && item.vessel_name.trim().length > 0) {
    return item.vessel_name;
  }

  if (item.title && item.title.trim().length > 0) {
    return item.title;
  }

  return 'Untitled case';
}

function normalizeCases(items: MapCaseItem[]): NormalizedMapCase[] {
  return items.map((item) => {
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
}

function flattenTrackCoordinates(tracks: TrackItem[]) {
  const points: [number, number][] = [];

  for (const track of tracks) {
    const coordinates = track.geometry?.coordinates;

    if (!Array.isArray(coordinates)) {
      continue;
    }

    for (const coordinate of coordinates) {
      if (!Array.isArray(coordinate) || coordinate.length < 2) {
        continue;
      }

      const lon = Number(coordinate[0]);
      const lat = Number(coordinate[1]);

      if (Number.isFinite(lat) && Number.isFinite(lon)) {
        points.push([lat, lon]);
      }
    }
  }

  return points;
}

function getMarkerStyle(selected: boolean) {
  return selected
    ? {
        radius: 9,
        color: '#7c2d12',
        weight: 3,
        fillColor: '#fb923c',
        fillOpacity: 0.92,
      }
    : {
        radius: 6,
        color: '#0f172a',
        weight: 2,
        fillColor: '#2563eb',
        fillOpacity: 0.78,
      };
}

export default function MapPage() {
  const [cases, setCases] = useState<NormalizedMapCase[]>([]);
  const [casesError, setCasesError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [trackError, setTrackError] = useState<string | null>(null);
  const [trackLoading, setTrackLoading] = useState(false);

  const mapElementRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const leafletRef = useRef<LeafletModule | null>(null);
  const markersRef = useRef<MarkerRegistry>(new Map());
  const markersLayerRef = useRef<any>(null);
  const trackLayerRef = useRef<any>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadCases() {
      try {
        setCasesError(null);
        const response = await fetch(`${apiUrl}/map/cases`, { cache: 'no-store' });

        if (!response.ok) {
          throw new Error(`API request failed with status ${response.status}`);
        }

        const payload = (await response.json()) as MapCasesResponse;
        const normalizedCases = normalizeCases(asCases(payload));

        if (cancelled) {
          return;
        }

        setCases(normalizedCases);

        const firstSelectable = normalizedCases.find((item) => item.hasCoordinates) ?? normalizedCases[0] ?? null;
        setSelectedKey(firstSelectable ? getCaseKey(firstSelectable) : null);
      } catch (error) {
        if (cancelled) {
          return;
        }

        setCases([]);
        setCasesError(error instanceof Error ? error.message : 'Unknown error while loading map cases.');
      }
    }

    loadCases();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function ensureMap() {
      if (!mapElementRef.current || mapRef.current) {
        return;
      }

      const L = require('leaflet');

      if (cancelled || !mapElementRef.current) {
        return;
      }

      leafletRef.current = L;

      const map = L.map(mapElementRef.current, {
        center: [18, 54],
        zoom: 3,
        zoomControl: true,
      });

      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
      }).addTo(map);

      markersLayerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;
    }

    ensureMap();

    return () => {
      cancelled = true;

      trackLayerRef.current?.remove();
      trackLayerRef.current = null;
      markersLayerRef.current?.clearLayers();
      markersRef.current.clear();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const markersLayer = markersLayerRef.current;

    if (!L || !map || !markersLayer) {
      return;
    }

    markersLayer.clearLayers();
    markersRef.current.clear();

    const coordinateCases = cases.filter((item) => item.hasCoordinates);

    for (const [index, item] of coordinateCases.entries()) {
      const key = getCaseKey(item, index);
      const marker = L.circleMarker([item.lat as number, item.lon as number], getMarkerStyle(key === selectedKey));

      marker.bindTooltip(getCaseLabel(item), {
        direction: 'top',
        offset: [0, -8],
      });

      marker.on('click', () => {
        setSelectedKey(key);
      });

      marker.addTo(markersLayer);
      markersRef.current.set(key, marker);
    }

    if (coordinateCases.length === 0) {
      map.setView([18, 54], 3);
      return;
    }

    const bounds = L.latLngBounds(
      coordinateCases.map((item) => [item.lat as number, item.lon as number] as [number, number]),
    );

    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [28, 28] });
    }
  }, [cases]);

  useEffect(() => {
    for (const [key, marker] of markersRef.current.entries()) {
      marker.setStyle(getMarkerStyle(key === selectedKey));
    }
  }, [selectedKey]);

  const selectedCase = useMemo(
    () => cases.find((item, index) => getCaseKey(item, index) === selectedKey) ?? null,
    [cases, selectedKey],
  );

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;

    if (!L || !map) {
      return;
    }

    trackLayerRef.current?.remove();
    trackLayerRef.current = null;

    if (!selectedCase || selectedCase.mmsi === null || selectedCase.mmsi === undefined) {
      setTrackLoading(false);
      setTrackError(null);
      return;
    }

    const selectedMmsi = String(selectedCase.mmsi);
    let cancelled = false;

    async function loadTrack() {
      try {
        setTrackLoading(true);
        setTrackError(null);

        const response = await fetch(`${apiUrl}/tracks/${encodeURIComponent(selectedMmsi)}`, {
          cache: 'no-store',
        });

        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('Track history is not available for this vessel yet.');
          }

          throw new Error('Unable to load the latest vessel track right now.');
        }

        const payload = (await response.json()) as TrackItem[];

        if (cancelled) {
          return;
        }

        const points = flattenTrackCoordinates(Array.isArray(payload) ? payload : []);

        if (points.length === 0) {
          setTrackLoading(false);
          setTrackError('Track history is not available for this vessel yet.');
          return;
        }

        const polyline = L.polyline(points, {
          color: '#f97316',
          weight: 3,
          opacity: 0.9,
        }).addTo(map);

        trackLayerRef.current = polyline;

        const marker = markersRef.current.get(selectedKey ?? '');
        const markerLatLng = marker ? [marker.getLatLng().lat, marker.getLatLng().lng] : null;
        const combinedPoints = markerLatLng ? [...points, markerLatLng as [number, number]] : points;
        const bounds = L.latLngBounds(combinedPoints);

        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [32, 32] });
        }

        setTrackLoading(false);
      } catch (error) {
        if (cancelled) {
          return;
        }

        setTrackLoading(false);
        setTrackError(
          error instanceof Error ? error.message : 'Unable to load the latest vessel track right now.',
        );
      }
    }

    loadTrack();

    return () => {
      cancelled = true;
    };
  }, [selectedCase, selectedKey]);

  const totalMarkers = cases.length;
  const markersWithCoordinates = cases.filter((item) => item.hasCoordinates);
  const missingCoordinatesCount = totalMarkers - markersWithCoordinates.length;
  const selectedCaseHref = selectedCase?.caseId !== null && selectedCase?.caseId !== undefined ? `/cases/${selectedCase.caseId}` : null;

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
      <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
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
            Review mapped cases, confirm vessel movement, and jump straight into the active case.
          </p>
        </header>

        {casesError ? (
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
            <div style={{ fontWeight: 700, marginBottom: '0.35rem' }}>Unable to load map cases</div>
            <div style={{ fontSize: '0.95rem' }}>
              The map feed is unavailable right now. Queue review can continue once the data service responds.
            </div>
          </section>
        ) : null}

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(320px, 380px) minmax(0, 1fr)',
            gap: '1.25rem',
            alignItems: 'start',
          }}
        >
          <aside
            style={{
              backgroundColor: '#ffffff',
              border: '1px solid #dbe3f0',
              borderRadius: '16px',
              padding: '1rem',
              boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
              display: 'grid',
              gap: '1rem',
              maxHeight: 'calc(100vh - 180px)',
              overflow: 'hidden',
            }}
          >
            <div>
              <h2 style={{ margin: '0 0 0.35rem', fontSize: '1.2rem' }}>Cases</h2>
              <p style={{ margin: 0, color: '#64748b', fontSize: '0.92rem' }}>
                Select a case to center the map, review vessel movement, and continue into case handling.
              </p>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
                gap: '0.65rem',
              }}
            >
              {[
                { label: 'Cases', value: String(totalMarkers) },
                { label: 'Mapped', value: String(markersWithCoordinates.length) },
                { label: 'Missing coords', value: String(missingCoordinatesCount) },
              ].map((item) => (
                <div
                  key={item.label}
                  style={{
                    padding: '0.8rem',
                    border: '1px solid #e2e8f0',
                    borderRadius: '12px',
                    backgroundColor: '#f8fafc',
                  }}
                >
                  <div style={{ fontSize: '0.76rem', color: '#64748b', marginBottom: '0.2rem' }}>{item.label}</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700 }}>{item.value}</div>
                </div>
              ))}
            </div>

            <div
              style={{
                padding: '0.85rem 0.95rem',
                borderRadius: '12px',
                backgroundColor: '#f8fafc',
                border: '1px solid #e2e8f0',
                color: '#475569',
                fontSize: '0.9rem',
                lineHeight: 1.5,
              }}
            >
              Use the map to verify location context and vessel movement before opening the full case record.
            </div>

            <div style={{ display: 'grid', gap: '0.75rem', overflowY: 'auto', paddingRight: '0.25rem' }}>
              {cases.length === 0 ? (
                <div
                  style={{
                    border: '1px dashed #cbd5e1',
                    borderRadius: '14px',
                    padding: '1rem',
                    textAlign: 'center',
                    color: '#475569',
                    backgroundColor: '#f8fafc',
                  }}
                >
                  No mapped cases are ready for review yet.
                </div>
              ) : (
                cases.map((item, index) => {
                  const key = getCaseKey(item, index);
                  const selected = key === selectedKey;

                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setSelectedKey(key)}
                      style={{
                        textAlign: 'left',
                        width: '100%',
                        border: selected ? '1px solid #2563eb' : '1px solid #e2e8f0',
                        borderRadius: '14px',
                        padding: '0.95rem',
                        backgroundColor: selected ? '#eff6ff' : '#ffffff',
                        cursor: 'pointer',
                        boxShadow: selected ? '0 0 0 1px rgba(37, 99, 235, 0.08)' : 'none',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          gap: '0.75rem',
                          alignItems: 'flex-start',
                          marginBottom: '0.6rem',
                        }}
                      >
                        <div>
                          <div style={{ fontWeight: 700, color: '#0f172a', marginBottom: '0.2rem' }}>
                            {getCaseLabel(item)}
                          </div>
                          <div style={{ color: '#475569', fontSize: '0.88rem' }}>{formatText(item.title)}</div>
                        </div>
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            borderRadius: '999px',
                            padding: '0.24rem 0.55rem',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            backgroundColor: selected ? '#dbeafe' : '#f8fafc',
                            border: '1px solid #cbd5e1',
                            color: '#334155',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {formatText(item.status)}
                        </span>
                      </div>

                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
                          gap: '0.45rem',
                          marginBottom: '0.65rem',
                        }}
                      >
                        <div style={{ fontSize: '0.82rem', color: '#475569' }}>
                          <div style={{ color: '#64748b' }}>Rank</div>
                          <div style={{ fontWeight: 700 }}>{formatScore(item.rank_score)}</div>
                        </div>
                        <div style={{ fontSize: '0.82rem', color: '#475569' }}>
                          <div style={{ color: '#64748b' }}>Anomaly</div>
                          <div style={{ fontWeight: 700 }}>{formatScore(item.anomaly_score)}</div>
                        </div>
                        <div style={{ fontSize: '0.82rem', color: '#475569' }}>
                          <div style={{ color: '#64748b' }}>Confidence</div>
                          <div style={{ fontWeight: 700 }}>{formatScore(item.confidence_score)}</div>
                        </div>
                      </div>

                      <div style={{ color: '#475569', fontSize: '0.84rem', lineHeight: 1.5 }}>
                        <div>MMSI: {item.mmsi ?? '—'}</div>
                        <div>
                          Coordinates:{' '}
                          {item.hasCoordinates
                            ? `${formatCoordinate(item.lon)}, ${formatCoordinate(item.lat)}`
                            : 'Awaiting position fix'}
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </aside>

          <div style={{ display: 'grid', gap: '1rem' }}>
            <section
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #dbe3f0',
                borderRadius: '16px',
                padding: '1rem',
                boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: '1rem',
                  flexWrap: 'wrap',
                  marginBottom: '0.9rem',
                }}
              >
                <div>
                  <h2 style={{ margin: '0 0 0.25rem', fontSize: '1.2rem' }}>Operational map</h2>
                  <p style={{ margin: 0, color: '#64748b', fontSize: '0.92rem' }}>
                    Monitor mapped case positions and the latest available vessel route for the selected record.
                  </p>
                </div>
                <div style={{ color: '#475569', fontSize: '0.88rem', textAlign: 'right' }}>
                  <div>Selected: {selectedCase ? getCaseLabel(selectedCase) : 'No case selected'}</div>
                  <div>
                    {trackLoading
                      ? 'Loading vessel track…'
                      : trackError
                        ? 'Track unavailable'
                        : selectedCase
                          ? 'Track shown when available'
                          : 'Select a case to review movement'}
                  </div>
                </div>
              </div>

              <div style={{ position: 'relative' }}>
                <div
                  ref={mapElementRef}
                  style={{
                    height: '68vh',
                    minHeight: '520px',
                    width: '100%',
                    borderRadius: '14px',
                    overflow: 'hidden',
                    border: '1px solid #dbe3f0',
                    backgroundColor: '#dbeafe',
                  }}
                />
                {trackLoading ? (
                  <div
                    style={{
                      position: 'absolute',
                      top: '1rem',
                      right: '1rem',
                      padding: '0.45rem 0.7rem',
                      borderRadius: '999px',
                      backgroundColor: 'rgba(15, 23, 42, 0.8)',
                      color: '#f8fafc',
                      fontSize: '0.82rem',
                      fontWeight: 700,
                      boxShadow: '0 8px 20px rgba(15, 23, 42, 0.18)',
                    }}
                  >
                    Loading track…
                  </div>
                ) : null}
              </div>
            </section>

            <section
              style={{
                backgroundColor: '#ffffff',
                border: '1px solid #dbe3f0',
                borderRadius: '16px',
                padding: '1rem 1.1rem',
                boxShadow: '0 8px 24px rgba(15, 23, 42, 0.04)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '0.75rem',
                  flexWrap: 'wrap',
                  marginBottom: '0.75rem',
                }}
              >
                <h2 style={{ margin: 0, fontSize: '1.05rem' }}>Selection detail</h2>
                {selectedCaseHref ? (
                  <Link
                    href={selectedCaseHref}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderRadius: '999px',
                      padding: '0.6rem 0.95rem',
                      backgroundColor: '#1d4ed8',
                      color: '#ffffff',
                      fontSize: '0.9rem',
                      fontWeight: 700,
                      textDecoration: 'none',
                    }}
                  >
                    Open case →
                  </Link>
                ) : null}
              </div>

              {selectedCase ? (
                <div style={{ display: 'grid', gap: '0.8rem' }}>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                      gap: '0.75rem',
                    }}
                  >
                    {[
                      { label: 'Vessel', value: formatText(selectedCase.vessel_name) },
                      { label: 'Title', value: formatText(selectedCase.title) },
                      { label: 'Status', value: formatText(selectedCase.status) },
                      { label: 'Priority', value: String(selectedCase.priority ?? '—') },
                      { label: 'MMSI', value: String(selectedCase.mmsi ?? '—') },
                      {
                        label: 'Coordinates',
                        value: selectedCase.hasCoordinates
                          ? `${formatCoordinate(selectedCase.lon)}, ${formatCoordinate(selectedCase.lat)}`
                          : 'Awaiting position fix',
                      },
                    ].map((item) => (
                      <div
                        key={item.label}
                        style={{
                          padding: '0.8rem',
                          borderRadius: '12px',
                          border: '1px solid #e2e8f0',
                          backgroundColor: '#f8fafc',
                        }}
                      >
                        <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.22rem' }}>
                          {item.label}
                        </div>
                        <div style={{ fontWeight: 700, color: '#0f172a' }}>{item.value}</div>
                      </div>
                    ))}
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(3, minmax(120px, 1fr))',
                      gap: '0.75rem',
                    }}
                  >
                    {[
                      { label: 'Rank', value: formatScore(selectedCase.rank_score) },
                      { label: 'Anomaly', value: formatScore(selectedCase.anomaly_score) },
                      { label: 'Confidence', value: formatScore(selectedCase.confidence_score) },
                    ].map((item) => (
                      <div
                        key={item.label}
                        style={{
                          padding: '0.85rem',
                          borderRadius: '12px',
                          backgroundColor: '#0f172a',
                          color: '#f8fafc',
                        }}
                      >
                        <div style={{ fontSize: '0.76rem', opacity: 0.72, marginBottom: '0.2rem' }}>
                          {item.label}
                        </div>
                        <div style={{ fontWeight: 700, fontSize: '1rem' }}>{item.value}</div>
                      </div>
                    ))}
                  </div>

                  {trackError ? (
                    <div
                      style={{
                        padding: '0.85rem 0.95rem',
                        backgroundColor: '#fff7ed',
                        border: '1px solid #fdba74',
                        borderRadius: '12px',
                        color: '#9a3412',
                        fontSize: '0.92rem',
                      }}
                    >
                      Vessel movement could not be drawn for this selection. {trackError}
                    </div>
                  ) : null}
                </div>
              ) : (
                <div
                  style={{
                    border: '1px dashed #cbd5e1',
                    borderRadius: '12px',
                    padding: '1rem',
                    color: '#475569',
                    backgroundColor: '#f8fafc',
                  }}
                >
                  Choose a case from the list or click a marker to review details and continue into the case record.
                </div>
              )}
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
