import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import {
  ArrowRight, ArrowUpRight, BookOpen, CalendarDays,
  Check, ChevronLeft, ChevronRight, CircleHelp, FileText, GraduationCap, LayoutDashboard,
  Library, LockKeyhole, LogOut, Menu, MessageSquare, Plus, RefreshCw, Search,
  ShieldCheck, Sparkles, Upload, Users, X, Pencil, Trash2, AlertCircle,
} from 'lucide-react';
import { api, ApiError, setCsrf } from './api';
import type { Resource, Row, Session } from './api';
import { ImportWorkspace } from './ImportWorkspace';
import { Relationships, SystemStatus, PhraseReview } from './AdminTools';
import { ManualPhrase, UnansweredReview } from './KnowledgeReview';

const NAV = [
  { label: 'Workspace', items: [{ id: 'overview', label: 'Overview', icon: LayoutDashboard }, { id: 'imports', label: 'Import centre', icon: Upload }, { id: 'relations', label: 'Links & assignments', icon: Users }, { id: 'system', label: 'System status', icon: ShieldCheck }] },
  { label: 'School management', items: [{ id: 'students', label: 'Students', icon: GraduationCap }, { id: 'parents', label: 'Parents', icon: Users }, { id: 'teachers', label: 'Teachers', icon: Users }, { id: 'departments', label: 'Departments', icon: Library }, { id: 'class-teachers', label: 'Class teachers', icon: Users }, { id: 'class-sections', label: 'Class sections', icon: LayoutDashboard }, { id: 'accounts', label: 'Chatbot accounts', icon: ShieldCheck }] },
  { label: 'Academics', items: [{ id: 'subjects', label: 'Subjects', icon: BookOpen }, { id: 'timetable', label: 'Timetables', icon: CalendarDays }, { id: 'exams', label: 'Exam schedules', icon: CalendarDays }] },
  { label: 'Nova & information', items: [{ id: 'almanac', label: 'School almanac', icon: FileText }, { id: 'notices', label: 'Notices', icon: MessageSquare }, { id: 'suggestions', label: 'Unanswered questions', icon: CircleHelp }, { id: 'phrases', label: 'Phrase review', icon: Sparkles }] },
];
const ITEMS = NAV.flatMap(group => group.items);
const DESCRIPTIONS: Record<string, string> = {
  overview: 'A little clarity for everything you manage.', imports: 'Bring school documents into one organised workflow.',
  students: 'Keep student records accurate and easy to find.', teachers: 'Your teaching team, departments and assignments.',
  departments: 'Organise teaching teams and their department heads.', 'class-teachers': 'The class teacher responsible for each division.',
  'class-sections': 'Explicit Boys and Girls mappings used in school reports.', accounts: 'Existing chatbot accounts and linked record IDs.',
  subjects: 'The subjects and classes in your school catalogue.', timetable: 'Review the teaching periods currently stored in the school database.',
  exams: 'Published assessment dates, classes and subjects.', almanac: 'The verified school information behind Nova’s answers.',
  notices: 'Keep your school community informed, with the right audience.', suggestions: 'Questions that need verified school information.',
  phrases: 'Review how people ask questions before approving new routing phrases.',
  relations: 'Manage explicit parent/student and teacher/subject links.', system: 'Review availability and deliberately re-enable Nova.', parents: 'Parent records; child links are managed under Links & assignments.',
};
function route() { const id = window.location.hash.slice(1); return ITEMS.some(item => item.id === id) ? id : 'overview'; }
function useData<T>(path: string, revision = 0) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true });
    api<T>(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ data, loading: false });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ error: error.message, loading: false });
    });
    return () => controller.abort();
  }, [path, revision]);
  return state;
}
function Brand({ light = false }: { light?: boolean }) {
  return <div className={`brand ${light ? 'brand-light' : ''}`}><span className="brand-symbol">y<span>·</span></span><div>yara<span className="brand-sub">SCHOOL WORKSPACE</span></div></div>;
}
function Spinner() { return <span className="spinner" aria-hidden="true" />; }
function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-box" role="alert"><AlertCircle size={19} /><div><strong>We couldn’t complete that</strong><p>{message}</p>{retry && <button className="text-button" onClick={retry}>Try again <ArrowRight size={14} /></button>}</div></div>;
}
function Skeleton() { return <div aria-label="Loading" role="status" className="skeleton-stack"><div className="skeleton short" /><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>; }

