'use client';

// Tactical dark-themed Cue2Case operator view with score breakdown, replay timeline, actions, notes, audit, and map.
import { use, useEffect, useMemo, useRef, useState } from 'react';

const API =
  typeof window !== 'undefined'
    ? window.location.hostname === 'localhost'
      ? 'http://localhost:8000'
      : 'https://cue2case-api.bxb-om.com'
    : 'http://localhost:8000';

const COLORS = {
  bg: '#0c0c0c',
  card: '#1a1a1a',
  border: '#2a2a2a',
  text: '#ffffff',
  muted: '#a0a0a0',
  blue: '#D94436',
  red: '#ef4444',
  yellow: '#f59e0b',
  green: '#4ade80',
  purple: '#D94436',
};

type ScoreComponents = Partial<{
  behavior_severity: number;
  zone_criticality: number;
  cue_corroboration: number;
  identity_risk: number;
  freshness: number;
  uncertainty_penalty: number;
}>;

type ScorePayload = {
  rank_score?: number | null;
  why_now?: string[] | null;
  top_reasons?: string[] | null;
  components?: ScoreComponents | null;
  confidence_explainer?: string | null;
  benign_context?: string | null;
  missing_evidence?: string[] | null;
};

type EvidenceItem = {
  id?: string | number;
  evidence_type?: string | null;
  evidence_ref?: string | null;
  provenance?: string | null;
  observed_at?: string | null;
  created_at?: string | null;
  timeline_order?: number | null;
  data?: Record<string, unknown> | null;
};

type NoteItem = {
  id?: string | number;
  author?: string | null;
  created_by?: string | null;
  body?: string | null;
  note?: string | null;
  content?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type AuditItem = {
  id?: string | number;
  action?: string | null;
  event?: string | null;
  actor?: string | null;
  user?: string | null;
  summary?: string | null;
  details?: unknown;
  created_at?: string | null;
  timestamp?: string | null;
};

type ReplayEvent = {
  timestamp?: string | null;
  event_type?: string | null;
  narrative?: string | null;
  data?: Record<string, unknown> | null;
};

type ReplayPayload = {
  events?: ReplayEvent[] | null;
  track_geojson?: unknown;
  vessel?: Record<string, unknown> | null;
  time_window?: Record<string, unknown> | null;
};

type CasePayload = {
  id?: string | number;
  title?: string | null;
  vessel_name?: string | null;
  mmsi?: string | number | null;
  status?: string | null;
  priority?: number | string | null;
  severity?: string | null;
  summary?: string | null;
  recommended_action?: string | null;
  zone_context?: string | null;
  primary_geom?: unknown;
  evidence?: EvidenceItem[] | null;
  score?: ScorePayload | null;
};

type ActionState = {
  loading: boolean;
  message: string;
  error: boolean;
};

declare global {
  interface Window { L: any; __leafletFailed?: boolean; }
}

type LeafletBounds = {
  isValid?: () => boolean;
};

type LeafletMap = {
  setView: (center: [number, number], zoom: number) => LeafletMap;
  fitBounds: (bounds: LeafletBounds, options?: Record<string, unknown>) => void;
  remove: () => void;
};

function formatText(value?: string | number | null) {
  if (value === null || value === undefined) {
    return '—';
  }

  const text = String(value).trim();
  return text.length ? text : '—';
}

function formatDate(value?: string | null) {
  if (!value) {
    return 'Unknown time';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Invalid time';
  }

  return `${new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date)} UTC`;
}

function formatScore(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '—';
  }

  return value.toFixed(3);
}

