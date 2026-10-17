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

Keep `DASHBOARD_READ_ONLY=true` during shared-data validation (the Blueprint now
defaults to it). The server rejects school-data mutations, including direct API
requests; only authentication can change session state. Set it to `false` only
after acceptance and explicit approval to enable live editing. Existing records
are read from the same configured database, not copied from Streamlit or seeded
from the sample preview. Credentials are still required in read-only mode.

For local real-data validation, use `python start_dashboard.py --read-only` after
configuring private admin credentials. This is different from the sample preview.
A Windows DPAPI backup is tied to the original Windows user profile; successful
decryption is not a tested database restore or an off-device disaster backup.

For user-authorised local editing before hosting, run
`python start_dashboard.py --local-setup`. It uses the existing cloud database,
prompts privately for a username and password, and starts only on
`http://127.0.0.1:5010` with editing enabled. These credentials and the random
session secret are held only in that process, not written to `.env`, Git or the
database. Keep the terminal running. Restarting requires choosing credentials
again. Add `--read-only` if you want browsing without writes instead. Do not use
the sample preview credentials for this mode. Production hosting still requires
its own persistent private credentials and session secret in Render.

The old Streamlit source remains for rollback but should not be operated as a
competing editor. Chatbot document retrieval/table/chip changes are not enabled by
this dashboard release. The local traffic-review candidate additionally needs
`python setup_database.py --admin-review-only` and a backend restart; the configured
database already has this additive table. Verify the completed review pages after
hosting. Phase 4 suggestions remain a separate release.