export default function App() {
  const [auth, setAuth] = useState<Session | null>(null);
  const [bootError, setBootError] = useState('');
  const [boot, setBoot] = useState(0);
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api<Session>('/session', { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) { setCsrf(value.csrf); setAuth(value); setBootError(''); }
    }).catch(error => { if (!controller.signal.aborted) setBootError(error.message); });
    return () => controller.abort();
  }, [boot]);
  useEffect(() => {
    const expire = () => { setAuth(null); setExpired(true); setBoot(n => n + 1); };
    window.addEventListener('admin:expired', expire);
    return () => window.removeEventListener('admin:expired', expire);
  }, []);
  if (bootError) return <div className="boot-screen"><Brand /><ErrorBox message={bootError} retry={() => setBoot(n => n + 1)} /></div>;
  if (!auth) return <div className="boot-screen"><Brand /><Spinner /><p>Opening your workspace…</p></div>;
  if (!auth.authenticated) return <Login expired={expired} onLogin={value => { setAuth(value); setExpired(false); }} />;
  return <Workspace key={auth.csrf} username={auth.username!} onLogout={() => { setAuth(null); setBoot(n => n + 1); window.location.hash = ''; }} />;
}

function Login({ onLogin, expired }: { onLogin: (value: Session) => void; expired: boolean }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const value = await api<{ username: string; csrf: string }>('/login', { method: 'POST', body: JSON.stringify({ username, password }) });
      setPassword(''); setCsrf(value.csrf);
      onLogin({ ...value, authenticated: true, idle_minutes: 30 });
    } catch (error) { setError((error as Error).message); } finally { setBusy(false); }
  }
  return <main className="login-layout">
    <section className="login-story"><Brand light /><div className="login-story-content"><span className="eyebrow light">YARA INTERNATIONAL SCHOOL</span><h1>A thoughtful space<br />for school life.</h1><p>Your records, your teaching teams, and Nova’s knowledge. All connected. All in one place.</p><div className="orbit-art" aria-hidden="true"><div className="orbit-ring" /><div className="orbit-ring inner" /><div className="orbit-centre"><GraduationCap size={52} strokeWidth={1.2} /></div><span className="orbit-label first"><BookOpen size={17} />School knowledge</span><span className="orbit-label second"><Users size={17} />People & learning</span><span className="orbit-dot" /></div></div><span className="story-footer">Made for focused school administration.</span></section>
    <section className="login-side"><div className="login-mobile-brand"><Brand /></div><div className="login-form-wrap"><span className="secure-label"><ShieldCheck size={16} />PRIVATE ADMIN WORKSPACE</span><h2>Welcome back.</h2><p className="muted">Sign in to pick up where you left off.</p>{expired && <p className="inline-notice">Your session ended. Sign in again to continue.</p>}<form onSubmit={submit} className="login-form"><label>Username<input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" placeholder="Your admin username" required maxLength={100} disabled={busy} /></label><label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" placeholder="Enter your password" required maxLength={512} disabled={busy} /></label>{error && <p role="alert" className="field-error">{error}</p>}<button className="button primary wide" disabled={busy}>{busy ? <Spinner /> : <>Sign in to workspace <ArrowRight size={18} /></>}</button></form><div className="login-footnote"><LockKeyhole size={15} /><span>For authorised school administrators only.<br />Contact your administrator if you need access.</span></div></div><span className="login-bottom">Yara International School · Riyadh</span></section>
  </main>;
}

