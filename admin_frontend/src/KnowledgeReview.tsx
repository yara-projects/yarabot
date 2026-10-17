import { useEffect, useState } from 'react';
import { api } from './api';
import { ConfirmDialog } from './ConfirmDialog';

export function ManualPhrase({ initialIntent = '' }: { initialIntent?: string }) {
  const [intents, setIntents] = useState<string[]>([]);
  const [phrase, setPhrase] = useState('');
  const [intent, setIntent] = useState(initialIntent);
  const [check, setCheck] = useState<{ status: string; reason: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => {
    const guard = (event: Event) => { if (phrase && !window.confirm('Discard this unsaved routing phrase?')) event.preventDefault(); };
    const unload = (event: BeforeUnloadEvent) => { if (phrase) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('admin:before-navigate', guard); window.addEventListener('beforeunload', unload);
    return () => { window.removeEventListener('admin:before-navigate', guard); window.removeEventListener('beforeunload', unload); };
  }, [phrase]);
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
