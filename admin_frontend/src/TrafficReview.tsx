import { useEffect, useState } from 'react';
import { api } from './api';
import { ConfirmDialog } from './ConfirmDialog';
import { ManualPhrase } from './KnowledgeReview';

type Period = { requests: number; nlp_rate: number | null; up_rate: number | null; fallback_rate: number | null };
type ReviewRow = { key: string; revision: string; topic: string; intent: string; requests: number; down: number; fallback: number; repeats: number; near_misses: number; incomplete: number };
type Review = { current: Period; previous: Period; rows: ReviewRow[]; sample_limited: boolean; more_groups: boolean; definitions: string };

export function TrafficReview({ view, readOnly }: { view: 'phrases' | 'knowledge'; readOnly: boolean }) {
  const [data, setData] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ReviewRow | null>(null);
  const [resolving, setResolving] = useState<ReviewRow | null>(null);
  const [message, setMessage] = useState('');
  async function load() {
    setBusy(true); setError('');
    try { setData(await api<Review>(`/review/traffic?view=${view}`)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => { void load(); }, [view]);
  async function resolve() {
    if (!resolving) return;
    const row = resolving; setResolving(null); setBusy(true); setError('');
    try {
      await api(`/review/${row.key}/resolve`, { method: 'POST', body: JSON.stringify({ revision: row.revision, confirmed: true }) });
      setMessage('Marked reviewed. This topic will return if its weekly evidence changes.');
      await load();
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }
  function choose(row: ReviewRow) {
    if (window.dispatchEvent(new Event('admin:before-navigate', { cancelable: true }))) setSelected(row);
  }
  const metrics = [{ key: 'nlp_rate', label: 'NLP share of requests' }, { key: 'up_rate', label: 'Positive feedback' }, { key: 'fallback_rate', label: 'Fallback rate' }] as const;
  const percent = (value: number | null) => value === null ? '—' : `${value}%`;
  return <>
    <section className="panel"><div className="panel-heading"><div><h2>{view === 'phrases' ? 'Routing & phrase review' : 'School knowledge review'}</h2><span className="subtle">Last 7 days compared with the previous 7 days · Topic totals, not private conversations.</span></div><button className="button secondary" disabled={busy} onClick={() => void load()}>Refresh review</button></div>
      <div className="panel-padding">
        {error && <p className="error-box" role="alert">{error}</p>}
        {message && <p className="inline-notice" role="status">{message}</p>}
        {busy && !data && <p role="status">Loading review…</p>}
        {data && <><div className="metrics-grid review-metrics">{metrics.map(metric => <div className="metric" key={metric.key}><div className="metric-label">{metric.label}</div><strong>{percent(data.current[metric.key])}</strong><span className="metric-note">Previous week: {percent(data.previous[metric.key])}</span></div>)}</div>
          <p className="subtle">{data.current.requests} eligible requests this week · {data.previous.requests} in the previous week. A dash means there is no denominator, not a zero rating.</p>
          {(data.sample_limited || data.more_groups) && <p className="inline-notice">Bounded view: at most 10,000 recent events and 100 topic groups. These totals may be partial.</p>}
          {!data.rows.length ? <div className="empty-state"><h3>{view === 'phrases' ? 'No routing issues flagged this week' : 'No knowledge gaps flagged this week'}</h3><p>New feedback and routing signals appear here automatically. Use School almanac for verified information, or Phrase review to author a routing phrase.</p></div> : <div className="table-scroll"><table><thead><tr><th>Topic / intent</th><th>Requests</th><th>Thumbs down</th><th>Fallbacks</th><th>Same-topic repeats</th><th>Near misses</th><th>Actions</th></tr></thead><tbody>{data.rows.map(row => <tr key={row.key}><td><strong>{row.topic}</strong><br /><span className="subtle">{row.intent}</span></td><td>{row.requests}</td><td>{row.down}</td><td>{row.fallback}</td><td>{row.repeats}</td><td>{row.near_misses}</td><td><div className="button-group"><button className="text-button" disabled={busy || readOnly} onClick={() => choose(row)}>{view === 'phrases' ? 'Draft phrase' : 'Add verified information'}</button><button className="text-button" disabled={busy || readOnly} onClick={() => setResolving(row)}>Mark reviewed</button></div></td></tr>)}</tbody></table></div>}
          <details className="review-definitions"><summary>How to interpret these signals</summary><p className="subtle">{data.definitions}</p><p className="subtle">No question text, answer text, names, record IDs, class groups or session identifiers are shown. Signals help prioritise review; they do not prove that a phrase or school fact is correct.</p></details>
        </>}
      </div>
    </section>
    {resolving && <ConfirmDialog message="Mark this topic's current evidence reviewed? No chat history is deleted. New or changed weekly evidence will bring it back." confirm={() => void resolve()} cancel={() => setResolving(null)} />}
    {!readOnly && (view === 'phrases' ? <section className="panel"><ManualPhrase key={selected?.key ?? 'manual'} initialIntent={selected?.intent === 'unclassified' ? '' : selected?.intent} /></section> : selected && <VerifiedAnswer key={selected.key} topic={selected.topic} />)}
  </>;
}

function VerifiedAnswer({ topic: initialTopic }: { topic: string }) {
  const [topic, setTopic] = useState(initialTopic);
  const [answer, setAnswer] = useState('');
  const [version, setVersion] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [message, setMessage] = useState('');
  async function loadVersion() {
    setError(''); setBusy(true);
    try { setVersion((await api<{ version: number }>('/almanac')).version); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => { void loadVersion(); }, []);
  useEffect(() => {
    const guard = (event: Event) => { if (answer && !window.confirm('Discard this unsaved verified answer?')) event.preventDefault(); };
    const unload = (event: BeforeUnloadEvent) => { if (answer) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('admin:before-navigate', guard); window.addEventListener('beforeunload', unload);
    return () => { window.removeEventListener('admin:before-navigate', guard); window.removeEventListener('beforeunload', unload); };
  }, [answer]);
  async function save() {
    setConfirm(false); setBusy(true); setError(''); setMessage('');
    try {
      const result = await api<{ version: number }>('/review/almanac', { method: 'POST', body: JSON.stringify({ topic, answer, version, confirmed: true }) });
      setVersion(result.version); setAnswer(''); setMessage('Verified information added. YaraBot normally refreshes within 60 seconds. Mark the topic reviewed when satisfied.');
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="panel"><div className="panel-padding"><h2>Add verified school information</h2><p className="subtle">Write a general school answer with its source and relevant dates. Do not include private student, staff or complaint details.</p><div className="almanac-form"><label>Topic<input value={topic} maxLength={150} disabled={busy} onChange={event => setTopic(event.target.value)} /></label><label>Verified school answer<textarea rows={6} value={answer} maxLength={20000} disabled={busy} onChange={event => setAnswer(event.target.value)} /></label><div className="button-group"><button className="button primary" disabled={busy || version === null || !topic.trim() || !answer.trim()} onClick={() => setConfirm(true)}>Add to almanac</button><button className="text-button" disabled={busy} onClick={() => void loadVersion()}>Reload almanac version</button></div></div>{error && <p className="error-box" role="alert">{error}</p>}{message && <p className="inline-notice" role="status">{message}</p>}</div>{confirm && <ConfirmDialog message="Append this verified topic and answer to the school almanac? Saved information affects live chatbot answers." confirm={() => void save()} cancel={() => setConfirm(false)} />}</section>;
}