function Workspace({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [page, setPage] = useState(route);
  const [mobile, setMobile] = useState(false);
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 800px)').matches);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState('');
  const [toast, setToast] = useState('');
  const { data: catalog, error: catalogError } = useData<{ resources: Record<string, Resource>; legacy_review_available: boolean }>('/catalog');
  const titleRef = useRef<HTMLHeadingElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 800px)');
    const update = () => { setNarrow(media.matches); if (!media.matches) setMobile(false); };
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!mobile || !narrow) return;
    const buttons = () => Array.from(sidebarRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
    buttons()[0]?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setMobile(false); menuRef.current?.focus(); }
      if (event.key !== 'Tab') return;
      const targets = buttons();
      const first = targets[0], last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    window.addEventListener('keydown', trap);
    return () => window.removeEventListener('keydown', trap);
  }, [mobile, narrow]);
  useEffect(() => {
    const handler = () => {
      const next = route();
      if (next !== page && !window.dispatchEvent(new Event('admin:before-navigate', { cancelable: true }))) {
        window.history.replaceState(null, '', `#${page}`); return;
      }
      setPage(next); setMobile(false);
    };
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, [page]);
  useEffect(() => { document.title = `${ITEMS.find(item => item.id === page)?.label} · Yara`; titleRef.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); }, [page]);
  useEffect(() => { if (!toast) return; const id = window.setTimeout(() => setToast(''), 4500); return () => window.clearTimeout(id); }, [toast]);
  function navigate(id: string) { window.location.hash = id; setMobile(false); }
  async function logout() { setSigningOut(true); try { await api('/logout', { method: 'POST' }); setCsrf(''); onLogout(); } catch (error) { setSignOutError((error as Error).message); setSigningOut(false); } }
  const current = ITEMS.find(item => item.id === page)!;
  const section = NAV.find(group => group.items.some(item => item.id === page))!.label;
  const dateLabel = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Riyadh' }).format(new Date());
  return <div className="workspace"><a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); titleRef.current?.focus(); }}>Skip to content</a>{mobile && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobile(false)} />}
    <aside ref={sidebarRef} inert={narrow && !mobile} role={narrow && mobile ? 'dialog' : undefined} aria-modal={narrow && mobile ? true : undefined} className={`sidebar ${mobile ? 'is-open' : ''}`} aria-label="Main navigation"><div className="sidebar-head"><Brand light /><button className="icon-button mobile-close" aria-label="Close navigation" onClick={() => { setMobile(false); menuRef.current?.focus(); }}><X size={20} /></button></div><div className="school-tag"><span className="school-avatar">YIS</span><div>Yara International School<small>Administration</small></div></div><nav>{NAV.map(group => <div className="nav-group" key={group.label}><span className="nav-label">{group.label}</span>{group.items.map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => navigate(item.id)} aria-current={page === item.id ? 'page' : undefined}><item.icon size={18} strokeWidth={1.7} /><span>{item.label}</span>{page === item.id && <span className="nav-active-dot" />}</button>)}</div>)}</nav><div className="sidebar-footer"><div className="admin-avatar">{username.slice(0, 2).toUpperCase()}</div><div className="admin-identity"><strong>{username}</strong><span>School administrator</span></div><button className="icon-button logout" aria-label="Sign out" title="Sign out" onClick={logout} disabled={signingOut}>{signingOut ? <Spinner /> : <LogOut size={17} />}</button></div></aside>
    <div className="workspace-main" inert={narrow && mobile}><header className="topbar"><button ref={menuRef} className="icon-button mobile-toggle" onClick={() => setMobile(true)} aria-label="Open navigation" aria-expanded={mobile}><Menu size={21} /></button><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={13} /><strong>{current.label}</strong></div><div className="topbar-right"><span className="topbar-date">{dateLabel}</span><span className="private-badge"><ShieldCheck size={13} />Admin access</span></div></header><main id="main-content" className="main-content" key={page}><div className="page-heading"><div><span className="eyebrow">{section}</span><h1 ref={titleRef} tabIndex={-1}>{current.label}</h1><p>{DESCRIPTIONS[page]}</p></div><span className="page-number">YIS / ADMIN</span></div>{signOutError && <ErrorBox message={signOutError} />}{catalogError && <ErrorBox message={catalogError} />}
      {(page === 'phrases' || page === 'suggestions') && catalog && !catalog.legacy_review_available
        ? <section className="panel"><div className="panel-padding"><h2>Historical review is protected</h2><p>Older chat-text queues are quarantined to protect private information. Privacy-safe traffic review will be released separately.</p></div>{page === 'phrases' && <ManualPhrase />}</section>
        : page === 'overview' ? <Overview navigate={navigate} /> : page === 'almanac' ? <Almanac notify={setToast} /> : page === 'imports' ? <ImportIntro /> : page === 'relations' ? <Relationships /> : page === 'system' ? <SystemStatus /> : page === 'phrases' ? <PhraseReview /> : page === 'suggestions' ? <UnansweredReview /> : catalog?.resources[page] ? <Records key={page} resource={page} spec={catalog.resources[page]} notify={setToast} /> : !catalogError ? <Skeleton /> : null}
      <footer className="workspace-footnote"><span>Yara International School</span><span><LockKeyhole size={12} /> Changes are saved only when you confirm.</span></footer>
    </main></div>{toast && <div className="toast" role="status"><Check size={18} />{toast}<button className="icon-button" onClick={() => setToast('')} aria-label="Dismiss notification"><X size={16} /></button></div>}
  </div>;
}

