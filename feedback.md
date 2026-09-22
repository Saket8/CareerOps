## Review outcome

The design intent is strong, but the production-safety claim is not yet justified. The most urgent risks are false-positive application confirmation, and duplicate submissions after partial failures. I made no changes.

### Findings

| Priority | What is wrong / why it matters / evidence | Recommended improvement | Complexity |
|---|---|---|---|
 **CRITICAL** | **The confirmation rule is weaker than the architecture invariant.** The architecture requires the green `already-applied` badge, but the verifier accepts confirmation text alone and the browser code promotes any `saveapply` URL or “applied to” page content to confirmed. This can falsely report a real application that was not completed. Evidence: [architecture.md](/C:/Users/2016tu/Desktop/Projects/Naukri/architecture.md:16), [verifier.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/verifier.py:138), [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:552). | Make a post-submit reload of the canonical listing and a visible badge assertion mandatory for `APPLIED_CONFIRMED`. Retain weaker signals only as `SUBMISSION_UNVERIFIED`. | Medium |
| **CRITICAL** | **Idempotency is not durable across the irreversible click.** The application row is saved only after browser submission returns; a crash, timeout, database rollback, or process kill after clicking Submit can lead to retrying the same job. There is also no unique constraint on `applications.job_id`, so concurrent actors can both pass the read-then-write check. Evidence: [application.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/application.py:73), [application.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/application.py:107), [models.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/database/models.py:151). | Persist an atomic application intent/lease before browser interaction; add `UNIQUE(job_id)` or a dedicated attempt table with an idempotency key; resume only explicitly recoverable attempts. | Large |
| **HIGH** | **Authentication and several configured safety stops fail open.** `_ensure_authenticated()` returns a Boolean but its result is ignored. The Playwright flow detects CAPTCHA but not MFA, OTP, payment, or login state before proceeding. Configuration advertises all of those stop controls. Evidence: [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:69), [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:327), [config.yaml](/C:/Users/2016tu/Desktop/Projects/Naukri/config/config.yaml:67). | Treat unsuccessful authentication and every configured barrier as terminal `NEEDS_MANUAL_INTERVENTION`/`APPLICATION_BLOCKED` states before Apply can be clicked. | Medium |
| **HIGH** | **Questionnaire handling can submit an untruthful answer.** Any visible “YES” chip is selected regardless of the question, and normal form handling ignores selects, radios, checkboxes, validation errors, and whether the intended resume was accepted. This breaches the candidate-truth boundary. Evidence: [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:452), [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:501). | Identify controls and their associated labels, resolve each through the candidate-answer resolver, and stop on every unknown or unverified option. Confirm upload and validation before submission. | Large |
| **HIGH** | **Run persistence and recovery are fragile.** One database session spans discovery, resume generation, browser actions, email, and retention. An exception can roll back the application record after the portal action; failed runs are not marked failed because `finish_run(...SUCCESS)` is only on the happy path. Retention opens a second session and may contend with the first SQLite write transaction. Evidence: [orchestrator.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/orchestrator.py:62), [orchestrator.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/orchestrator.py:251), [retention_manager.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/maintenance/retention_manager.py:98). | Commit short-lived state transitions before external effects; isolate reporting/retention; wrap the run in a top-level failure handler that records a terminal failure state and error summary. | Large |
| **HIGH** | **GitHub Actions cannot reliably preserve state, and its dry-run input is ignored.** Cache keys include `github.run_id`, so every run writes a new cache and only opportunistically restores a prefix match. Meanwhile `main.py` overrides the `DRY_RUN` environment value unless `--dry-run` is passed, but the workflow never passes that flag. Loss of state reopens duplicate-application risk. Evidence: [career_agent_daily.yml](/C:/Users/2016tu/Desktop/Projects/Naukri/.github/workflows/career_agent_daily.yml:42), [career_agent_daily.yml](/C:/Users/2016tu/Desktop/Projects/Naukri/.github/workflows/career_agent_daily.yml:79), [main.py](/C:/Users/2016tu/Desktop/Projects/Naukri/main.py:64). | Use durable state storage or a deliberate, versioned artifact handoff; pass CLI flags from dispatch inputs; add a CI assertion that a requested dry run performs no live portal action. | Medium |
| **HIGH** | **Production bootstrapping seeds pre-existing application records.** `init_db()` loads `seed.sql` whenever `jobs` is empty, and the seed contains application/job records already marked `APPLIED_CONFIRMED`. This can make phase validation pass without proving the current run discovered or verified anything. Evidence: [connection.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/database/connection.py:55), [seed.sql](/C:/Users/2016tu/Desktop/Projects/Naukri/src/database/seed.sql:180), [phase_validator.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/cli/phase_validator.py:104). | Remove production seeding. Keep fixtures under tests only, and make the phase gate evaluate the current run’s records and evidence timestamps. | Medium |
| **HIGH** | **Resume artifacts can collide and audit linkage is unreliable.** Output names contain company, truncated role, and date—but not job ID—despite the intended architecture requiring it. Two matching listings with the same company/title on one day overwrite the same DOCX/PDF. Also, the browser uploads DOCX even though the intended flow specifies the tailored PDF. Evidence: [resume_agent.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/resume_agent.py:210), [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:533), [architecture.md](/C:/Users/2016tu/Desktop/Projects/Naukri/architecture.md:138). | Include immutable job ID/version ID in filenames; record hashes for both formats; upload the configured/validated format and verify portal acceptance. | Medium |
| **HIGH** | **Test coverage is mostly mocked and CI runs only unit tests.** There are 53 test functions, not the 66 claimed in the architecture. Browser, authentication, selectors, upload, form safety, cache recovery, and real workflow behavior are not exercised in CI. The lone integration test patches discovery and runs offline. Evidence: [career_agent_daily.yml](/C:/Users/2016tu/Desktop/Projects/Naukri/.github/workflows/career_agent_daily.yml:67), [test_orchestration_dry_run.py](/C:/Users/2016tu/Desktop/Projects/Naukri/tests/integration/test_orchestration_dry_run.py:117). | Add contract tests using captured sanitized Naukri DOM fixtures, deterministic Playwright tests against a local mock site, migration tests, and coverage/lint/type/security gates. Never use a live account in routine CI tests. | Large |
| **MEDIUM** | **SQLite does not implement the documented durability configuration.** No connection setup enables WAL or foreign-key enforcement; the seed explicitly sets `PRAGMA foreign_keys=OFF`. The schema also lacks uniqueness on `applications.job_id` and interview packs. Evidence: [architecture.md](/C:/Users/2016tu/Desktop/Projects/Naukri/architecture.md:221), [connection.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/database/connection.py:18), [models.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/database/models.py:154). | Enable WAL, `busy_timeout`, and foreign keys on every SQLite connection; introduce versioned migrations; add appropriate unique constraints and indexes. | Medium |
| **MEDIUM** | **Salary policy is split across configuration, code, documentation, and tests.** Configuration says ₹25 LPA, adapters hard-code 25, while parser/discovery comments and fixtures still use 20. The `MIN_SALARY_LPA` override is therefore not applied to live parsing. Evidence: [config.yaml](/C:/Users/2016tu/Desktop/Projects/Naukri/config/config.yaml:25), [salary_parser.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/utils/salary_parser.py:32), [discovery.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/discovery.py:105). | Make one configured threshold flow through all adapters and tests; add boundary tests for 20–25 LPA and ranges that cross the floor. | Small |
| **MEDIUM** | **Qualification can be based on incomplete/untrusted data.** Full JD fetch uses a separate unauthenticated HTTP client, suppresses failures, and does not detect barriers. The score itself awards non-zero baseline values and matches broad keywords from title/query, making false positives likely when JDs are unavailable. Evidence: [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:192), [browser_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/browser_adapter.py:127), [qualification.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/qualification.py:227). | Fetch details through the authenticated browser context, track JD completeness, require evidence for qualification, and calibrate scoring against labelled historical outcomes. | Medium |
| **MEDIUM** | **Reporting is not safely escaped or immutable per run.** Portal-derived company/title/URL data is inserted directly into HTML and Markdown. Daily report paths use only the date, so the afternoon run overwrites the morning report. Email delivery is not persisted, so a report can be sent without a durable run record. Evidence: [reporting.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/reporting.py:148), [reporting.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/reporting.py:25), [smtp_mailer.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/email_service/smtp_mailer.py:73). | HTML-escape all display text, validate/allowlist URLs, include run ID in report paths, and record email attempts/delivery state via an outbox. | Medium |
| **MEDIUM** | **Configured resilience controls are largely unused.** `retry_attempts`, backoff, request limits, and most safety switches exist in YAML but are not wired into browser/discovery execution. Fixed `sleep()` calls and brittle selectors will fail as Naukri changes. Evidence: [config.yaml](/C:/Users/2016tu/Desktop/Projects/Naukri/config/config.yaml:31), [playwright_adapter.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/naukri/playwright_adapter.py:423). | Use bounded retries only for idempotent reads, explicit Playwright waits, selector fallbacks with diagnostics, circuit breakers, and per-run request budgets. | Medium |
| **LOW** | **Blocklist matching is overly broad.** A substring match for `cts` can reject unrelated companies whose names contain those letters. Evidence: [discovery.py](/C:/Users/2016tu/Desktop/Projects/Naukri/src/agents/discovery.py:35). | Normalize legal company names and match word boundaries/approved aliases; retain an auditable blocked-company decision. | Small |
| **ENHANCEMENT** | **Observability is log-centric rather than operational.** Logging has useful redaction, but there are no structured run metrics, alert thresholds, trace bundles, release/version attribution, or dashboardable health checks. | Emit structured JSON events and per-stage metrics; retain sanitized DOM/screenshot bundles only for failed or disputed attempts; alert on barrier rate, zero-discovery runs, and confirmation decline. | Medium |

