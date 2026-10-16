import { useEffect, useState } from 'react';
import { api } from './api';
import type { Resource } from './api';
import { ConfirmDialog } from './ConfirmDialog';

type Draft = { kind: string; filename: string; rows: Record<string, string>[]; source_text: string; warnings?: string[]; suggested_scope?: Record<string, string>; scope?: Record<string, string>; document_id?: string; revision?: number; publication_version?: number; status?: string };
type Saved = { document_id: string; filename: string; status: string; revision: number };
const FIELDS = [
  ['year', 'Academic year (2026-27)'], ['grade', 'Grade'], ['division', 'Class division (F)'], ['stream', 'Stream (Commerce)'],
  ['assessment', 'Assessment (Term 2 / UT 1 / Whole year)'], ['teacher_id', 'Teacher ID (teacher timetable only)'],
  ['effective_from', 'Valid from'], ['effective_to', 'Valid until'],
];

export function ImportWorkspace() {
  const [kind, setKind] = useState('timetable');
  const [catalog, setCatalog] = useState<Record<string, Resource>>({});
  const recordImport = kind.startsWith('records/');
  const [file, setFile] = useState<File | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [scope, setScope] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Saved[]>([]);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [pendingAction, setPendingAction] = useState('');
  const columns = recordImport ? ['_id', ...(catalog[kind.split('/')[1]]?.fields.map(field => field.key) ?? []), '_revision'] : kind === 'syllabus' ? ['subject', 'section', 'chapter', 'topic'] : ['day', 'period', 'start', 'end', 'activity', 'teacher', 'class'];
  const immutable = draft && !['draft', 'approved'].includes(draft.status ?? 'draft');
  async function history() { try { setSaved((await api<{ documents: Saved[] }>('/imports')).documents); } catch (err) { setError((err as Error).message); } }
  useEffect(() => { void history(); api<{ resources: Record<string, Resource> }>('/catalog').then(value => setCatalog(value.resources)).catch(err => setError(err.message)); }, []);
  useEffect(() => {
    const nav = (event: Event) => { if (dirty && !window.confirm('Discard unsaved document changes?')) event.preventDefault(); };
    const unload = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('admin:before-navigate', nav); window.addEventListener('beforeunload', unload);
    return () => { window.removeEventListener('admin:before-navigate', nav); window.removeEventListener('beforeunload', unload); };
  }, [dirty]);
  function load(value: Draft) { setDraft(value); setKind(value.kind); setScope(value.scope ?? value.suggested_scope ?? {}); setDirty(false); setReviewed(false); }
  async function run(task: () => Promise<void>) { setBusy(true); setError(''); setMessage(''); try { await task(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  function change(value: Draft) { setDraft(value); setDirty(true); setReviewed(false); }
  async function extract() {
    if (!file) return;
    if (dirty && !window.confirm('Discard unsaved document changes?')) return;
    await run(async () => { const body = new FormData(); body.set('kind', kind); body.set('file', file); load(await api<Draft>('/imports/preview', { method: 'POST', body })); setDirty(true); });
  }
  async function save() {
    if (!draft) return;
    await run(async () => {
      const value = await api<Draft>(draft.document_id ? `/imports/${draft.document_id}` : '/imports', { method: draft.document_id ? 'PUT' : 'POST', body: JSON.stringify({ revision: draft.revision, document: { kind, scope, rows: draft.rows, filename: draft.filename, source_text: draft.source_text } }) });
      load(value); setMessage('Draft saved. It is not available to the chatbot.'); await history();
    });
  }
  async function transition(action: string) {
    if (!draft?.document_id || dirty) return;
    setPendingAction('');
    await run(async () => { load(await api<Draft>(`/imports/${draft.document_id}/${action}`, { method: 'POST', body: JSON.stringify({ revision: draft.revision, publication_version: draft.publication_version, confirmed: true }) })); setMessage(`${action === 'publish' ? 'Published' : action === 'approve' ? 'Approved, not yet published' : 'Withdrawn'}.`); await history(); });
  }
  return <section className="panel"><div className="panel-heading"><div><h2>Upload → review → approve → publish</h2><span className="subtle">Local extraction. Explicit publication. Previous versions retained.</span></div></div>
    {pendingAction && <ConfirmDialog message={pendingAction === 'publish' ? `Publish this ${recordImport ? 'record batch (applies every row to school records, not undoable here)' : 'document'} and replace publication version ${draft?.publication_version ?? 0} for exactly this scope?` : pendingAction === 'withdraw' ? 'Withdraw this document from chatbot answers? History is retained.' : 'Approve these reviewed entries and their confirmed scope? Approval alone does not publish them.'} cancel={() => setPendingAction('')} confirm={() => void transition(pendingAction)} />}
    <div className="draft-workspace"><div className="form-grid"><label>Document type<select value={kind} disabled={busy || !!draft} onChange={event => setKind(event.target.value)}><option value="timetable">Student / class timetable</option><option value="teacher_timetable">Teacher timetable</option><option value="syllabus">Syllabus / exam portions</option>{['students', 'parents', 'teachers', 'departments', 'subjects', 'exams', 'timetable', 'class-teachers', 'class-sections'].filter(key => catalog[key]).map(key => <option key={key} value={`records/${key}`}>{catalog[key].title} — record batch</option>)}</select></label><label>School document<input type="file" accept=".csv,.xlsx,.pdf,.docx,.png,.jpg,.jpeg,.webp" disabled={busy} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label></div><p className="subtle">Up to 8 MB. CSV, XLSX, PDF, DOCX or image. OCR requires the local Tesseract runtime; no external AI upload.</p><button className="button secondary" disabled={!file || busy || !!immutable} onClick={() => void extract()}>{busy ? 'Working…' : 'Extract review draft'}</button>
    {error && <div className="error-box" role="alert">{error}</div>}{message && <p role="status" className="inline-notice">{message}</p>}
    {draft && <><div className="section-heading"><h2>{draft.filename}</h2><span className="record-tag">{draft.status ?? 'Unsaved draft'} · revision {draft.revision ?? '—'}</span></div>
      <fieldset disabled={busy || !!immutable}>{!recordImport && <div className="form-grid scope-fields">{FIELDS.map(([key, label]) => <label key={key}>{label}<input type="text" placeholder={key.startsWith('effective_') ? 'YYYY-MM-DD' : undefined} maxLength={80} value={scope[key] ?? ''} onChange={event => { setScope({ ...scope, [key]: event.target.value }); setDirty(true); setReviewed(false); }} /></label>)}</div>}
      <details className="draft-warnings"><summary>Source and review notes</summary><ul>{(draft.warnings ?? []).map((warning, index) => <li key={index}>{warning}</li>)}</ul><p>Verify OCR, abbreviations, combined subjects, teacher identity and 24-hour times. B2 and unknown codes are not interpreted. No optional-subject assignment is inferred.</p><pre className="source-preview">{draft.source_text || 'No text extracted. Enter verified rows manually.'}</pre></details>
      <div className="table-scroll draft-table"><table><thead><tr><th>#</th>{columns.map(column => <th key={column}>{column}</th>)}<th>Remove</th></tr></thead><tbody>{draft.rows.map((row, index) => <tr key={index}><td>{index + 1}</td>{columns.map(column => <td key={column}><textarea aria-label={`Row ${index + 1} ${column}`} rows={3} maxLength={10000} readOnly={column === '_revision'} value={row[column] ?? ''} onChange={event => change({ ...draft, rows: draft.rows.map((entry, i) => i === index ? { ...entry, [column]: event.target.value } : entry) })} /></td>)}<td><button className="text-button" onClick={() => change({ ...draft, rows: draft.rows.filter((_, i) => i !== index) })}>Remove</button></td></tr>)}</tbody></table></div>
      <div className="draft-actions"><button className="button secondary" disabled={draft.rows.length >= 1000} onClick={() => change({ ...draft, rows: [...draft.rows, Object.fromEntries(columns.map(key => [key, '']))] })}>Add entry</button><button className="button primary" disabled={!dirty} onClick={() => void save()}>Save draft</button></div></fieldset>
      {!dirty && draft.status === 'draft' && <label className="review-confirmation"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} /> <span>I checked every entry, identity, scope and validity date against the school source. {recordImport && 'Record batches replace every shown field on existing IDs; blanks are not preserved automatically.'}</span></label>}
      <div className="draft-actions">{draft.status === 'draft' && <button className="button primary" disabled={busy || dirty || !reviewed} onClick={() => setPendingAction('approve')}>Approve reviewed draft</button>}{draft.status === 'approved' && <button className="button primary" disabled={busy || dirty} onClick={() => setPendingAction('publish')}>Publish approved version</button>}{draft.status === 'published' && !recordImport && <button className="button secondary" disabled={busy} onClick={() => setPendingAction('withdraw')}>Withdraw publication</button>}{immutable && <button className="button secondary" disabled={busy} onClick={() => { load({ ...draft, document_id: undefined, revision: undefined, publication_version: undefined, status: 'draft' }); setDirty(true); }}>Create replacement draft</button>}<button className="text-button" disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard unsaved changes?')) { setDraft(null); setDirty(false); } }}>Close draft</button></div></>}
    <div className="section-heading"><h2>Saved drafts & publication history</h2><button className="text-button" disabled={busy} onClick={() => void history()}>Refresh</button></div><div className="table-scroll"><table><thead><tr><th>Document</th><th>Status</th><th>Revision</th><th>Review</th></tr></thead><tbody>{saved.map(item => <tr key={item.document_id}><td>{item.filename}</td><td>{item.status}</td><td>{item.revision}</td><td><button className="text-button" disabled={busy} onClick={() => { if (!dirty || window.confirm('Discard unsaved changes?')) void run(async () => load(await api<Draft>(`/imports/${item.document_id}`))); }}>Open</button></td></tr>)}</tbody></table></div></div></section>;
}