type Counts = { students: number; teachers: number; subjects: number; accounts: number; suggestions: number; attendance_risk: number; pending_fees: number };
function Overview({ navigate }: { navigate: (page: string) => void }) {
  const [revision, setRevision] = useState(0);
  const { data, loading, error } = useData<Counts>('/overview', revision);
  const shortcuts = [
    { title: 'Student records', page: 'students', text: 'Find a student. Keep the essentials up to date.', icon: GraduationCap, color: 'sage' },
    { title: 'Teaching team', page: 'teachers', text: 'Staff profiles, departments and class assignments.', icon: Users, color: 'sand' },
    { title: 'Timetables', page: 'timetable', text: 'Teaching periods, subjects and class divisions.', icon: CalendarDays, color: 'blue' },
    { title: 'School almanac', page: 'almanac', text: 'Give Nova accurate, verified school information.', icon: BookOpen, color: 'sage' },
    { title: 'School notices', page: 'notices', text: 'Share an announcement with the right audience.', icon: MessageSquare, color: 'sand' },
    { title: 'Import centre', page: 'imports', text: 'Extract a school document into a reviewable draft.', icon: Upload, color: 'blue' },
  ];
  return <><section className="overview-hero"><div><span className="eyebrow light">LESS ADMIN. MORE CLARITY.</span><h2>Your school,<br /><span>beautifully organised.</span></h2><p>A focused workspace for the people, information<br className="desktop-break" /> and everyday details that keep school moving.</p><button className="button hero-button" onClick={() => navigate('almanac')}>Manage school knowledge <ArrowUpRight size={16} /></button></div><div className="hero-illustration" aria-hidden="true"><div className="illustration-grid"><span /><span /><span /><span /><span><GraduationCap size={42} strokeWidth={1.1} /></span><span /><span /><span /><span /></div><span className="illustration-caption">PEOPLE · LEARNING · KNOWLEDGE</span></div></section>
    <div className="section-heading"><h2>At a glance</h2><button className="text-button" onClick={() => setRevision(n => n + 1)} disabled={loading}><RefreshCw size={14} className={loading ? 'rotating' : ''} />Refresh counts</button></div>{error ? <ErrorBox message={error} retry={() => setRevision(n => n + 1)} /> : <div className="metrics-grid">{[{ key: 'students', label: 'Students', icon: GraduationCap }, { key: 'teachers', label: 'Teachers', icon: Users }, { key: 'subjects', label: 'Subjects', icon: BookOpen }, { key: 'accounts', label: 'Chatbot accounts', icon: ShieldCheck }].map(item => <div className="metric" key={item.key}><div className="metric-label">{item.label}<item.icon size={18} /></div><strong>{loading ? <span className="skeleton metric-skeleton" /> : data?.[item.key as keyof Counts]?.toLocaleString() ?? '—'}</strong><span className="metric-note">Current database records</span></div>)}</div>}
    <div className="section-heading"><h2>Your everyday essentials</h2><span className="subtle">A shorter route to what matters</span></div><div className="shortcut-grid">{shortcuts.map(item => <button className="shortcut" key={item.page} onClick={() => navigate(item.page)}><div className={`shortcut-icon ${item.color}`}><item.icon size={21} strokeWidth={1.7} /></div><ArrowUpRight size={17} className="shortcut-arrow" /><h3>{item.title}</h3><p>{item.text}</p></button>)}</div>
    {data && <section className="attention-strip"><span className="attention-icon"><CircleHelp size={22} /></span><div><h3>Keep an eye on the details</h3><p>{data.suggestions} unanswered questions · {data.attendance_risk} students below 75% attendance · {data.pending_fees} pending fee statuses</p></div><button className="text-button" onClick={() => navigate('suggestions')}>Review questions <ArrowRight size={15} /></button></section>}
  </>;
}

