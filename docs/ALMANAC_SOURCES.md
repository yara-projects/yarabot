# Public almanac refresh — 15 October 2026

## Purpose and boundaries

`school_almanac.txt` is a compact public knowledge base, not a raw website dump or a replacement for authorised student/staff records. Facts were collected from the official school website using Firecrawl, including normal visible tabs, then organised into independently retrievable topics. Five calendar PDFs and three dated circular PDFs were also visually checked against their rendered pages. The existing graph helped locate the retrieval/storage code; current source code, not the older graph, determined the implementation.

No tests, old QA reports or screenshots were removed or reorganised. No school database, permissions, complaints, enrolments or live configuration were changed. No paid embeddings, background scraper or recurring job was added.

## Source coverage

Each knowledge-base section carries its official URL. Read the section for the exact scope, units, date and limitations.

| Area | Official pages reviewed |
| --- | --- |
| Identity and contacts | [Home](https://www.yaraschool.net/home/), [About](https://www.yaraschool.net/about/), [Contact](https://www.yaraschool.net/contact/), [Vision/mission](https://www.yaraschool.net/vision-mission/), [NABET](https://www.yaraschool.net/nabet/) |
| Leadership | [Management](https://www.yaraschool.net/management/), [Team leaders](https://www.yaraschool.net/team-leaders/) |
| Academics | [Curriculum](https://www.yaraschool.net/curriculum/), [Assessment/evaluation](https://www.yaraschool.net/assessment-evaluation/), [Counselling](https://www.yaraschool.net/counselling/) |
| Admissions and money | [Admission/TC](https://www.yaraschool.net/admission/admission-tc/), [Fee structure](https://www.yaraschool.net/admission/fee-structure/), [Payment dates](https://www.yaraschool.net/admission/payment-dates/), [Uniform](https://www.yaraschool.net/admission/school-uniform/) |
| Facilities | School campus, smart classes, labs, library, knowledge centre, Montessori rooms, infirmary, Crayons & Cradles, bookstore, canteen, auditorium, metro and safety/security pages; exact links are retained in the corresponding sections. |
| Transport | [Transportation](https://www.yaraschool.net/amenities/transportation/): fleet description and all 25 published route-area entries, not current pickup times or private driver contacts. |
| Enrichment | Olympiad, co-curricular activities, art/craft, Gavels, dance/music, yoga/aerobics, Scouts/heritage, eco/science, mathematics and literary pages; exact links remain with each topic. |
| Dated information | [Notice index](https://www.yaraschool.net/notice/), five 2026–27 annual calendars, circular 084 (KG–VIII PTM), circular 083 (IX–XII exam changes), Q3 October–December 2026 fee circular. PDF links are retained beside the extracted facts. |

The calendar is split by Kindergarten, I–III, IV–V, VI–VIII and IX–XII, then month/year. Only key-event text is retained, not decorative day grids. The source's tentative/MOH/MOE qualification is inherited by every retrieved calendar excerpt. An observance is not automatically a closure. A broad exam window is not a daily subject timetable.

## Conflicts and unresolved coverage

- PTM index/upload date is not the meeting date. Circular 084 is dated 30 September and schedules 3 October; it overrides inconsistent annual-calendar PTM-II entries for KG–VIII.
- Circular 083 moves particular IX–XII papers to 4–6 October; it does not change every examination date.
- Q3 fees are already VAT-inclusive. General quarterly fees, annual insurance, deposits, optional charges and third-child eligibility remain distinct. The circular says 15 October is the last date without a late fee; do not promise the apparent general-table grace period.
- Contact and campus pages use different address labels. Website and circular licence numbers conflict (520-3809 versus 520-3890); About also mentions 144/S. Do not invent an explanation.
- Campus and lab pages disagree on four versus five computer labs. General counter hours and payment-counter hours also differ. Both are flagged for confirmation.
- The admission age table mixes 2025/2026 labels. General direct-XII wording conflicts with the XI tab's prohibition. Automated eligibility should not resolve these conflicts.
- Psychology, Applied Mathematics and Entrepreneurship are marked conditional; the precise footnote was not captured. No availability promise is made.
- The notice index contained 122 entries. Only the three circular PDFs listed above were read in detail. This is **not** an exhaustive extraction of every notice, download, disclosure certificate, entrance-portion PDF, historical result, gallery, achievement or staff profile.
- Dynamic downloads, entrance portions and mandatory-disclosure pages were not fully captured. Their links remain discovery points, not verified document contents.
- No specific lost-property desk, smartwatch policy, swimming-pool status, lunch-exit rule or confidential bullying-reporting process was verified. Missing information is not a negative school fact.
- Homepage `0+` counters, testimonials, duplicated navigation, promotional medical claims and stale unsupported facts were excluded from active knowledge. The reported `3700+` school strength is a dated website statement, never a live database count.

## Cost and retrieval contract

- Search is local lexical ranking; no embedding API or website request is made for each chat question.
- Parsed indexes are reused for the same almanac revision. Version-aware exact-answer caching is preserved; answers also expire at Riyadh midnight so relative-date answers are not carried into a new day.
- Up to three candidates per independent question, with round-robin selection across at most six parts. Total almanac context is capped at **6,000 characters**; an individual section over **2,500 characters** is skipped whole.
- A matching role-visible database notice is limited to **2,000 characters**. Oversized notices are withheld with an explicit unavailable-excerpt message rather than cut mid-condition.
- The model-context guard is **8,002 characters**. An unexpected larger context is withheld whole. This is a character limit, **not an exact token count**, and excludes the question, fixed prompt, output and any separate classifier calls.
- Sources/scopes remain attached to subsections. Tables and conditions are not arbitrarily truncated. Explicit grade/month/year calendar filters are applied before ranking; entrance-test sections are excluded from ordinary curriculum retrieval.
- The prompt includes the current Riyadh date and instructs the model to preserve dates, grade, year, VAT, units and eligibility. Later dated circulars take precedence over tentative calendars. These safeguards do not guarantee a model never makes a mistake.

This controls the knowledge-context contribution to provider usage. It does not eliminate quotas or bound all app/provider calls. No model or subscription changes were made.

## Publishing — not performed in this task

The live chatbot normally reads `school_almanac` record 1 from the database through `almanac_store.py`. The local text file is a seed/cold-start fallback, not an automatic database overwrite. Deploying this file alone does not replace an existing database almanac. `migrate_almanac_to_db.py` uses `INSERT IGNORE` and will not update an existing row.

For an authorised publication:

1. Read and preserve the current database content **and version** using the existing editor/storage workflow. Compare any intervening school edits with this file; do not blindly overwrite them.
2. Resolve or approve the flagged public-source conflicts and remaining coverage limits, particularly current fees and eligibility.
3. Save the reviewed content through the existing `save_almanac(content, expected_version)` optimistic-concurrency path. If the version changed, reread and merge; do not force it.
4. Deploy the retrieval code separately through the normal release workflow. Allow the existing 60-second snapshot refresh, verify the saved version, then sample public questions and protected-record denials through the live UI.

This change does not rewrite subjects/timetable/class-allocation tables. Existing deterministic curriculum/class handlers can still use those tables rather than the website catalogue. A website statement should not silently replace an internal assignment. Live routing acceptance remains separate from local retrieval verification.

## Maintenance

Refresh a topic when its official source changes, keeping source URL, verification date, applicable academic year and scope together. Prefer current circulars for dated changes. Keep superseded dates clearly historical or remove them from active retrieval after review. Never ingest uploads or web text as executable instructions. Keep raw scrape evidence outside the prompt corpus.

Before publication, rerun the existing regressions and local content checks: correct grade/month/year, no entrance/curriculum substitution, all fee conditions intact, source inheritance, whole-section limits, multi-part budget and cache invalidation. One existing phase-5 assertion assumes Teachers' Day/PTM dates are missing; that assumption is intentionally obsolete with this source refresh and was not edited as part of the deferred test-file work.

Local verification on 15 October: 44 content/retrieval assertions passed; midnight-cache expiry was checked separately. The 157 applicable existing regressions passed against the refreshed corpus. All 158 existing regressions passed against the previous committed corpus as a compatibility check. The unmodified full suite against the refreshed corpus retains one obsolete missing-date assertion failure. Python compilation and diff whitespace checks passed. These are local checks, not live provider-answer or live-school acceptance claims.