function labelize(value: string) {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function asArray<T>(value: T[] | null | undefined) {
  return Array.isArray(value) ? value : [];
}

function noteBody(note: NoteItem) {
  return note.body || note.note || note.content || '—';
}

function noteAuthor(note: NoteItem) {
  return note.author || note.created_by || 'Analyst';
}

function auditLabel(item: AuditItem) {
  return item.action || item.event || 'case_event';
}

function auditActor(item: AuditItem) {
  return item.actor || item.user || 'system';
}

function detailText(value: unknown) {
  if (typeof value === 'string') {
    return value;
  }

  if (value === null || value === undefined) {
    return '';
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function extractCoordinates(primaryGeom: unknown): [number, number] | null {
  if (!primaryGeom || typeof primaryGeom !== 'object') {
    return null;
  }

  const geom = primaryGeom as { type?: string; coordinates?: unknown; geometry?: unknown };
  if (geom.type === 'Point' && Array.isArray(geom.coordinates) && geom.coordinates.length >= 2) {
    const [lng, lat] = geom.coordinates;
    if (typeof lat === 'number' && typeof lng === 'number') {
      return [lat, lng];
    }
  }

  if (geom.geometry) {
    return extractCoordinates(geom.geometry);
  }

  return null;
}

function eventColor(type?: string | null) {
  switch (type) {
    case 'position':
      return COLORS.blue;
    case 'alert':
      return COLORS.red;
    case 'cue':
      return COLORS.yellow;
    case 'note':
      return COLORS.green;
    case 'status_change':
      return COLORS.purple;
    default:
      return COLORS.muted;
  }
}

function eventIcon(type?: string | null) {
  switch (type) {
    case 'position':
      return '◎';
    case 'alert':
      return '⚠';
    case 'cue':
      return '◈';
    case 'note':
      return '✎';
    case 'status_change':
      return '⟳';
    default:
      return '•';
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export default function CaseDetailPage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = use(params);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<LeafletMap | null>(null);

  const [caseData, setCaseData] = useState<CasePayload | null>(null);
  const [replay, setReplay] = useState<ReplayPayload | null>(null);
  const [notes, setNotes] = useState<NoteItem[]>([]);
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [showAllEvents, setShowAllEvents] = useState(false);
  const [dismissReason, setDismissReason] = useState('');
  const [noteDraft, setNoteDraft] = useState('');
  const [briefMarkdown, setBriefMarkdown] = useState('');
  const [actionState, setActionState] = useState<ActionState>({ loading: false, message: '', error: false });
  const [noteState, setNoteState] = useState<ActionState>({ loading: false, message: '', error: false });

  const loadAll = async () => {
    try {
      setLoading(true);
      setLoadError('');
      setCaseData(null);
      setReplay(null);
      setNotes([]);
      setAudit([]);
      setShowAllEvents(false);
      setDismissReason('');
      setNoteDraft('');
      setBriefMarkdown('');
      setActionState({ loading: false, message: '', error: false });
      setNoteState({ loading: false, message: '', error: false });

      // Core case data — must succeed
      const casePayload = await fetchJson<CasePayload>(`${API}/cases/${encodeURIComponent(caseId)}`);
      setCaseData(casePayload);

      // Non-critical data — fetch independently so failures don't block the page
      const [replayPayload, notesPayload, auditPayload] = await Promise.all([
        fetchJson<ReplayPayload>(`${API}/cases/${encodeURIComponent(caseId)}/replay`).catch(() => null),
        fetchJson<NoteItem[] | { notes?: NoteItem[] }>(`${API}/cases/${encodeURIComponent(caseId)}/notes`).catch(() => null),
        fetchJson<AuditItem[] | { audit?: AuditItem[] }>(`${API}/cases/${encodeURIComponent(caseId)}/audit`).catch(() => null),
      ]);

      setReplay(replayPayload);
      const n = notesPayload ? (Array.isArray(notesPayload) ? notesPayload : (notesPayload as any).notes) : [];
      const a = auditPayload ? (Array.isArray(auditPayload) ? auditPayload : (auditPayload as any).audit) : [];

      setNotes(Array.isArray(n) ? n : []);
      setAudit(Array.isArray(a) ? a : []);
    } catch (error) {
      setCaseData(null);
      setLoadError(error instanceof Error ? error.message : 'Failed to load case');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, [caseId]);

  const primaryCoords = useMemo(() => extractCoordinates(caseData?.primary_geom), [caseData?.primary_geom]);

  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    let retryInterval: ReturnType<typeof setInterval> | null = null;

    const initMap = () => {
      if (!mapRef.current) return true;

      if (window.__leafletFailed) {
        setMapError(true);
        return true;
      }

      if (!window.L) {
        return false;
      }

      if (!caseData?.primary_geom && !primaryCoords) {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.remove();
          mapInstanceRef.current = null;
        }
        setMapError(false);
        return true;
      }

      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }

      setMapError(false);

      const map = window.L.map(mapRef.current).setView(primaryCoords || [0, 0], primaryCoords ? 7 : 2);
      mapInstanceRef.current = map;

      window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(map);

      if (caseData?.primary_geom) {
        try {
          const layer = window.L.geoJSON(caseData.primary_geom);
          layer.addTo(map);
          const bounds = layer.getBounds?.();
          if (bounds && bounds.isValid?.()) {
            map.fitBounds(bounds, { padding: [24, 24] });
          } else if (primaryCoords) {
            map.setView(primaryCoords, 8);
          }
        } catch {
          if (primaryCoords) map.setView(primaryCoords, 8);
        }
      } else if (primaryCoords) {
        window.L.marker(primaryCoords).addTo(map);
        map.setView(primaryCoords, 8);
      }

      return true;
    };

    const initialized = initMap();

    if (initialized === false) {
      let attempts = 0;

      retryInterval = setInterval(() => {
        attempts += 1;

        const retryInitialized = initMap();

        if (retryInitialized !== false) {
          if (retryInterval) {
            clearInterval(retryInterval);
            retryInterval = null;
          }
          return;
        }

        if (attempts >= 6) {
          if (retryInterval) {
            clearInterval(retryInterval);
            retryInterval = null;
          }
          setMapError(true);
        }
      }, 500);
    }

    return () => {
      if (retryInterval) {
        clearInterval(retryInterval);
      }
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [caseData?.primary_geom, primaryCoords]);

  const score = caseData?.score || {};
  const whyNow = asArray(score.why_now);
  const topReasons = asArray(score.top_reasons);
  const missingEvidence = asArray(score.missing_evidence);
  const evidence = asArray(caseData?.evidence);
  const events = asArray(replay?.events);
  const visibleEvents = showAllEvents ? events : events.slice(0, 30);
  const components: Array<{ key: keyof ScoreComponents; label: string }> = [
    { key: 'behavior_severity', label: 'Behavior severity' },
    { key: 'zone_criticality', label: 'Zone criticality' },
    { key: 'cue_corroboration', label: 'Cue corroboration' },
    { key: 'identity_risk', label: 'Identity risk' },
    { key: 'freshness', label: 'Freshness' },
    { key: 'uncertainty_penalty', label: 'Uncertainty penalty' },
  ];

  const cueStrip = useMemo(() => {
    const evidenceCueTypes = evidence
      .map((item) => formatText(item.evidence_type))
      .filter((item) => item !== '—')
      .slice(0, 6);

    return [...whyNow, ...evidenceCueTypes].slice(0, 8);
  }, [evidence, whyNow]);

  async function runAction(action: string, extra?: Record<string, unknown>) {
    if (action === 'dismiss' && dismissReason.trim().length === 0) {
      setActionState({ loading: false, message: 'Dismiss requires a reason.', error: true });
      return;
    }

    try {
      setActionState({ loading: true, message: '', error: false });

      const response = await fetch(`${API}/cases/${encodeURIComponent(caseId)}/actions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          actor: 'abdullah',
          ...(action === 'dismiss' ? { reason: dismissReason.trim() } : {}),
          ...(action === 'assign' ? { assignee: 'abdullah' } : {}),
          ...extra,
        }),
      });

      let payload: Record<string, unknown> | null = null;
      try {
        payload = (await response.json()) as Record<string, unknown>;
      } catch {
        payload = null;
      }

      if (!response.ok) {
        throw new Error(
          typeof payload?.detail === 'string'
            ? payload.detail
            : typeof payload?.message === 'string'
              ? payload.message
              : `Action failed: ${response.status}`
        );
      }

      if (action === 'export_brief') {
        const markdown =
          (typeof payload?.markdown === 'string' && payload.markdown) ||
          (typeof payload?.brief_markdown === 'string' && payload.brief_markdown) ||
          (typeof payload?.content === 'string' && payload.content) ||
          (typeof payload?.result === 'string' && payload.result) ||
          'Export completed, but no markdown payload was returned.';
        setBriefMarkdown(markdown);
      }

      if (action === 'dismiss') {
        setDismissReason('');
      }

      setActionState({ loading: false, message: `${labelize(action)} completed.`, error: false });
      await loadAll();
    } catch (error) {
      setActionState({ loading: false, message: error instanceof Error ? error.message : 'Action failed.', error: true });
    }
  }

  async function submitNote() {
    if (noteDraft.trim().length === 0) {
      setNoteState({ loading: false, message: 'Enter a note before submitting.', error: true });
      return;
    }

    try {
      setNoteState({ loading: true, message: '', error: false });
      const response = await fetch(`${API}/cases/${encodeURIComponent(caseId)}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author: 'abdullah', content: noteDraft.trim() }),
      });

      if (!response.ok) {
        throw new Error(`Note submit failed: ${response.status}`);
      }

      setNoteDraft('');
      setNoteState({ loading: false, message: 'Note added.', error: false });
      await loadAll();
    } catch (error) {
      setNoteState({ loading: false, message: error instanceof Error ? error.message : 'Failed to add note.', error: true });
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: COLORS.bg,
        color: COLORS.text,
        padding: '20px',
        fontSize: '13px',
        lineHeight: 1.45,
        fontFamily: 'Inter, Arial, sans-serif',
      }}
    >
      <div style={{ maxWidth: '1600px', margin: '0 auto', display: 'grid', gap: '16px' }}>
        <div
          style={{
            background: COLORS.card,
            border: `1px solid ${COLORS.border}`,
            borderRadius: '14px',
            padding: '16px 18px',
            display: 'grid',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div style={{ display: 'grid', gap: '6px' }}>
              <div style={{ fontSize: '12px', color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.14em' }}>
                Tactical Case View
              </div>
              <div style={{ fontSize: '28px', fontWeight: 700 }}>{formatText(caseData?.title || `Case ${caseId}`)}</div>
              <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', color: COLORS.muted }}>
                <span>MMSI {formatText(caseData?.mmsi)}</span>
                <span>Vessel {formatText(caseData?.vessel_name)}</span>
                <span>Case ID {caseId}</span>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <Badge label={`Status ${formatText(caseData?.status)}`} color={COLORS.blue} />
              <Badge label={`Severity ${formatText(caseData?.severity || caseData?.priority)}`} color={COLORS.red} />
              <Badge label={`Evidence ${evidence.length}`} color={COLORS.green} />
              <Badge label={`Replay ${events.length}`} color={COLORS.purple} />
            </div>
          </div>

          <div style={{ display: 'grid', gap: '8px' }}>
            <div style={{ fontSize: '12px', color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.14em' }}>
              Why now
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {whyNow.length ? (
                whyNow.map((item, index) => <Badge key={`${item}-${index}`} label={item} color={COLORS.yellow} />)
              ) : (
                <span style={{ color: COLORS.muted }}>No active why-now cues.</span>
              )}
            </div>
          </div>
        </div>

        {loading ? (
          <SectionCard title="Loading case">Fetching tactical picture…</SectionCard>
        ) : loadError ? (
          <SectionCard title="Load error">
            <div style={{ color: COLORS.red }}>{loadError}</div>
          </SectionCard>
        ) : (
          <>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 3fr) minmax(320px, 2fr)',
                gap: '16px',
                alignItems: 'start',
              }}
            >
              <div style={{ display: 'grid', gap: '16px' }}>
                <SectionCard title="Score breakdown">
                  <div style={{ display: 'grid', gap: '16px' }}>
                    <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', alignItems: 'center' }}>
                      <div>
                        <div style={{ color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.12em', fontSize: '11px' }}>
                          Rank score
                        </div>
                        <div style={{ fontSize: '34px', fontWeight: 800, color: COLORS.blue }}>{formatScore(score.rank_score)}</div>
                      </div>
                      <div style={{ flex: 1, minWidth: '240px', color: COLORS.muted }}>{formatText(score.confidence_explainer)}</div>
                    </div>

                    <div style={{ display: 'grid', gap: '10px' }}>
                      {components.map(({ key, label }) => {
                        const raw = score.components?.[key];
                        const numeric = typeof raw === 'number' && Number.isFinite(raw) ? raw : 0;
                        const percent = Math.max(0, Math.min(100, numeric <= 1 ? numeric * 100 : numeric));
                        const barColor = key === 'uncertainty_penalty' ? COLORS.red : COLORS.blue;

                        return (
                          <div key={key} style={{ display: 'grid', gap: '6px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                              <span>{label}</span>
                              <span style={{ color: COLORS.muted }}>{typeof raw === 'number' ? raw.toFixed(3) : '—'}</span>
                            </div>
                            <div style={{ height: '10px', background: '#0c0c0c', borderRadius: '999px', overflow: 'hidden', border: `1px solid ${COLORS.border}` }}>
                              <div style={{ width: `${percent}%`, height: '100%', background: barColor, opacity: 0.9 }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {score.benign_context ? (
                      <div style={{ padding: '12px', borderRadius: '10px', background: '#1a1a1a', border: `1px solid ${COLORS.border}`, color: COLORS.muted }}>
                        <div style={{ color: COLORS.green, marginBottom: '6px', fontWeight: 600 }}>Benign context</div>
                        {score.benign_context}
                      </div>
                    ) : null}

                    <div style={{ display: 'grid', gap: '8px' }}>
                      <div style={{ color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.12em', fontSize: '11px' }}>Top reasons</div>
                      {topReasons.length ? (
                        <ul style={{ margin: 0, paddingLeft: '18px', display: 'grid', gap: '6px' }}>
                          {topReasons.map((reason, index) => (
                            <li key={`${reason}-${index}`}>{reason}</li>
                          ))}
                        </ul>
                      ) : (
                        <div style={{ color: COLORS.muted }}>No supporting reasons returned.</div>
                      )}
                    </div>

                    <div style={{ display: 'grid', gap: '8px' }}>
                      <div style={{ color: COLORS.red, textTransform: 'uppercase', letterSpacing: '0.12em', fontSize: '11px' }}>Missing evidence</div>
                      {missingEvidence.length ? (
                        missingEvidence.map((item, index) => (
                          <div
                            key={`${item}-${index}`}
                            style={{
                              padding: '10px 12px',
                              borderRadius: '10px',
                              border: `1px solid rgba(217,68,54,0.35)`,
                              background: 'rgba(217,68,54,0.08)',
                              color: '#ffffff',
                            }}
                          >
                            {item}
                          </div>
                        ))
                      ) : (
                        <div style={{ color: COLORS.muted }}>No missing evidence flagged.</div>
                      )}
                    </div>
                  </div>
                </SectionCard>

                <SectionCard title="Replay timeline" subtitle={`${events.length} events captured`}>
                  <div style={{ display: 'grid', gap: '12px' }}>
                    {visibleEvents.length ? (
                      visibleEvents.map((event, index) => {
                        const color = eventColor(event.event_type);
                        return (
                          <div key={`${event.timestamp || 'event'}-${index}`} style={{ display: 'grid', gridTemplateColumns: '26px 1fr', gap: '10px' }}>
                            <div style={{ display: 'grid', justifyItems: 'center', gap: '4px' }}>
                              <div
                                style={{
                                  width: '22px',
                                  height: '22px',
                                  borderRadius: '999px',
                                  background: '#1a1a1a',
                                  border: `1px solid ${color}`,
                                  color,
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  fontSize: '12px',
                                  fontWeight: 700,
                                }}
                              >
                                {eventIcon(event.event_type)}
                              </div>
                              {index < visibleEvents.length - 1 ? <div style={{ width: '1px', minHeight: '42px', background: COLORS.border }} /> : null}
                            </div>
                            <div style={{ paddingBottom: '8px' }}>
                              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '5px' }}>
                                <span style={{ color: COLORS.muted }}>{formatDate(event.timestamp)}</span>
                                <Badge label={formatText(event.event_type)} color={color} />
                              </div>
                              <div style={{ marginBottom: '6px' }}>{formatText(event.narrative)}</div>
                              {event.data ? (
                                <pre
                                  style={{
                                    margin: 0,
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    padding: '10px',
                                    borderRadius: '8px',
                                    background: '#1a1a1a',
                                    border: `1px solid ${COLORS.border}`,
                                    color: COLORS.muted,
                                    fontSize: '12px',
                                  }}
                                >
                                  {detailText(event.data)}
                                </pre>
                              ) : null}
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div style={{ color: COLORS.muted }}>No replay events returned.</div>
                    )}

                    {events.length > 30 ? (
                      <button
                        type="button"
                        onClick={() => setShowAllEvents((value) => !value)}
                        style={buttonStyle('secondary')}
                      >
                        {showAllEvents ? 'Show first 30' : `Show all ${events.length} events`}
                      </button>
                    ) : null}
                  </div>
                </SectionCard>

                <SectionCard title="Evidence list" subtitle={`${evidence.length} evidence items`}>
                  <div style={{ display: 'grid', gap: '10px' }}>
                    {evidence.length ? (
                      evidence.map((item, index) => (
                        <div
                          key={String(item.id || index)}
                          style={{
                            padding: '12px',
                            borderRadius: '10px',
                            border: `1px solid ${COLORS.border}`,
                            background: '#1a1a1a',
                            display: 'grid',
                            gap: '8px',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                              <Badge label={formatText(item.evidence_type)} color={COLORS.green} />
                              {item.timeline_order !== null && item.timeline_order !== undefined ? (
                                <Badge label={`Order ${item.timeline_order}`} color={COLORS.purple} />
                              ) : null}
                            </div>
                            <div style={{ color: COLORS.muted }}>{formatDate(item.observed_at || item.created_at)}</div>
                          </div>
                          <div style={{ color: COLORS.muted }}>
                            Ref {formatText(item.evidence_ref)} · Source {formatText(item.provenance)}
                          </div>
                          {item.data ? (
                            <pre
                              style={{
                                margin: 0,
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                                padding: '10px',
                                borderRadius: '8px',
                                background: COLORS.bg,
                                border: `1px solid ${COLORS.border}`,
                                color: COLORS.text,
                                fontSize: '12px',
                              }}
                            >
                              {detailText(item.data)}
                            </pre>
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <div style={{ color: COLORS.muted }}>No evidence attached.</div>
                    )}
                  </div>
                </SectionCard>
              </div>

              <div style={{ display: 'grid', gap: '16px' }}>
                <SectionCard title="Operator actions">
                  <div style={{ display: 'grid', gap: '10px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '8px' }}>
                      <button type="button" onClick={() => void runAction('acknowledge')} style={buttonStyle('primary')} disabled={actionState.loading}>
                        Acknowledge
                      </button>
                      <button type="button" onClick={() => void runAction('assign')} style={buttonStyle('primary')} disabled={actionState.loading}>
                        Assign to me
                      </button>
                      <button type="button" onClick={() => void runAction('escalate')} style={buttonStyle('danger')} disabled={actionState.loading}>
                        Escalate
                      </button>
                      <button type="button" onClick={() => void runAction('export_brief')} style={buttonStyle('secondary')} disabled={actionState.loading}>
                        Export brief
                      </button>
                    </div>

                    <div style={{ display: 'grid', gap: '8px', marginTop: '4px' }}>
                      <label style={{ color: COLORS.muted }}>Dismiss reason</label>
                      <input
                        value={dismissReason}
                        onChange={(event) => setDismissReason(event.target.value)}
                        placeholder="Required for dismiss"
                        style={inputStyle}
                      />
                      <button type="button" onClick={() => void runAction('dismiss')} style={buttonStyle('danger')} disabled={actionState.loading}>
                        Dismiss
                      </button>
                    </div>

                    {actionState.message ? (
                      <div
                        style={{
                          padding: '10px 12px',
                          borderRadius: '10px',
                          border: `1px solid ${actionState.error ? 'rgba(217,68,54,0.4)' : 'rgba(74,222,128,0.4)'}`,
                          background: actionState.error ? 'rgba(217,68,54,0.08)' : 'rgba(74,222,128,0.08)',
                          color: actionState.error ? '#ffffff' : '#ffffff',
                        }}
                      >
                        {actionState.loading ? 'Working… ' : ''}
                        {actionState.message}
                      </div>
                    ) : null}

                    {briefMarkdown ? (
                      <div style={{ display: 'grid', gap: '8px' }}>
                        <div style={{ color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.12em', fontSize: '11px' }}>
                          Exported brief
                        </div>
                        <pre
                          style={{
                            margin: 0,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            padding: '12px',
                            borderRadius: '10px',
                            background: '#1a1a1a',
                            border: `1px solid ${COLORS.border}`,
                            maxHeight: '320px',
                            overflow: 'auto',
                          }}
                        >
                          {briefMarkdown}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                </SectionCard>

                <SectionCard title="Notes">
                  <div style={{ display: 'grid', gap: '10px' }}>
                    <textarea
                      value={noteDraft}
                      onChange={(event) => setNoteDraft(event.target.value)}
                      placeholder="Add analyst note"
                      style={{ ...inputStyle, minHeight: '96px', resize: 'vertical' }}
                    />
                    <button type="button" onClick={() => void submitNote()} style={buttonStyle('primary')} disabled={noteState.loading}>
                      Submit note
                    </button>
                    {noteState.message ? (
                      <div style={{ color: noteState.error ? COLORS.red : COLORS.green }}>{noteState.message}</div>
                    ) : null}
                    <div style={{ display: 'grid', gap: '10px' }}>
                      {notes.length ? (
                        notes.map((note, index) => (
                          <div key={String(note.id || index)} style={{ padding: '12px', borderRadius: '10px', border: `1px solid ${COLORS.border}`, background: '#1a1a1a' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '6px', flexWrap: 'wrap' }}>
                              <strong>{noteAuthor(note)}</strong>
                              <span style={{ color: COLORS.muted }}>{formatDate(note.created_at || note.updated_at)}</span>
                            </div>
                            <div style={{ whiteSpace: 'pre-wrap' }}>{noteBody(note)}</div>
                          </div>
                        ))
                      ) : (
                        <div style={{ color: COLORS.muted }}>No analyst notes yet.</div>
                      )}
                    </div>
                  </div>
                </SectionCard>

                <SectionCard title="Cue strip">
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                    {cueStrip.length ? cueStrip.map((cue, index) => <Badge key={`${cue}-${index}`} label={cue} color={COLORS.yellow} />) : <span style={{ color: COLORS.muted }}>No cues collected.</span>}
                  </div>
                  <div style={{ color: COLORS.muted, whiteSpace: 'pre-wrap' }}>{formatText(caseData?.zone_context || caseData?.summary)}</div>
                </SectionCard>

                <SectionCard title="Audit trail" subtitle={`${audit.length} records`}>
                  <div style={{ display: 'grid', gap: '8px' }}>
                    {audit.length ? (
                      audit.map((item, index) => (
                        <div key={String(item.id || index)} style={{ padding: '10px 12px', borderRadius: '10px', border: `1px solid ${COLORS.border}`, background: '#1a1a1a' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', marginBottom: '4px' }}>
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                              <Badge label={labelize(auditLabel(item))} color={COLORS.purple} />
                              <span style={{ color: COLORS.muted }}>by {auditActor(item)}</span>
                            </div>
                            <span style={{ color: COLORS.muted }}>{formatDate(item.timestamp || item.created_at)}</span>
                          </div>
                          <div style={{ color: COLORS.text }}>{formatText(item.summary || detailText(item.details))}</div>
                        </div>
                      ))
                    ) : (
                      <div style={{ color: COLORS.muted }}>No audit activity returned.</div>
                    )}
                  </div>
                </SectionCard>
              </div>
            </div>

            <SectionCard title="Map section" subtitle={primaryCoords ? `Lat ${primaryCoords[0].toFixed(4)} · Lon ${primaryCoords[1].toFixed(4)}` : 'No primary geometry available'}>
              {caseData?.primary_geom || primaryCoords ? (
                mapError ? (
                  <div style={{ height: '360px', width: '100%', borderRadius: '12px', border: `1px solid ${COLORS.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.muted, fontSize: '13px', backgroundColor: COLORS.card }}>
                    Map unavailable — Leaflet failed to load
                  </div>
                ) : (
                  <div ref={mapRef} style={{ height: '360px', width: '100%', borderRadius: '12px', overflow: 'hidden', border: `1px solid ${COLORS.border}` }} />
                )
              ) : (
                <div
                  style={{
                    height: '180px',
                    borderRadius: '12px',
                    border: `1px dashed ${COLORS.border}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: COLORS.muted,
                    background: '#1a1a1a',
                  }}
                >
                  No map geometry on this case.
                </div>
              )}
            </SectionCard>
          </>
        )}
      </div>
    </div>
  );
}

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      style={{
        background: COLORS.card,
        border: `1px solid ${COLORS.border}`,
        borderRadius: '14px',
        padding: '14px',
        display: 'grid',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap', alignItems: 'baseline' }}>
        <div style={{ fontSize: '15px', fontWeight: 700 }}>{title}</div>
        {subtitle ? <div style={{ color: COLORS.muted, fontSize: '12px' }}>{subtitle}</div> : null}
      </div>
      {children}
    </section>
  );
}

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '5px 9px',
        borderRadius: '999px',
        border: `1px solid ${color}`,
        color,
        background: '#1a1a1a',
        fontSize: '11px',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        fontWeight: 700,
      }}
    >
      {label}
    </span>
  );
}

function buttonStyle(kind: 'primary' | 'secondary' | 'danger'): React.CSSProperties {
  const palette =
    kind === 'danger'
      ? { border: COLORS.red, text: '#ffffff', background: 'rgba(217,68,54,0.12)' }
      : kind === 'secondary'
        ? { border: COLORS.purple, text: '#ffffff', background: 'rgba(217,68,54,0.12)' }
        : { border: COLORS.blue, text: '#ffffff', background: 'rgba(217,68,54,0.12)' };

  return {
    padding: '10px 12px',
    borderRadius: '10px',
    border: `1px solid ${palette.border}`,
    background: palette.background,
    color: palette.text,
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: 700,
  };
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: '10px',
  border: `1px solid ${COLORS.border}`,
  background: '#1a1a1a',
  color: COLORS.text,
  fontSize: '13px',
  outline: 'none',
  boxSizing: 'border-box',
};