function Records({ resource, spec, notify }: { resource: string; spec: Resource; notify: (message: string) => void }) {
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(25);
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<{ row: Row | null; deleting: boolean } | null>(null);
  const { data, loading, error } = useData<{ rows: Row[]; total: number }>(`/records/${resource}?q=${encodeURIComponent(search)}&page=${page}&size=${size}`, revision);
  const refresh = useCallback(() => setRevision(n => n + 1), []);
  function submit(event: FormEvent) { event.preventDefault(); setPage(1); setSearch(query.trim()); }
  return <section className="panel records-panel"><div className="panel-heading"><div><h2>{spec.title}</h2><span className="subtle">{loading ? 'Loading records…' : `${data?.total.toLocaleString() ?? '—'} records`}</span></div><div className="button-group"><button className="button secondary compact" onClick={refresh} disabled={loading} aria-label="Refresh records"><RefreshCw size={16} /></button>{spec.editable && <button className="button primary compact" onClick={() => setEditing({ row: null, deleting: false })}><Plus size={16} />Add record</button>}</div></div><div className="table-toolbar"><form onSubmit={submit} className="search-form"><Search size={17} /><input aria-label="Search records" placeholder="Search these records…" value={query} maxLength={200} onChange={event => setQuery(event.target.value)} /><button className="text-button" type="submit">Search</button></form><label className="rows-label">Rows<select value={size} onChange={event => { setSize(Number(event.target.value)); setPage(1); }}><option>25</option><option>50</option><option>100</option></select></label></div>
    {!spec.editable && <div className="read-only-note"><ShieldCheck size={14} />Read-only in this build. Existing editing workflows are being migrated with their validation.</div>}
    {loading ? <div className="table-loading"><Skeleton /></div> : error ? <div className="panel-padding"><ErrorBox message={error} retry={refresh} /></div> : !data?.rows.length ? <Empty icon={<Search size={28} />} title={search ? 'No matching records' : 'No records here yet'} text={search ? 'Try a different name, class or record ID.' : 'Records will appear when they are added to the school database.'} /> : <div className="table-scroll" tabIndex={0} aria-label={`${spec.title} table, scroll for more columns`}><table><thead><tr><th>ID</th>{spec.fields.filter(f => f.key !== spec.pk).map(f => <th key={f.key}>{f.label}</th>)}{spec.editable && <th><span className="sr-only">Actions</span></th>}</tr></thead><tbody>{data.rows.map(row => <tr key={String(row[spec.pk])}><td className="id-cell">{row[spec.pk]}</td>{spec.fields.filter(f => f.key !== spec.pk).map(f => <td key={f.key}>{['fees_status', 'priority', 'role', 'school_section'].includes(f.key) ? <span className={`record-tag ${row[f.key] === 'pending' || row[f.key] === 'urgent' ? 'amber' : ''}`}>{String(row[f.key] ?? '—')}</span> : f.kind === 'textarea' ? <span className="cell-excerpt" title={String(row[f.key] ?? '')}>{String(row[f.key] ?? '—')}</span> : String(row[f.key] ?? '—')}</td>)}{spec.editable && <td><div className="row-actions"><button className="icon-button" aria-label={`Edit record ${row[spec.pk]}`} onClick={() => setEditing({ row, deleting: false })}><Pencil size={15} /></button><button className="icon-button danger" aria-label={`Delete record ${row[spec.pk]}`} onClick={() => setEditing({ row, deleting: true })}><Trash2 size={15} /></button></div></td>}</tr>)}</tbody></table></div>}
    <div className="pagination"><span>{data?.total ? `${(page - 1) * size + 1}–${Math.min(page * size, data.total)} of ${data.total}` : '0 records'}</span><div><button className="icon-button" aria-label="Previous page" disabled={loading || page <= 1} onClick={() => setPage(n => n - 1)}><ChevronLeft size={18} /></button><span>Page {page}</span><button className="icon-button" aria-label="Next page" disabled={loading || !data || page * size >= data.total} onClick={() => setPage(n => n + 1)}><ChevronRight size={18} /></button></div></div>
    {editing && <RecordEditor resource={resource} spec={spec} row={editing.row} deleting={editing.deleting} close={() => setEditing(null)} saved={() => { setEditing(null); refresh(); notify(editing.deleting ? 'Record deleted.' : 'Changes saved.'); }} />}
  </section>;
}

