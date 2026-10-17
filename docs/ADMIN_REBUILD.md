# Admin dashboard and school-document workflows

## Scope and release boundary

One main admin dashboard: React + TypeScript + CSS, served on the same origin by an independent Flask API. It does not import the chatbot application or initialise its AI clients. `python start_dashboard.py` selects this primary dashboard; `--legacy-streamlit` is explicit rollback only. The old Streamlit source is retained until deployment, shared-data verification, final testing and user acceptance of stability; do not operate both production editors as competing dashboards. The current visual design is intentionally retained.

This is the separate dashboard prerequisite release, not the Phase 3 traffic-review release. Its source package excludes the unfinished chatbot app/UI integration changes. No production dashboard is certified by these local checks. On 16 October 2026, metadata preflight verified all expected columns in 19 existing Aiven tables. A schema-only snapshot (not a school-record/data backup) was saved locally; the two additive document-table definitions were then applied deliberately. No school-record values or published documents were imported. Production admin credentials and final Render deployment still require configuration; deployment evidence is recorded separately. Local test publication means publication inside disposable synthetic SQLite. Work final QA is a separate acceptance gate.

## Implemented workflows

### Review pages completed locally — 17 October 2026

The blocked-history placeholders are replaced by a privacy-safe weekly traffic
review. Phrase review shows feedback/repeat/near-miss signals and supports manually
authored phrases through the existing safety check and confirmed approval. School
knowledge review supports confirmed, version-checked almanac appends. Mark-reviewed
persists a topic fingerprint; changed weekly evidence reopens the item. No traffic
rows are deleted. Existing raw-text history remains inaccessible to these pages.

Metrics use only 14 days of content-free `query_log` metadata, bounded to 10,000
events and 100 displayed groups. Topics and intents are server-allowlisted;
unknown text never becomes a displayed label. Complaint intents and null topics
are excluded. No names, record IDs, class groups, ownership hashes, answer IDs,
questions or answers are returned. Repeat and low-score signals are approximate,
not proof of an error. Missing rate denominators display as dashes.

`python setup_database.py --admin-review-only` is the additive review-status
migration. It creates only `admin_review_resolutions`, which stores opaque keys,
fingerprints and update times. It was applied to the configured database on
17 October; no school records, live phrases, almanac content or histories were
changed. Read-only real-storage smoke requests returned HTTP 200 for both review
views and confirmed the raw-history endpoints still return 403. Hosted runtime
packages `admin_review.py` and `traffic_feedback.py`, without importing chatbot
startup or changing AI model routing. Local servers require restart to load the
new backend; this implementation is not itself a Render deployment.

Verification: 64 Python tests passed, including canary exclusions, week windows,
undefined rates, view selection, fingerprint persistence/new-evidence reopening,
stale revisions, confirmed almanac appends, CSRF and read-only guards. The NLP
audit exited 0 and the production frontend built. Work independently exercised
the sample-data browser flows: safe manual fee phrase check/confirmation/approval,
almanac cancel/no-write then confirmed append preserving versioned content,
mark-reviewed across refresh/reload/both views/relogin and sampled privacy-canary
exclusion. Its one low-severity empty-state copy finding was corrected and the
narrow retest passed. This is bounded local acceptance, not live write, hosting,
exhaustive privacy or old chatbot-failure acceptance. Detailed evidence is in the
testing chat's `dashboard-review-qa-20261017` and `dashboard-review-retest-20261017`
Markdown/JSON outputs.

- Separate admin authentication, CSRF protection, login throttling, server-side logout revocation, 30-minute idle and eight-hour absolute expiry. Hosted cookies require HTTPS. No default credentials.
- Paginated/searchable editors for students, parents, teachers, subjects, departments, class teachers/sections, timetables, exams, notices and accounts. Revisions reject stale edits. Password hashes never appear in account responses.
- Exact-ID parent-child and teacher-subject linking. No name-based identity inference or automatic account creation.
- Versioned almanac editing and manually authored routing phrases with cross-role safety rechecks. Historical raw unanswered/learned-phrase queues and their row actions remain quarantined in production. The completed weekly review above uses content-free traffic instead. Greeting/thanks/help cannot be changed here.
- System status and recent actions; confirmed re-enable only. Existing Principal emergency-disable authority is unchanged.
- Local extraction from UTF-8 CSV, XLSX, PDF, DOCX and timetable images. OCR uses Tesseract, not an external AI service. Uncertain cells and extracted source remain reviewable.
- Draft, edit, approve, publish, supersede and withdraw document states. Editing approved content revokes approval. Document revision and publication-head version are checked. Published history is immutable.
- Atomic school-record batches for students, parents, teachers, departments, subjects, exams, timetables and class mappings. Explicit IDs update; omitted IDs create. Every row is validated. Blank mapped fields replace existing values: review carefully. Account, notice, almanac and phrase bulk imports are excluded. Applied record batches cannot be withdrawn as undo; use a correction batch.