## What is already well designed

- Agent responsibilities are sensibly separated into discovery, qualification, resume generation, application, reporting, interview preparation, and repositories.
- The current-employer gate appears in discovery, qualification, and application, which is the right defense-in-depth pattern.
- Direct HTTP submission is deliberately disabled; browser submission is the only path.
- Candidate-answer resolution has a safe “unknown” outcome in the text-input path.
- Pydantic domain models, repositories, application-event records, evidence paths, and credential-redacting logging are good foundations worth preserving.
- External portals are surfaced for manual action rather than silently auto-submitted.

## Architecture-to-code divergences

| Intended architecture | Actual implementation |
|---|---|
| SQLite WAL mode with foreign keys | Neither is enabled in connection setup; seed disables foreign keys. |
| Green applied badge is the sole confirmation standard | Text and URL heuristics can mark applications confirmed. |
| Resume clones the immutable master and names outputs with job ID | Resume is rebuilt programmatically; artifact names omit job ID. |
| Configurable ₹25 LPA guardrail | Live adapters hard-code 25 while parser/docs/tests still retain 20-LPA behavior. |
| CI dry-run dispatch | Workflow exposes an input but invokes `main.py` without `--dry-run`. |
| Phase gate validates live current-run proof | Historical seed records can satisfy it. |
| Robust production state across automated runs | GitHub cache is the sole persistence mechanism and is keyed per run. |