function RecordEditor({ resource, spec, row, deleting, close, saved }: { resource: string; spec: Resource; row: Row | null; deleting: boolean; close: () => void; saved: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(spec.fields.map(f => [f.key, String(row?.[f.key] ?? '')])));
  const [newPassword, setNewPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { const element = dialog.current!; element.showModal(); return () => element.close(); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await api(`/records/${resource}${row ? '/' + encodeURIComponent(String(row[spec.pk])) : ''}`, { method: deleting ? 'DELETE' : row ? 'PUT' : 'POST', body: JSON.stringify({ record: values, revision: row?._revision, ...(resource === 'accounts' ? { new_password: newPassword } : {}) }) }); setNewPassword(''); saved(); }
    catch (error) { setError((error as Error).message); setBusy(false); }
  }
  return <dialog ref={dialog} className="editor-dialog" aria-labelledby="editor-title" onCancel={event => { event.preventDefault(); if (!busy) close(); }}><form onSubmit={submit}><div className="dialog-heading"><div><span className="eyebrow">{spec.title}</span><h2 id="editor-title">{deleting ? 'Delete this record?' : row ? 'Edit record' : 'Add a record'}</h2></div><button type="button" className="icon-button" onClick={close} disabled={busy} aria-label="Close editor"><X size={20} /></button></div>{deleting ? <p className="delete-warning">This will permanently delete record <strong>{row?.[spec.pk]}</strong> from the connected school database. Linked records may prevent deletion. This cannot be undone here.</p> : <div className="form-grid">{spec.fields.map(f => <label key={f.key} className={f.kind === 'textarea' ? 'full-width' : ''}>{f.label}{!f.required && <span className="optional">Optional</span>}{f.kind === 'select' ? <select required={f.required} value={values[f.key]} disabled={busy} onChange={e => setValues({ ...values, [f.key]: e.target.value })}><option value="">Choose…</option>{f.options?.map(value => <option key={value}>{value}</option>)}</select> : f.kind === 'textarea' ? <textarea rows={7} required={f.required} value={values[f.key]} disabled={busy} onChange={e => setValues({ ...values, [f.key]: e.target.value })} /> : <input required={f.required} type={f.kind === 'number' ? 'number' : f.kind === 'date' ? 'date' : 'text'} step={f.key === 'attendance_pct' ? '0.01' : '1'} min={['attendance_pct', 'period_no', 'linked_id'].includes(f.key) ? 0 : f.kind === 'number' ? 1 : undefined} max={f.key === 'attendance_pct' ? 100 : undefined} maxLength={150} value={values[f.key]} disabled={busy || (!!row && f.key === spec.pk)} onChange={e => setValues({ ...values, [f.key]: e.target.value })} />}</label>)}</div>}{resource === 'accounts' && !deleting && <label>{row ? 'New password (blank keeps current password)' : 'Initial password'}<input type="password" autoComplete="new-password" minLength={12} maxLength={512} required={!row} disabled={busy} value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label>}{error && <ErrorBox message={error} />}<div className="dialog-footer"><button type="button" className="button secondary" onClick={close} disabled={busy}>Cancel</button><button type="submit" className={`button ${deleting ? 'destructive' : 'primary'}`} disabled={busy}>{busy ? <Spinner /> : deleting ? <><Trash2 size={16} />Delete record</> : <><Check size={16} />Save changes</>}</button></div></form></dialog>;
}

