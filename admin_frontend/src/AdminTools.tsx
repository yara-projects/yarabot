import { useEffect, useState } from 'react';
import { api } from './api';
import type { Row } from './api';
import { ManualPhrase } from './KnowledgeReview';

function Failure({ error }: { error: string }) { return error ? <p role="alert" className="error-box">{error}</p> : null; }

export function Relationships() {
  const [kind, setKind] = useState('parent-children');
  const [owner, setOwner] = useState('');
  const [ids, setIds] = useState('');
  const [snapshot, setSnapshot] = useState<{ revision: string; members: { id: number; label: string }[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    const guard = (event: Event) => { if (dirty && !window.confirm('Discard unsaved relationship changes?')) event.preventDefault(); };
    const unload = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('admin:before-navigate', guard); window.addEventListener('beforeunload', unload);
    return () => { window.removeEventListener('admin:before-navigate', guard); window.removeEventListener('beforeunload', unload); };
  }, [dirty]);
  async function load(save = false) {
    if (save && (!snapshot || !window.confirm('Replace these links? This changes access/assignments. An empty list removes every link for this person.'))) return;
    if (!save && dirty && !window.confirm('Discard unsaved links and reload?')) return;
    const values = ids.trim() ? ids.split(',').map(value => Number(value.trim())) : [];
    if (save && values.some(value => !Number.isInteger(value) || value < 1)) { setError('Use positive IDs separated by commas.'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const result = await api<typeof snapshot>(`/relations/${kind}/${owner}`, save ? { method: 'PUT', body: JSON.stringify({ ids: values, revision: snapshot?.revision, confirmed: true }) } : {});
      setSnapshot(result); setIds(result?.members.map(item => item.id).join(', ') ?? ''); setDirty(false); if (save) setMessage('Links saved.');
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <section className="panel"><div className="panel-heading"><div><h2>Explicit links, never guessed</h2><span className="subtle">Use IDs from Parents, Students, Teachers and Subjects. Existing links are retained until you confirm a replacement.</span></div></div><div className="panel-padding"><div className="form-grid"><label>Relationship<select value={kind} disabled={busy || dirty} onChange={event => { setKind(event.target.value); setSnapshot(null); }}><option value="parent-children">Parent → linked students</option><option value="teacher-subjects">Teacher → subjects taught</option></select></label><label>{kind === 'parent-children' ? 'Parent ID' : 'Teacher ID'}<input type="number" min="1" disabled={busy || dirty} value={owner} onChange={event => { setOwner(event.target.value); setSnapshot(null); }} /></label></div><button className="button secondary" disabled={busy || !owner} onClick={() => void load()}>Load current links</button>{snapshot && <><p>Current: {snapshot.members.map(item => `${item.id}: ${item.label}`).join(' · ') || 'No linked records'}</p><label>{kind === 'parent-children' ? 'Student IDs' : 'Subject IDs'} (comma-separated)<input value={ids} disabled={busy} onChange={event => { setIds(event.target.value); setDirty(true); }} /></label><p className="subtle">Student/teacher names are not used as IDs. Removing a parent link immediately changes which children their account can access.</p><button className="button primary" disabled={busy || !dirty} onClick={() => void load(true)}>Confirm link replacement</button></>}<Failure error={error} />{message && <p role="status">{message}</p>}</div></section>;
}

type System = { enabled: boolean; revision: string; logs: { action: string; timestamp: string }[] };
export function SystemStatus() {
  const [data, setData] = useState<System | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load(enable = false) {
    if (enable && !window.confirm('Bring Nova back online for all accounts?')) return;
    setBusy(true); setError('');
    try { setData(await api<System>('/system', enable ? { method: 'PUT', body: JSON.stringify({ enable: true, confirmed: true, revision: data?.revision }) } : {})); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, []);
  return <section className="panel"><div className="panel-heading"><h2>Nova system status</h2><button className="button secondary" disabled={busy} onClick={() => void load()}>Refresh</button></div><div className="panel-padding"><Failure error={error} />{data && <><p className="record-tag">{data.enabled ? 'Online' : 'Offline'}</p><p>The emergency disable stays with the principal. This admin control can deliberately re-enable Nova.</p>{!data.enabled && <button className="button primary" disabled={busy} onClick={() => void load(true)}>Re-enable Nova</button>}<h3>Recent system actions</h3><div className="table-scroll"><table><thead><tr><th>Action</th><th>Recorded timestamp</th></tr></thead><tbody>{data.logs.map((log, index) => <tr key={index}><td>{log.action}</td><td>{log.timestamp}</td></tr>)}</tbody></table></div></>}</div></section>;
}

export function PhraseReview() {
  const [rows, setRows] = useState<Row[]>([]);
  const [checks, setChecks] = useState<Record<string, { status: string; reason: string }>>({});
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load() {
    setBusy(true); setError('');
    try { const result = await api<{ rows: Row[]; total: number }>(`/records/phrases?page=${page}&size=25`); setRows(result.rows); setTotal(result.total); setChecks({}); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, [page]);
  async function action(row: Row, name: string) {
    if (name !== 'check' && !window.confirm(`${name === 'approve' ? 'Approve this routing phrase? It will change live NLP routing.' : 'Dismiss this candidate?'} The server will recheck its revision and safety.`)) return;
    setBusy(true); setError('');
    try {
      const result = await api<{ status: string; reason: string }>(`/phrases/${row.id}/${name}`, { method: 'POST', body: JSON.stringify({ revision: row._revision, confirmed: name !== 'check' }) });
      if (name === 'check') setChecks({ ...checks, [String(row.id)]: result }); else await load();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <section className="panel"><div className="panel-heading"><div><h2>Routing phrase review</h2><span className="subtle">Existing cross-role collision checks run again at approval. Unsafe candidates cannot be forced through.</span></div><button className="button secondary" disabled={busy} onClick={() => void load()}>Refresh</button></div><div className="panel-padding"><Failure error={error} /><div className="table-scroll"><table><thead><tr><th>Phrase</th><th>Intent / role</th><th>Safety</th><th>Actions</th></tr></thead><tbody>{rows.map(row => <tr key={String(row.id)}><td>{row.phrase_text}</td><td>{row.resolved_intent} · {row.role}</td><td>{row.applied ? 'Already resolved' : checks[String(row.id)] ? `${checks[String(row.id)].status}: ${checks[String(row.id)].reason || 'No routing collision found'}` : 'Not checked'}</td><td>{!row.applied && <div className="button-group"><button className="text-button" disabled={busy} onClick={() => void action(row, 'check')}>Check</button><button className="text-button" disabled={busy || checks[String(row.id)]?.status !== 'safe'} onClick={() => void action(row, 'approve')}>Approve</button><button className="text-button" disabled={busy} onClick={() => void action(row, 'dismiss')}>Dismiss</button></div>}</td></tr>)}</tbody></table></div><div className="pagination"><button className="button secondary" disabled={busy || page === 1} onClick={() => setPage(value => value - 1)}>Previous</button><span>Page {page}</span><button className="button secondary" disabled={busy || page * 25 >= total} onClick={() => setPage(value => value + 1)}>Next</button></div></div><ManualPhrase /></section>;
}