## Chatbot integration — excluded from this dashboard release

The working checkout also contains uncommitted timetable/exam tables, document retrieval and contextual-choice integration. Those chatbot app/UI changes are not bundled into this release. Helper modules needed to validate dashboard documents are packaged, but do not enable chatbot retrieval. Enabling published school-document answers requires a separate tested chatbot release and explicit `SCHOOL_DOCUMENTS_ENABLED=true`; this release does neither. Phase 4 suggestion chips remain separate.

## Import limits and review responsibilities

Sources: 8 MB, 1,000 rows, 150,000 text characters; workbooks: ten sheets; PDFs: 20 pages. Scanned PDFs: five pages with a shared 120-second OCR budget; individual passes are also bounded. One extraction runs per admin process. Unrecognised layouts require manual correction, not guessed mappings.

Approval requires explicit scope and validity dates. A generation date is not an effective-date policy. Review all days, periods (including zero), times and activities. The supplied timetable yielded five day rows and 55 period/break entries in local OCR checks, but small-text errors remained, including a misread time. This is not perfect transcription. Teachers/classes and optional alternatives must be reviewed before publication. Individual subject-choice tracking is not introduced.

## Development and packaging

Run npm ci and npm run build in admin_frontend. Flask factory: admin_app:create_app(). Vite development proxies /api to localhost:5010; a built Flask preview serves assets and API together.

Configure DASHBOARD_ADMIN_USERNAME, DASHBOARD_ADMIN_PASSWORD_HASH using the existing helper, and a random DASHBOARD_SESSION_SECRET of at least 32 characters. Existing database settings apply. Never put secrets in frontend variables or source. Use HTTPS and exactly one Gunicorn worker with threads: sessions and throttling are process-local. Restarts invalidate sessions. No keep-alive loops, external fonts or AI extraction calls are introduced.

Dockerfile.dashboard packages frontend/API plus English/Arabic Tesseract packs. Build with: docker build -f Dockerfile.dashboard -t yarabot-dashboard:local .

render-dashboard.yaml describes the replacement Docker service, not a second school dashboard. Building an image does not deploy it.

## Deliberate production rollout

### Shared-data validation — 16 October 2026

No record-copy migration was needed. The configured Aiven database was compared
read-only with authenticated in-process requests to the new dashboard API (no
network listener). All 1,590 projected records matched: students 500, teachers 50,
parents 2, departments 6, subjects 148, class teachers 28, class sections 28,
timetable entries 740, exams 56, accounts 24 and notices 8. All three parent/student
links and 50 teacher/subject links matched, with no orphaned links. The almanac
content/version matched. Account hashes, read-state metadata and notice author
metadata remain stored even when not exposed by the editor.

An encrypted full-schema/data mysqldump of 25 InnoDB tables, with routines/events/
triggers requested, was saved outside the repository and OneDrive under the
Windows user's local AppData backup folder. Saved-file decryption was verified;
database restore was **not** tested. Windows DPAPI requires the original user
profile and is not an off-device disaster-recovery guarantee. No source records,
complaints, phrases, publications or permissions were changed by this validation.

`DASHBOARD_READ_ONLY=true` rejects all data-changing API methods except session
login/logout, makes record catalogues non-editable and replaces editing tools
with read-only notices. Repository reads use MySQL read-only transactions and
read-only relationship/system lookups no longer request write locks. The Render
Blueprint defaults to this mode; local startup also supports `--read-only`.

Remaining gates: configure private dashboard admin credentials/session secret,
verify the intended deployed environment (local configuration equality alone is
not Render identity proof), complete browser-based live-data acceptance and
confirm a recoverable backup before authorising editing. Existing historical raw
chat-review queues remain quarantined; this check is not exhaustive workflow
parity, HAL integration or a completed cloud rollout. Streamlit is not deleted.

1. Rollout approved; metadata-only compatibility checks passed. A schema-only snapshot exists, not a full data backup. Verify the school's data-backup policy before real editing/imports. Current transactional workflow tests use SQLite adapters, not real MySQL concurrency certification.
2. migrations/school_documents.sql was applied deliberately on 16 October 2026; both tables were absent before the additive migration. Runtime never creates these tables. No destructive reset script was used.
3. Configure credentials, secret and database access; deploy the replacement as the one main admin service. Verify health/login/logout, disposable drafts and version conflicts before real data.
4. Deploy chatbot changes. Published-document retrieval stays disabled unless SCHOOL_DOCUMENTS_ENABLED=true is explicitly configured after the schema exists. This work has not enabled it in production.
5. Publish real school documents only with explicit authority. Validate school facts and links with school owners, then verify role boundaries, tables, stale choices and full-prefix context sequences on the deployed version.