function Almanac({ notify }: { notify: (message: string) => void }) {
  const [revision, setRevision] = useState(0);
  const { data, loading, error } = useData<{ content: string; version: number }>('/almanac', revision);
  return <section className="panel"><div className="panel-heading"><div><h2>School knowledge, kept current</h2><span className="subtle">Only verified school information belongs here.</span></div><button className="button secondary compact" onClick={() => { if (window.dispatchEvent(new Event('admin:before-navigate', { cancelable: true }))) setRevision(n => n + 1); }} disabled={loading}><RefreshCw size={15} />Reload</button></div>{loading ? <div className="panel-padding"><Skeleton /></div> : error ? <div className="panel-padding"><ErrorBox message={error} retry={() => setRevision(n => n + 1)} /></div> : data ? <AlmanacEditor key={`${revision}-${data.version}`} data={data} notify={notify} /> : null}</section>;
}
function AlmanacEditor({ data, notify }: { data: { content: string; version: number }; notify: (message: string) => void }) {
  const [content, setContent] = useState(data.content);
  const [version, setVersion] = useState(data.version);
  const [baseline, setBaseline] = useState(data.content);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [conflict, setConflict] = useState(false);
  const dirty = content !== baseline;
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ''; } }; window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard); }, [dirty]);
  useEffect(() => {
    const guard = (event: Event) => { if (dirty && !window.confirm('Discard your unsaved almanac changes and continue?')) event.preventDefault(); };
    window.addEventListener('admin:before-navigate', guard);
    return () => window.removeEventListener('admin:before-navigate', guard);
  }, [dirty]);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { const result = await api<{ version: number }>('/almanac', { method: 'PUT', body: JSON.stringify({ content, version }) }); setVersion(result.version); setBaseline(content); notify('Almanac saved. Nova normally receives changes within a minute.'); }
    catch (error) { setError((error as Error).message); setConflict(error instanceof ApiError && error.status === 409); } finally { setBusy(false); }
  }
  return <form onSubmit={save} className="almanac-form"><div className="editor-tip"><BookOpen size={19} /><p>Keep each topic under a clear heading, with its source, dates and scope. Student records and private staff details do not belong in the almanac.</p></div><label htmlFor="almanac-content" className="sr-only">Almanac content</label><textarea id="almanac-content" className="almanac-content" value={content} disabled={busy} onChange={event => setContent(event.target.value)} spellCheck={false} maxLength={500000} />{error && <ErrorBox message={error} />}<div className="almanac-footer"><span>{content.length.toLocaleString()} characters · Version {version}{dirty ? ' · Unsaved changes' : ' · No unsaved changes'}</span><button className="button primary" disabled={busy || !dirty || conflict || !content.trim()}>{busy ? <Spinner /> : <><Check size={16} />Save changes</>}</button></div></form>;
}
function Empty({ icon, title, text }: { icon: ReactNode; title: string; text: string }) { return <div className="empty-state"><span>{icon}</span><h3>{title}</h3><p>{text}</p></div>; }
function ImportIntro() { return <ImportWorkspace />; }