## Quick wins


2. Require authentication success and a reloaded green badge before confirmation.
3. Remove production seed data and scope phase validation to the active run.
4. Pass `--dry-run` correctly in GitHub Actions.
5. Add job ID to resume filenames and switch/verify the intended upload format.
6. Wire the salary threshold from configuration into both adapters.
7. Enable SQLite foreign keys, WAL, and a unique application-per-job constraint.

## Prioritized roadmap

**P0 — Fix immediately**


- Enforce badge-based confirmation only.
- Add durable application intent + atomic uniqueness before Submit.
- Remove production confirmation seed data.
- Fail closed on missing authentication, MFA, CAPTCHA, payment, and unknown controls.

**P1 — High-value improvements**

- Redesign run transactions and failed-run recovery.
- Fix Actions state persistence and dry-run behavior.
- Build robust, truth-driven form-control handling and resume-upload verification.
- Add browser contract tests, migration tests, CI coverage, linting, type checking, and secret scanning.
- Make resume artifacts job-ID/version-specific.

**P2 — Nice-to-have enhancements**

- Enable WAL/foreign keys/busy timeouts and versioned migrations.
- Improve scoring calibration and JD completeness controls.
- Escape reports, persist email delivery attempts, and make reports immutable per run.
- Implement structured metrics, alerts, and sanitized diagnostic bundles.

**P3 — Future/optional ideas**

- Move durable state from SQLite/cache to managed Postgres if concurrent workers or multi-machine execution is needed.
- Add a human approval queue for high-impact applications.
- Add outcome feedback loops from recruiter responses to improve qualification and search ranking.