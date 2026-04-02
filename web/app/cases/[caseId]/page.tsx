// Server-rendered Cue2Case case detail page with analyst workflow actions, notes, audit, and evidence timeline.
import Link from 'next/link';
import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';


type EvidenceItem = {
  id?: string | number;
  case_id?: string | number;
  evidence_type?: string | null;
  evidence_ref?: string | null;
  provenance?: string | null;
  observed_at?: string | null;
  timeline_order?: number | null;
  created_at?: string | null;
  data?: {
    explanation?: string | null;
    alert_type?: string | null;
    [key: string]: unknown;
  } | null;
};

type NoteItem = {
  id?: string | number;
  body?: string | null;
  note?: string | null;
  content?: string | null;
  author?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type AuditItem = {
  id?: string | number;
  action?: string | null;
  event?: string | null;
  actor?: string | null;
  user?: string | null;
  details?: unknown;
  summary?: string | null;
  created_at?: string | null;
  timestamp?: string | null;
};

type CasePayload = {
  id?: string | number;
  title?: string | null;
  vessel_name?: string | null;
  mmsi?: string | number | null;
  anomaly_score?: number | null;
  rank_score?: number | null;
  confidence_score?: number | null;
  priority?: number | null;
  status?: string | null;
  assigned_to?: string | null;
  summary?: string | null;
  recommended_action?: string | null;
  created_at?: string | null;
  start_observed_at?: string | null;
  end_observed_at?: string | null;
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

function formatObservedWindow(start?: string | null, end?: string | null) {
  if (!start && !end) {
    return 'Unknown window';
  }

  return `${formatUtcDate(start)} → ${formatUtcDate(end)}`;
}

function asEvidence(caseData?: CasePayload | null) {
  return Array.isArray(caseData?.evidence) ? caseData.evidence : [];
}

function asNotes(notes?: NoteItem[] | null) {
  return Array.isArray(notes) ? notes : [];
}

function asAudit(audit?: AuditItem[] | null) {
  return Array.isArray(audit) ? audit : [];
}

async function fetchJson<T>(endpoint: string) {
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
    const payload = (await response.json()) as T;
    return { kind: 'ok' as const, payload };
  } catch {
    return {
      kind: 'error' as const,
      message: 'API returned invalid JSON',
    };
  }
}

async function getCase(caseId: string) {
  return fetchJson<CasePayload>(`${apiUrl}/cases/${encodeURIComponent(caseId)}`);
}

async function getNotes(caseId: string) {
  const result = await fetchJson<NoteItem[] | { notes?: NoteItem[] | null }>(
    `${apiUrl}/cases/${encodeURIComponent(caseId)}/notes`
  );

  if (result.kind !== 'ok') {
    return result;
  }

  const payload = result.payload;
  const notes = Array.isArray(payload) ? payload : asNotes(payload.notes);
  return { kind: 'ok' as const, payload: notes };
}

async function getAudit(caseId: string) {
  const result = await fetchJson<AuditItem[] | { audit?: AuditItem[] | null }>(
    `${apiUrl}/cases/${encodeURIComponent(caseId)}/audit`
  );

  if (result.kind !== 'ok') {
    return result;
  }

  const payload = result.payload;
  const audit = Array.isArray(payload) ? payload : asAudit(payload.audit);
  return { kind: 'ok' as const, payload: audit };
}

async function patchCase(caseId: string, body: Record<string, unknown>) {
  const response = await fetch(`${apiUrl}/cases/${encodeURIComponent(caseId)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`Unable to update case ${caseId}: ${response.status}`);
  }
}

async function postCaseNote(caseId: string, content: string) {
  const response = await fetch(`${apiUrl}/cases/${encodeURIComponent(caseId)}/notes`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      author: 'abdullah',
      content,
    }),
  });

  if (!response.ok) {
    throw new Error(`Unable to create note for case ${caseId}: ${response.status}`);
  }
}

function noteBody(note: NoteItem) {
  return note.body || note.note || note.content || '—';
}

function noteAuthor(note: NoteItem) {
  return note.author || note.created_by || 'Analyst';
}

function auditLabel(entry: AuditItem) {
  return entry.action || entry.event || 'Case event';
}

function auditActor(entry: AuditItem) {
  return entry.actor || entry.user || 'System';
}

function auditDetail(entry: AuditItem) {
  if (typeof entry.details === 'string') {
    const details = entry.details.trim();
    if (details.length > 0) {
      return details;
    }
  }

  if (Array.isArray(entry.details) || (entry.details && typeof entry.details === 'object')) {
    try {
      return JSON.stringify(entry.details, null, 2);
    } catch {
      return String(entry.summary || 'No additional detail provided.');
    }
  }

  if (entry.details != null) {
    return String(entry.details);
  }

  return entry.summary || 'No additional detail provided.';
}

export default async function CaseDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ caseId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { caseId } = await params;
  const resolvedSearchParams = (await searchParams) || {};
  const feedback = Array.isArray(resolvedSearchParams.feedback)
    ? resolvedSearchParams.feedback[0]
    : resolvedSearchParams.feedback;
  const [caseResult, notesResult, auditResult] = await Promise.all([
    getCase(caseId),
    getNotes(caseId),
    getAudit(caseId),
  ]);

  async function updateWorkflow(formData: FormData) {
    'use server';

    const nextStatus = String(formData.get('status') || '').trim();
    const nextAssignee = String(formData.get('assigned_to') || '').trim();
    const payload: Record<string, string> = {};

    if (nextStatus) {
      payload.status = nextStatus;
    }

    if (nextAssignee) {
      payload.assigned_to = nextAssignee;
    }

    if (Object.keys(payload).length === 0) {
      return;
    }

    await patchCase(caseId, payload);
    revalidatePath(`/cases/${caseId}`);
    redirect(`/cases/${caseId}?feedback=workflow-updated`);
  }

  async function createNote(formData: FormData) {
    'use server';

    const content = String(formData.get('body') || '').trim();

    if (!content) {
      return;
    }

    await postCaseNote(caseId, content);
    revalidatePath(`/cases/${caseId}`);
    redirect(`/cases/${caseId}?feedback=note-added`);
  }

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
    padding: '1.25rem',
    boxShadow: '0 8px 24px rgba(15, 23, 42, 0.06)',
  } as const;

  const sectionTitleStyle = {
    margin: 0,
    fontSize: '1.15rem',
    color: '#0f172a',
  } as const;

  const feedbackConfig =
    feedback === 'workflow-updated'
      ? {
          title: 'Workflow updated',
          description: 'The case status or assignee was updated successfully.',
        }
      : feedback === 'note-added'
        ? {
            title: 'Note added',
            description: 'Your analyst note was saved to the case timeline.',
          }
        : null;

  return (
    <main style={pageStyle}>
      <div style={{ maxWidth: '1280px', margin: '0 auto' }}>
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

        {feedbackConfig ? (
          <section
            style={{
              ...cardStyle,
              marginBottom: '1rem',
              padding: '0.95rem 1.1rem',
              backgroundColor: '#ecfdf3',
              border: '1px solid #86efac',
              color: '#166534',
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: '0.2rem' }}>{feedbackConfig.title}</div>
            <div style={{ fontSize: '0.92rem' }}>{feedbackConfig.description}</div>
          </section>
        ) : null}

        {caseResult.kind === 'not-found' ? (
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
        ) : caseResult.kind === 'error' ? (
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
              {caseResult.message}. Check API availability and configuration.
            </div>
          </section>
        ) : (
          (() => {
            const caseData = caseResult.payload;
            const evidence = asEvidence(caseData);
            const notes = notesResult.kind === 'ok' ? asNotes(notesResult.payload) : [];
            const audit = auditResult.kind === 'ok' ? asAudit(auditResult.payload) : [];

            return (
              <div style={{ display: 'grid', gap: '1rem' }}>
                <section
                  style={{
                    ...cardStyle,
                    padding: '1.5rem',
                    background:
                      'linear-gradient(135deg, rgba(219,234,254,0.65) 0%, rgba(255,255,255,1) 40%)',
                  }}
                >
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
                      <div
                        style={{
                          color: '#1d4ed8',
                          fontWeight: 700,
                          fontSize: '0.85rem',
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                          marginBottom: '0.45rem',
                        }}
                      >
                        Case {caseData.id ?? caseId}
                      </div>
                      <h1 style={{ margin: '0 0 0.4rem', fontSize: '2rem' }}>
                        {formatText(caseData.title)}
                      </h1>
                      <div style={{ color: '#334155', fontSize: '1rem', fontWeight: 600 }}>
                        {formatText(caseData.vessel_name)} · MMSI {caseData.mmsi ?? '—'}
                      </div>
                      <div style={{ color: '#475569', fontSize: '0.92rem', marginTop: '0.45rem' }}>
                        Observed window: {formatObservedWindow(caseData.start_observed_at, caseData.end_observed_at)}
                      </div>
                    </div>
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(3, minmax(110px, 1fr))',
                        gap: '0.6rem',
                        minWidth: '340px',
                        width: 'min(100%, 420px)',
                      }}
                    >
                      {[
                        { label: 'Anomaly', value: formatScore(caseData.anomaly_score) },
                        { label: 'Rank', value: formatScore(caseData.rank_score) },
                        { label: 'Confidence', value: formatScore(caseData.confidence_score) },
                      ].map((field) => (
                        <div
                          key={field.label}
                          style={{
                            backgroundColor: '#0f172a',
                            color: '#f8fafc',
                            borderRadius: '14px',
                            padding: '0.85rem',
                          }}
                        >
                          <div style={{ fontSize: '0.75rem', opacity: 0.72, marginBottom: '0.25rem' }}>
                            {field.label}
                          </div>
                          <div style={{ fontSize: '1.15rem', fontWeight: 700 }}>{field.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                      gap: '0.75rem',
                    }}
                  >
                    {[
                      { label: 'Status', value: formatText(caseData.status) },
                      { label: 'Assigned to', value: formatText(caseData.assigned_to) },
                      { label: 'Priority', value: String(caseData.priority ?? '—') },
                      { label: 'Created', value: formatUtcDate(caseData.created_at) },
                    ].map((field) => (
                      <div
                        key={field.label}
                        style={{
                          padding: '0.85rem',
                          backgroundColor: 'rgba(248,250,252,0.95)',
                          border: '1px solid #dbe3f0',
                          borderRadius: '12px',
                        }}
                      >
                        <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.25rem' }}>
                          {field.label}
                        </div>
                        <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>{field.value}</div>
                      </div>
                    ))}
                  </div>
                </section>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(0, 2fr) minmax(320px, 1fr)',
                    gap: '1rem',
                    alignItems: 'start',
                  }}
                >
                  <div style={{ display: 'grid', gap: '1rem' }}>
                    <section style={cardStyle}>
                      <div style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: '0.35rem' }}>
                        Summary
                      </div>
                      <p style={{ margin: 0, lineHeight: 1.7, color: '#334155' }}>
                        {formatText(caseData.summary)}
                      </p>
                    </section>

                    <section style={cardStyle}>
                      <div style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: '0.35rem' }}>
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
                          <h2 style={sectionTitleStyle}>Evidence timeline</h2>
                          <div style={{ marginTop: '0.25rem', color: '#64748b', fontSize: '0.9rem' }}>
                            Observed time is primary. Ingest time is shown secondarily.
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
                        <div style={{ display: 'grid', gap: '0.8rem' }}>
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
                                    display: 'grid',
                                    gridTemplateColumns: 'minmax(0, 1.5fr) minmax(260px, 1fr)',
                                    gap: '0.9rem',
                                    marginBottom: explanation ? '0.75rem' : 0,
                                  }}
                                >
                                  <div>
                                    <div
                                      style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '0.5rem',
                                        flexWrap: 'wrap',
                                        marginBottom: '0.35rem',
                                      }}
                                    >
                                      <div
                                        style={{
                                          fontSize: '1rem',
                                          fontWeight: 700,
                                          color: '#0f172a',
                                        }}
                                      >
                                        {formatText(item.evidence_type)}
                                      </div>
                                      {alertType ? (
                                        <span
                                          style={{
                                            display: 'inline-flex',
                                            alignItems: 'center',
                                            borderRadius: '999px',
                                            padding: '0.22rem 0.55rem',
                                            fontSize: '0.72rem',
                                            fontWeight: 700,
                                            color: '#1d4ed8',
                                            backgroundColor: '#dbeafe',
                                            border: '1px solid #bfdbfe',
                                          }}
                                        >
                                          {alertType}
                                        </span>
                                      ) : null}
                                    </div>
                                    <div style={{ color: '#475569', fontSize: '0.9rem' }}>
                                      Provenance: {formatText(item.provenance)}
                                    </div>
                                    <div style={{ color: '#475569', fontSize: '0.9rem', marginTop: '0.2rem' }}>
                                      Ref: {formatText(item.evidence_ref)}
                                    </div>
                                  </div>
                                  <div
                                    style={{
                                      backgroundColor: '#ffffff',
                                      border: '1px solid #dbe3f0',
                                      borderRadius: '12px',
                                      padding: '0.75rem',
                                    }}
                                  >
                                    <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.2rem' }}>
                                      Timeline order
                                    </div>
                                    <div style={{ fontWeight: 700, marginBottom: '0.55rem' }}>
                                      {item.timeline_order ?? index + 1}
                                    </div>
                                    <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.2rem' }}>
                                      Observed at
                                    </div>
                                    <div style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '0.55rem' }}>
                                      {formatUtcDate(item.observed_at)}
                                    </div>
                                    <div style={{ fontSize: '0.78rem', color: '#64748b', marginBottom: '0.2rem' }}>
                                      Recorded at
                                    </div>
                                    <div style={{ fontSize: '0.88rem', color: '#334155' }}>
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

                  <div style={{ display: 'grid', gap: '1rem' }}>
                    <section style={cardStyle}>
                      <div style={{ marginBottom: '0.9rem' }}>
                        <h2 style={sectionTitleStyle}>Workflow actions</h2>
                        <div style={{ color: '#64748b', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                          Quick analyst state changes for this case.
                        </div>
                        <div style={{ color: '#94a3b8', fontSize: '0.82rem', marginTop: '0.35rem' }}>
                          Changes save immediately and refresh with a confirmation message.
                        </div>
                      </div>
                      <div style={{ display: 'grid', gap: '0.65rem' }}>
                        {[
                          { label: 'Start review', status: 'in_review' },
                          { label: 'Assign to me', assigned_to: 'Abdullah' },
                          { label: 'Escalate', status: 'escalated' },
                          { label: 'Resolve', status: 'resolved' },
                          { label: 'Dismiss', status: 'dismissed' },
                        ].map((action) => {
                          const isActive =
                            ('status' in action && caseData.status === action.status) ||
                            ('assigned_to' in action && caseData.assigned_to === action.assigned_to);

                          return (
                            <form key={action.label} action={updateWorkflow}>
                              {'status' in action ? (
                                <input type="hidden" name="status" value={action.status} />
                              ) : null}
                              {'assigned_to' in action ? (
                                <input type="hidden" name="assigned_to" value={action.assigned_to} />
                              ) : null}
                              <button
                                type="submit"
                                aria-pressed={isActive}
                                style={{
                                  width: '100%',
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                  gap: '0.75rem',
                                  textAlign: 'left',
                                  border: isActive ? '1px solid #93c5fd' : '1px solid #cbd5e1',
                                  borderRadius: '12px',
                                  backgroundColor: isActive ? '#eff6ff' : '#ffffff',
                                  color: '#0f172a',
                                  padding: '0.85rem 0.95rem',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                <span>{action.label}</span>
                                <span
                                  style={{
                                    fontSize: '0.74rem',
                                    fontWeight: 700,
                                    color: isActive ? '#1d4ed8' : '#64748b',
                                  }}
                                >
                                  {isActive ? 'Current' : 'Save'}
                                </span>
                              </button>
                            </form>
                          );
                        })}
                      </div>
                    </section>

                    <section style={cardStyle}>
                      <div style={{ marginBottom: '0.9rem' }}>
                        <h2 style={sectionTitleStyle}>Analyst notes</h2>
                        <div style={{ color: '#64748b', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                          Working notes for handoff, decisions, and context.
                        </div>
                      </div>

                      <form action={createNote} style={{ display: 'grid', gap: '0.6rem', marginBottom: '1rem' }}>
                        <textarea
                          name="body"
                          rows={4}
                          placeholder="Add an analyst note…"
                          style={{
                            width: '100%',
                            resize: 'vertical',
                            border: '1px solid #cbd5e1',
                            borderRadius: '12px',
                            padding: '0.85rem',
                            font: 'inherit',
                            color: '#0f172a',
                            backgroundColor: '#fff',
                            boxSizing: 'border-box',
                          }}
                        />
                        <button
                          type="submit"
                          style={{
                            justifySelf: 'start',
                            border: '1px solid #1d4ed8',
                            backgroundColor: '#1d4ed8',
                            color: '#fff',
                            borderRadius: '10px',
                            padding: '0.65rem 0.9rem',
                            fontWeight: 700,
                            cursor: 'pointer',
                          }}
                        >
                          Add note
                        </button>
                      </form>

                      {notesResult.kind === 'error' ? (
                        <div style={{ color: '#9f1239', fontSize: '0.92rem' }}>
                          Failed to load notes: {notesResult.message}
                        </div>
                      ) : notes.length === 0 ? (
                        <div
                          style={{
                            padding: '1rem',
                            color: '#475569',
                            backgroundColor: '#f8fafc',
                            border: '1px dashed #cbd5e1',
                            borderRadius: '12px',
                          }}
                        >
                          No notes yet.
                        </div>
                      ) : (
                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                          {notes.map((note, index) => (
                            <article
                              key={note.id ?? `note-${index}`}
                              style={{
                                border: '1px solid #e2e8f0',
                                borderRadius: '12px',
                                backgroundColor: '#f8fafc',
                                padding: '0.85rem',
                              }}
                            >
                              <div
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  gap: '0.75rem',
                                  flexWrap: 'wrap',
                                  marginBottom: '0.45rem',
                                }}
                              >
                                <div style={{ fontWeight: 700, fontSize: '0.92rem' }}>{noteAuthor(note)}</div>
                                <div style={{ color: '#64748b', fontSize: '0.82rem' }}>
                                  {formatUtcDate(note.created_at || note.updated_at)}
                                </div>
                              </div>
                              <p style={{ margin: 0, lineHeight: 1.6, color: '#334155', whiteSpace: 'pre-wrap' }}>
                                {noteBody(note)}
                              </p>
                            </article>
                          ))}
                        </div>
                      )}
                    </section>

                    <section style={cardStyle}>
                      <div style={{ marginBottom: '0.9rem' }}>
                        <h2 style={sectionTitleStyle}>Audit trail</h2>
                        <div style={{ color: '#64748b', fontSize: '0.9rem', marginTop: '0.25rem' }}>
                          Recent workflow and system activity on this case.
                        </div>
                      </div>

                      {auditResult.kind === 'error' ? (
                        <div style={{ color: '#9f1239', fontSize: '0.92rem' }}>
                          Failed to load audit trail: {auditResult.message}
                        </div>
                      ) : audit.length === 0 ? (
                        <div
                          style={{
                            padding: '1rem',
                            color: '#475569',
                            backgroundColor: '#f8fafc',
                            border: '1px dashed #cbd5e1',
                            borderRadius: '12px',
                          }}
                        >
                          No audit events recorded yet.
                        </div>
                      ) : (
                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                          {audit.map((entry, index) => (
                            <article
                              key={entry.id ?? `audit-${index}`}
                              style={{
                                borderLeft: '3px solid #1d4ed8',
                                padding: '0.15rem 0 0.15rem 0.85rem',
                              }}
                            >
                              <div
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  gap: '0.75rem',
                                  flexWrap: 'wrap',
                                  marginBottom: '0.2rem',
                                }}
                              >
                                <div style={{ fontWeight: 700, fontSize: '0.92rem' }}>{auditLabel(entry)}</div>
                                <div style={{ color: '#64748b', fontSize: '0.82rem' }}>
                                  {formatUtcDate(entry.created_at || entry.timestamp)}
                                </div>
                              </div>
                              <div style={{ color: '#334155', fontSize: '0.88rem', marginBottom: '0.2rem' }}>
                                Actor: {auditActor(entry)}
                              </div>
                              <pre
                                style={{
                                  margin: 0,
                                  color: '#475569',
                                  fontSize: '0.88rem',
                                  lineHeight: 1.5,
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-word',
                                  fontFamily: 'inherit',
                                }}
                              >
                                {auditDetail(entry)}
                              </pre>
                            </article>
                          ))}
                        </div>
                      )}
                    </section>
                  </div>
                </div>
              </div>
            );
          })()
        )}
      </div>
    </main>
  );
}
