# YaraBot dashboard and testing loop

## Run locally

Run `streamlit run dashboard.py`. The database connection comes from `.env`.
Keep `USE_CLOUD_DB=true` to use the current Aiven school data.

## Host on Render

Create a separate Python web service from `yara-projects/yarabot`, branch `main`.
Use the free plan and Frankfurt region, matching the existing chatbot.
Build: `pip install -r requirements.txt`. Start: `python start_dashboard.py`.
Health check: `/_stcore/health`.

Alternatively import `render-dashboard.yaml` as a Blueprint; choose that custom
file path during setup. This file defines only the dashboard service.

Configure `USE_CLOUD_DB=true`, `DASHBOARD_HOSTED=true`, the existing Aiven
`CLOUD_DB_HOST`, `CLOUD_DB_PORT`, `CLOUD_DB_USER`, `CLOUD_DB_PASSWORD`, and
`CLOUD_DB_NAME`. Set `FLASK_APP_URL=https://yarabot-backend-t4cy.onrender.com`
and use the same `DASHBOARD_API_TOKEN` as the chatbot service.

Set a dedicated `DASHBOARD_ADMIN_USERNAME` and
`DASHBOARD_ADMIN_PASSWORD_HASH`. Generate the existing SHA-256 format locally
without putting the password in shell history:

```powershell
python -c "from getpass import getpass; from auth_helpers import hash_password; print(hash_password(getpass('Dashboard password: ')))"
```

Enter the resulting hash in Render's secret environment settings. Do not commit
it or include passwords in testing reports. Hosted startup refuses missing
configuration or known development passwords. CORS and XSRF protections stay on.

The dashboard is a privileged admin application: its login grants access to all
dashboard pages. It is not the chatbot's role-based login. Use it only for the
authorised testing task and school administrators.

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
admin credentials. This document is the agreed procedure, not an installed
scheduler or an automatically running repair controller.
