import { useEffect, useState } from 'react';
import { api } from './api';

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

export function HalConnection() {
  return <section className="panel"><div className="panel-heading"><div><h2>HAL ERP connection</h2><span className="record-tag amber">Not connected · Awaiting school IT</span></div></div><div className="panel-padding"><p>Automatic updates are not available yet. Existing dashboard records are not evidence of a HAL connection.</p><div className="table-scroll"><table><thead><tr><th>Planned data</th><th>Current availability</th></tr></thead><tbody><tr><td>Admissions, withdrawals and parent links</td><td>HAL sync pending; automatic account deactivation is not implemented.</td></tr><tr><td>Fee balances, payments and outstanding amounts</td><td>HAL sync pending; current student records contain fee status only.</td></tr><tr><td>Student attendance</td><td>HAL sync pending; current student records contain attendance percentage only.</td></tr><tr><td>Teacher attendance</td><td>Not implemented; requires HAL data and agreed access rules.</td></tr></tbody></table></div><p className="subtle">School IT or HAL support must provide approved integration documentation and read-only access. No HAL credentials are collected here. No sync has run.</p><p>Continue using the Import centre for supported files and school documents. Imports are not automatic ERP updates.</p></div></section>;
}
