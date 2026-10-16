# Finish the main dashboard deployment

The prepared Render form is for `yarabot-dashboard` in Yara / Production:
Docker, `main`, Frankfurt, **Free**, `./Dockerfile.dashboard`, health `/healthz`.
Leave the root directory and Docker-command override blank. It is not a second
school dashboard: Render previously contained only the chatbot service.

## Enter credentials yourself in Render

Do not paste passwords, hashes, database secrets or session keys into chat.

- `USE_CLOUD_DB=true` and `DASHBOARD_HOSTED=true` are already filled.
- Choose `DASHBOARD_ADMIN_USERNAME` for the authorised school admin login.
- Set `DASHBOARD_ADMIN_PASSWORD_HASH` to the hash of a strong, private password.
  This release uses the project's existing SHA-256 helper/credential format.
  Run the following yourself in a terminal in the repository; the password input
  is hidden. Copy the resulting hash directly to Render, not to chat:

  ```powershell
  python -c "from getpass import getpass; from auth_helpers import hash_password; print(hash_password(getpass('New dashboard admin password: ')))"
  ```

- Use Render's **Generate** button for `DASHBOARD_SESSION_SECRET` (at least 32
  characters). Do **not** use Generate for the password-hash field: that would not
  give you a known login password.
- Copy the existing `CLOUD_DB_HOST`, `CLOUD_DB_PORT`, `CLOUD_DB_USER`,
  `CLOUD_DB_PASSWORD`, and `CLOUD_DB_NAME` values from the chatbot's Render
  environment settings. They stay in Render, not source or browser screenshots.

Before clicking **Deploy web service**, confirm the selected plan is Free and the
Dockerfile path is `./Dockerfile.dashboard`. This creates the protected admin
service with school-database access; do not expose a default or shared test login.
Free compute has limited RAM/CPU; OCR may require smaller files. No production
OCR capacity guarantee is implied by the local container test.

After it shows Live, sign in yourself and ask for final verification. Check the
release revision, health, login/logout and read-only navigation first. Do not test
writes against real school data or publish source documents without explicit
authority. A schema-only snapshot is not a full data backup: confirm the school's
backup/recovery arrangements before real edits/imports.

The old Streamlit source remains for rollback but should not be operated as a
competing editor. Chatbot document retrieval/table/chip changes are not enabled by
this dashboard release. Phase 3 traffic review and Phase 4 suggestions follow only
after the dashboard prerequisite is verified live.
