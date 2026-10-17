# YaraBot dashboard and testing loop

## Run locally

The primary dashboard is React + TypeScript, served by the independent Flask
admin API. Install `requirements-dashboard.txt`, then run `npm ci` and
`npm run build` inside `admin_frontend`. From the repository root, run
`python start_dashboard.py` and open `http://127.0.0.1:5010`.

The connection comes from `.env`; this launcher is **not** the disposable sample
preview. Configure `DASHBOARD_ADMIN_USERNAME`, `DASHBOARD_ADMIN_PASSWORD_HASH`
and a `DASHBOARD_SESSION_SECRET` of at least 32 characters. With
`USE_CLOUD_DB=true`, it accesses the existing Aiven data and confirmed edits can
affect the live chatbot. Do not switch the sample preview to production data
without separately agreeing on read-only validation and backup arrangements.

## Host on Render

Use a Docker web service from `yara-projects/yarabot`, branch `main`, with
`./Dockerfile.dashboard`, the free plan and Frankfurt region. Leave the Docker
command override blank; the image starts the React/Flask dashboard with Gunicorn.
Health check: `/healthz`. Full setup: `docs/DASHBOARD_DEPLOYMENT.md`.

Alternatively import `render-dashboard.yaml` as a Blueprint; choose that custom
file path during setup. This file defines only the dashboard service.

Configure `USE_CLOUD_DB=true`, `DASHBOARD_HOSTED=true`, the existing Aiven
`CLOUD_DB_HOST`, `CLOUD_DB_PORT`, `CLOUD_DB_USER`, `CLOUD_DB_PASSWORD`, and
`CLOUD_DB_NAME`. Set a private `DASHBOARD_SESSION_SECRET` of at least 32 characters.
The primary dashboard does not require `FLASK_APP_URL` or `DASHBOARD_API_TOKEN`.

Set a dedicated `DASHBOARD_ADMIN_USERNAME` and
`DASHBOARD_ADMIN_PASSWORD_HASH`. Generate the existing SHA-256 format locally
without putting the password in shell history:

```powershell
python -c "from getpass import getpass; from auth_helpers import hash_password; print(hash_password(getpass('Dashboard password: ')))"
```

Enter the resulting hash in Render's secret environment settings. Do not commit
it or include passwords in testing reports. Hosted startup refuses missing
configuration or known development passwords. Same-origin CSRF protections stay on.

The dashboard is a privileged admin application: its login grants access to all
dashboard pages. It is not the chatbot's role-based login. Use it only for the
authorised testing task and school administrators.

## Legacy dashboard retirement

The old Streamlit implementation was retired after the React dashboard was
accepted as the primary dashboard. `python start_dashboard.py` now starts only
the React/Flask application. Git history retains the pre-removal implementation
if an authorised recovery investigation is ever required.

## Bounded test–fix–retest process

Testing chat: **Benchmark YaraBot responses**. Coding chat: this YaraBot project.
Tests use the current school database, as requested. There is no staging copy.

1. Test the deployed chatbot and dashboard through actual browser logins. Keep
   the original V5 failure sequences as regression cases, and add natural
   paraphrases, multi-turn corrections, role-denial checks and UI checks.
2. Save private JSON/Markdown evidence in the testing chat's local `outputs`
   directory. Each case records role, preceding turns, question, actual reply,
   expected behaviour, result, response times, target URL and observable deployed
   version. Mark missing accounts and unverified school facts as blocked.
3. The coding chat reads the evidence, reproduces confirmed failures, adds a
   regression test and makes a narrow fix. Run relevant tests and the NLP audit.
4. Push authorised fixes, confirm deployment, then explicitly message the testing
   chat with the fixed cases and neighbouring regressions to replay.
5. Stop after three repair rounds per batch, or when all verifiable cases pass.
   Report unresolved failures and blocked checks. No task may independently
   start more chats or expand its messaging permissions.

### Dashboard mutation protocol

Before any edit, persist a private restoration journal with the record's stable
ID, original value/version, proposed value and dependent chatbot question. One
edit at a time. Do not delete records, send notices or complaints, change account
permissions, or toggle service availability as part of ordinary automated tests.

Save once through the dashboard. Independently reread storage using an authorised
read-only database connection, or report database verification blocked; reloading
the dashboard alone is not independent verification. Capture the dependent live
bot answer after the cache TTL (normally 60 seconds for almanac/phrases).

Restore the original value through the dashboard even if a test fails. Confirm
storage and the restored live answer. Mark the journal restored only after both
checks. If someone else edited the same record, do not overwrite their edit:
stop and report the conflict and the outstanding test change. If restoration
fails, stop the entire batch and report the exact remaining change.

School record, almanac and phrase data have different save paths; test each
explicitly. Never approve a phrase only because a generated answer sounds good:
run the existing routing safety check and verify the live role-specific result.

## Current automation status

The first chatbot pilot has been dispatched to the selected testing chat.
Dashboard hosting still requires access to the Yara Render account and dedicated
admin credentials. The approved **YaraBot test–fix–retest pilot** heartbeat is
active every 30 minutes in the coding chat, with a maximum of three repair rounds.
It waits for database recovery, stays quiet on unchanged blocks, and records
progress in ignored `qa_loop_state.json`. Keep the computer on and Codex running.
