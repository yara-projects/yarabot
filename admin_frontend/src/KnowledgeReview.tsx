import { useEffect, useState } from 'react';
import { api } from './api';
import type { Row } from './api';
import { ConfirmDialog } from './ConfirmDialog';

export function ManualPhrase() {
  const [intents, setIntents] = useState<string[]>([]);
  const [phrase, setPhrase] = useState('');
  const [intent, setIntent] = useState('');
  const [check, setCheck] = useState<{ status: string; reason: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { api<{ intents: string[] }>('/phrase-intents').then(result => setIntents(result.intents)).catch(err => setError(err.message)); }, []);
  async function submit(approve = false) {
    setConfirm(false); setBusy(true); setError(''); setMessage('');
    try {
      const result = await api<{ status: string; reason: string }>(`/phrases/manual/${approve ? 'approve' : 'check'}`, { method: 'POST', body: JSON.stringify({ phrase, intent, confirmed: approve }) });
      if (approve) { setPhrase(''); setCheck(null); setMessage('Manual phrase approved. The chatbot refreshes its phrase cache within 60 seconds.'); } else setCheck(result);
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <div className="panel-padding"><h3>Add a routing phrase manually</h3><p className="subtle">Use a genuine school question, not a general keyword. Approval reruns the cross-role safety checks.</p>{confirm && <ConfirmDialog message="Approve this phrase for live routing? The server will rerun collision checks against the current phrase set." confirm={() => void submit(true)} cancel={() => setConfirm(false)} />}<div className="form-grid"><label>Phrase<input value={phrase} maxLength={500} disabled={busy} onChange={event => { setPhrase(event.target.value); setCheck(null); }} /></label><label>Intent<select value={intent} disabled={busy} onChange={event => { setIntent(event.target.value); setCheck(null); }}><option value="">Choose an intent…</option>{intents.map(value => <option key={value}>{value}</option>)}</select></label></div><div className="draft-actions"><button className="button secondary" disabled={busy || !phrase.trim() || !intent} onClick={() => void submit()}>Check safety</button><button className="button primary" disabled={busy || check?.status !== 'safe'} onClick={() => setConfirm(true)}>Approve manual phrase</button></div>{check && <p role="status">{check.status}: {check.reason || 'No routing collision found.'}</p>}{error && <p className="error-box" role="alert">{error}</p>}{message && <p role="status">{message}</p>}</div>;
}

export function UnansweredReview() {
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Row | null>(null);
  const [topic, setTopic] = useState('');
  const [answer, setAnswer] = useState('');
  const [action, setAction] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load() { setBusy(true); setError(''); try { const value = await api<{ rows: Row[]; total: number }>(`/records/suggestions?page=${page}&size=25`); setRows(value.rows); setTotal(value.total); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  useEffect(() => { void load(); }, [page]);
  useEffect(() => {
    const guard = (event: Event) => { if (answer && !window.confirm('Discard this unsaved verified answer?')) event.preventDefault(); };
    const unload = (event: BeforeUnloadEvent) => { if (answer) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('admin:before-navigate', guard); window.addEventListener('beforeunload', unload);
    return () => { window.removeEventListener('admin:before-navigate', guard); window.removeEventListener('beforeunload', unload); };
  }, [answer]);
  async function submit() {
    if (!selected) return;
    const operation = action; setAction(''); setBusy(true); setError('');
    try { await api(`/suggestions/${selected.id}/${operation}`, { method: 'POST', body: JSON.stringify({ revision: selected._revision, confirmed: true, topic, answer }) }); setSelected(null); setAnswer(''); await load(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <section className="panel"><div className="panel-heading"><div><h2>Unanswered questions</h2><span className="subtle">Write a school-verified answer before adding it to the almanac. No automatic AI-generated facts.</span></div><button className="button secondary" disabled={busy} onClick={() => void load()}>Refresh</button></div>{action && <ConfirmDialog message={action === 'append' ? 'Append this verified topic and answer to the latest almanac, then remove the question from the queue?' : 'Dismiss this unanswered question permanently?'} confirm={() => void submit()} cancel={() => setAction('')} />}<div className="panel-padding">{error && <p className="error-box" role="alert">{error}</p>}<div className="table-scroll"><table><thead><tr><th>Question</th><th>Count</th><th>Review</th></tr></thead><tbody>{rows.map(row => <tr key={String(row.id)}><td>{row.question_text}</td><td>{row.ask_count}</td><td><button className="text-button" disabled={busy} onClick={() => { if (!answer || window.confirm('Discard the unsaved answer?')) { setSelected(row); setTopic(String(row.question_text).slice(0, 150)); setAnswer(''); } }}>Review</button></td></tr>)}</tbody></table></div>{selected && <div className="almanac-form"><label>Topic<input value={topic} maxLength={150} disabled={busy} onChange={event => setTopic(event.target.value)} /></label><label>Verified school answer<textarea rows={6} value={answer} maxLength={20000} disabled={busy} onChange={event => setAnswer(event.target.value)} /></label><div className="draft-actions"><button className="button primary" disabled={busy || !topic.trim() || !answer.trim()} onClick={() => setAction('append')}>Add verified answer to almanac</button><button className="button secondary" disabled={busy} onClick={() => setAction('dismiss')}>Dismiss question</button></div></div>}<div className="pagination"><button className="button secondary" disabled={busy || page === 1} onClick={() => setPage(value => value - 1)}>Previous</button><span>Page {page}</span><button className="button secondary" disabled={busy || page * 25 >= total} onClick={() => setPage(value => value + 1)}>Next</button></div></div></section>;
}
