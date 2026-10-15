# Phase 2: content-free analytics and feedback

Scope: chat response instrumentation, feedback controls and an idempotent
`python setup_database.py --analytics-only` migration. No model, routing,
school-record, permission or complaint-form changes.

Privacy deliberately overrides raw-question collection: `question_text` stores
only static topic labels (or `other`), never submitted wording. No answer bodies,
student names/IDs, class assignments or hashed user IDs are retained. An HMAC of a
random session nonce binds feedback; it is not derived from the user's identity.
Complaint-sensitive events have only a fixed complaint intent plus operational
metadata; no question/topic/score or rephrase association, and no feedback buttons.
Existing historical stores are not purged or certified by this feature.

Feedback requires an authenticated chat session (including Guest), its CSRF token,
same-origin requests when Origin is present, answer ownership and completion.
One immutable vote per answer; optional reason is a three-value enum, never free
text. Five votes/minute per session, serialized with a MySQL advisory lock held
through commit and released on connection close. Logout invalidates ownership.

The rephrase flag means only a same-topic repeat within 30 seconds of a completed
answer in the same session. It does not establish dissatisfaction or exact wording
similarity. `other` and complaint turns do not participate. No raw pairs retained.

JSON completion means a successful reply payload; streaming completion requires
the `[DONE]` marker. Interrupted streams remain incomplete. `nlp` means an explicitly
observed scored NLP dispatch. Early returns without an observed lane are labelled
`fallback` (unattributed), not falsely credited to NLP. The score is nullable and is
not a probability.
Model-lane completion is not proof of a correct or answered question.

Expiry: feedback/rephrase eligibility excludes events older than 30 days.
Each logged turn purges up to 1,000 expired rows; physical deletion is lazy and may
lag after inactivity/backlogs. No scheduled purge is claimed. Storage/feedback
outages never interrupt delivery of the chat response; feedback reports failure.
Logging uses a two-second connection timeout, not a guarantee on total SQL latency.

Verification: synthetic Flask JSON/streaming, privacy, session/CSRF/origin guards,
ownership/duplicates/rate/expiry SQL guards, fail-open paths, rephrase SQL and NLP
audit. Live revision/requests and real migration must be verified before Phase 3.