Rollback: disable SCHOOL_DOCUMENTS_ENABLED to restore legacy timetable handling. Withdrawing removes the current document publication; older versions are not silently revived. Record-batch writes require a correction or authorised restore, not withdrawal.

## Local verification — 15 October 2026

- TypeScript/Vite production build passes: about 86.1 KB gzip JavaScript and 7.0 KB gzip CSS. Sizes are not latency measurements.
- Synthetic API/SQLite workflows cover CSRF/logout, conflicts, accounts, exact-ID links, atomic rollback, phrase rechecks and reviewed-answer appends.
- Document/chat route tests cover published-only retrieval, term selection/correction, subject follow-up, stale choices, Clear and role changes. Broader routing/privacy suites exclude one unchanged pre-existing phase-5 missing-date assertion because the refreshed almanac now contains those dates.
- JavaScript late-JSON, late-stream and parent-chip checks pass.
- Earlier synthetic browser checks covered login, student editing, expiry, 390px records layout, upload-to-draft/save, and a separately resumed saved-draft approve/publish flow. These were not one uninterrupted upload-to-publication run. File-picker stalls are not backend latency evidence. Import action confirmation now uses an in-app dialog.
- The supplied two-page syllabus was parsed locally with subject/book continuations retained. No real source document was published to school storage.
- Broader local combined run: 227 applicable Python tests pass (44.2 seconds), plus all three JavaScript session checks. The final affected-area run passes 22 tests, including an additional named-target clarification safeguard. Strict YYYY-MM-DD dates and trailing-only scope regressions are included. Restricted Windows runs hit temporary-file permission errors; normal-permission reruns passed. The Docker build and OCR smoke checks passed before the final Work routing repairs; the latest image refresh is pending a stopped local Docker engine. Earlier container checks confirmed the independent API does not load app.py or google.genai, with English/Arabic Tesseract packs installed. The production npm audit reports zero known vulnerabilities. Passing local tests is not deployed acceptance or exhaustive privacy certification.
- A subsequent preview-fixture audit found inherited Almanac helpers were not redirected to SQLite. The local preview was stopped and restarted with explicit SQLite overrides; all 12 admin workflow tests now pass, including a new isolation regression. Earlier preview-wide isolation must not be asserted for that endpoint. Work confirmed it never opened or saved the Almanac page; no live write occurred through that QA path.
- Work independently confirmed stale-write rejection, approval revocation after edits, synthetic replacement publication and superseding the previous version. It initially reproduced three context defects: unknown-subject follow-ups repeated syllabus content; a transport topic switch was captured by syllabus context; combined syllabus/timetable questions merged filters. All three were repaired and given endpoint regressions. Work's independent five-interaction retest confirmed all three exact failures fixed, HTTP 200 throughout, and no new issue demonstrated in that narrow retest. Transport used a labelled synthetic public-response stub, not an external provider response or school-fact verification. Evidence is in the QA chat's outputs/local-admin-qa-retest-20261015.md and matching JSON. This does not exhaust all context forms, real MySQL concurrency, browser file formats or deployment behaviour.

Graphify's existing graph provided orientation only; no rebuild or semantic-extraction model call was needed. Old QA artifacts and regression tests are retained at the user's request.

## Release preparation checks — 16 October 2026

- The release's synthetic admin/API/import/document/OCR checks include the production raw-queue quarantine and SQLite phrase-snapshot isolation regressions. OCR temporary files use a workspace temp directory. The initial restricted-temp failure is a verification-environment limitation, not a claimed product repair.
- NLP audit exited 0. TypeScript/Vite production build passed (86.23 KB gzip JavaScript, 7.01 KB gzip CSS); npm production audit reported zero known vulnerabilities at check time.
- Docker image `yarabot-dashboard:release-20261016` built successfully after starting the installed Docker engine. A networking-disabled container smoke test passed built-UI/health/auth-boundary checks, verified no `app.py` or `google.genai` imports, and found both English and Arabic OCR packs.
- Production-mode regression verifies legacy raw-text review endpoints/actions are denied and do not return canary complaint text. No historical rows were purged.
- Independent browser QA uses `.phase-work/serve_admin_release.py`: disposable SQLite, explicit almanac overrides, all MySQL/global almanac connections blocked, loopback-only serial server, production-mode legacy-text quarantine. Results must not be presented as live MySQL/deployment acceptance.
- Work independently checked login/logout/relogin, student validation/editing, exact-ID links, almanac stale-write rejection, historical-text quarantine and synthetic CSV upload through draft/approval/edit-revocation/reapproval/publication. Published content reopened read-only and replacement draft history retained the prior publication. The manual phrase checker initially hit the preview's blocked external-read guard because its phrase snapshot lacked a SQLite override; that fixture was repaired, given a regression, and independently rechecked. No phrase was approved, no production data was written, and a routing-safety verdict is not certification of a phrase's intended meaning.
