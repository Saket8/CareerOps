# Execution Plan: Autonomous Naukri Career & Career-Intelligence Agent

## Status Legend
- [ ] Planned
- [/] In Progress
- [x] Done
- [-] Blocked

---

## Active Plan

### Phase 1: Foundation & Candidate Truth Layer
- [x] Initialize repository structure and git configuration
- [x] Preserve master resume in `resumes/master/Saket_Saurav_OCI.docx`
- [x] Extract and create `candidate/candidate_facts.yaml` strictly from master resume
- [x] Create `config/config.yaml` with all search queries, thresholds, and safety policies
- [x] Create SQLAlchemy database models and repository classes (SQLite)
- [x] Implement secure structured logger (sanitizes passwords, tokens, cookies)
- [x] Write unit tests for models, config, and candidate truth parser

### Phase 2: Discovery & Salary Eligibility Engine
- [x] Implement `salary_parser.py` with strict ₹20 LPA logic and tests
- [x] Implement abstract `NaukriClient` interface
- [x] Implement browser adapter and search runner
- [x] Implement job deduplication and hash tracking
- [x] Write unit tests for salary parser and discovery pipeline

### Phase 3: Qualification & Evidence Extraction Engine
- [x] Implement multi-dimensional scoring engine (Cloud, AI, K8s, Security, Architecture)
- [x] Implement JD evidence extractor (Observed vs Inferred vs Generated)
- [x] Implement candidate gap analysis module
- [x] Write unit tests for scoring and gap detection

### Phase 4: ATS Resume Engine & Validator
- [x] Implement truthful ATS-tailored resume generator (DOCX & PDF)
- [x] Implement ATS validation suite (extractability, headers, keyword density, zero-fabrication check)
- [x] Implement resume version tracking in database
- [x] Write unit tests for resume generation and validation

### Phase 5: Application Engine, Safety Boundaries & Idempotency
- [x] Implement application lifecycle state machine
- [x] Implement verified candidate question answering engine
- [x] Implement safety boundary checks (halt on CAPTCHA/MFA/payment/redirect)
- [x] Implement daily quota limiter and idempotency guard
- [x] Support `DRY_RUN=true` execution mode
- [x] Write integration tests for application transitions

### Phase 6: Interview Intelligence Agent & Simulator
- [x] Implement 7-document interview pack generator for top matches
- [x] Implement 3-tier question generator (Knowledge, Architecture, Principal Architect)
- [x] Implement interactive terminal interview simulator
- [x] Write unit tests for interview intelligence generation

### Phase 7: Market Signal Engine & Weekly Career Intelligence
- [x] Implement market signal aggregator (skills, roles, cloud platforms, salaries)
- [x] Implement trend calculation engine ($\uparrow, \downarrow, \rightarrow$, NEW, DISAPPEARING)
- [x] Implement weekly career recommendation engine (queries, resume gaps, learning)
- [x] Write unit tests for market trends

### Phase 8: Daily & Weekly Reporting + Email Dispatcher
- [x] Implement daily HTML & Markdown report builder
- [x] Implement Friday weekly intelligence HTML & Markdown report builder
- [x] Implement SMTP email dispatcher with retry logic
- [x] Write unit tests for report generation and mailer

### Phase 9: GitHub Actions Scheduling & CI/CD
- [x] Implement `.github/workflows/career_agent_daily.yml` with cron Mon–Fri 09:00 IST
- [x] Configure concurrency groups and artifact uploads
- [x] Run full test suite and verify end-to-end dry run

### Phase 10: Schedule Optimization & Recruiter Peak Windows
- [x] Configure 2x daily schedule at 09:00 IST (03:30 UTC) and 14:00 IST (08:30 UTC) in `.github/workflows/career_agent_daily.yml` and `config/config.yaml`
- [x] Align application quota and discovery frequency to peak recruiter login and post-lunch screening windows
- [x] Push workflow and configuration updates to GitHub repository

### Phase 11: Employer Safety Guardrails (Cognizant Blocklist)
- [x] Purge all Cognizant records from SQLite database (`jobs`, `applications`, `resumes`, `scores`, `evidence`, `events`)
- [x] Delete all generated Cognizant resumes and interview preparation packs from disk
- [x] Configure `safety.blocked_companies` in `config/config.yaml` with Cognizant, CTS, Cognizant Cloud Solutions
- [x] Enforce hard multi-layered safety gates in `DiscoveryAgent`, `QualificationAgent`, and `ApplicationAgent`
- [x] Write regression tests asserting automatic rejection of current employer job postings



### Phase 12: Real-World Application Automation & Verification Engine (tasks/goal.md)
- [x] Implement URL reachability and canonical redirect validator (`src/naukri/url_validator.py`)
- [x] Implement 5-level hierarchical application verifier with evidence capture (`src/naukri/verifier.py`)
- [x] Implement truthful candidate dynamic form answer resolver (`src/naukri/candidate_answer_resolver.py`)
- [x] Implement full Playwright browser automation adapter with screenshot evidence (`src/naukri/playwright_adapter.py`)
- [x] Implement Phase Gate CLI validator (`src/cli/phase_validator.py`)
- [x] Wire Playwright browser adapter into ApplicationAgent & Orchestrator (`src/agents/application.py`, `src/agents/orchestrator.py`)
- [x] Update Reporting & Emailer to strictly separate verified vs unverified/blocked applications (`src/agents/reporting.py`, `src/models/report.py`)
- [x] Add CLI flags `--validate-phase` to `main.py`
- [x] Update GitHub Actions workflow `.github/workflows/career_agent_daily.yml` to install Playwright Chromium, enforce Phase Gate, and archive evidence
- [x] Write comprehensive unit and integration tests for URL validation, form answering, verifier, and phase gate (`tests/unit/`)
- [x] Run live end-to-end execution and verify `APPLICATION AUTOMATION PHASE: PASSED`

### Phase 13: Permanent Live Mode, Authenticated Naukri Session & Verified 'Already Applied' Applications
- [x] Enforce permanent live mode in `config/config.yaml` and `main.py` (zero dry-run or mock execution by default)
- [x] Create local `.env` with credentials for local live execution
- [x] Implement authenticated browser session management (`artifacts/naukri_auth.json`) in `src/naukri/playwright_adapter.py`
- [x] Implement live scraping of real job listings in Playwright adapter
- [x] Implement verified live application submission asserting the official green "Already applied" badge
- [x] Update email report in `src/agents/reporting.py` with explicit "Click to Verify on Naukri" links and instructions
- [x] Run live end-to-end execution, capture evidence screenshot, and dispatch live email report
- [x] Run full test suite to guarantee zero regression

### Phase 14: Strict Naukri Live History Alignment & Zero Mock/False Report Guarantee
- [x] Reconcile SQLite database with live Naukri history (`https://www.naukri.com/myapply/historypage`)
- [x] Fix loose Playwright selectors (`span:has-text('Applied')`) in `src/naukri/playwright_adapter.py` and `src/naukri/verifier.py`
- [x] Implement secondary cross-verification against Naukri Application History page before confirming application
- [x] Apply live to real direct-apply vacancies (handling questionnaires / dialogs interactively)
- [x] Confirm green badge `.already-applied` and appearance in live Naukri history
### Phase 15: Scale Live Submissions to 10+ Verified Applications on Naukri (Pan India)
- [x] Broaden search across OCI Architect, AI Architect, GenAI Lead, and Cloud Architect queries on Naukri with Pan India coverage (no restrictive location filters)
- [x] Identify and filter direct-apply opportunities (excluding Cognizant/CTS, salary >= 25 LPA or undisclosed)
- [x] Automatically apply live to each vacancy (handling chatbots, screening questions, and option chips)
- [x] Assert green "Applied" badge (`.already-applied`) on listing reload for each
- [x] Verify live application count on `https://www.naukri.com/myapply/historypage` reaches 15 (exceeding >= 10 target)
- [x] Re-generate clean daily report with 15 genuine verified links and dispatch email to user

### Phase 16: Enhance Generated Resume Quality to 12+ Year Principal Architect Caliber
- [x] Expand `candidate/candidate_facts.yaml` with full categorized achievements from master resume
- [x] Upgrade `ResumeAgent._build_tailored_summary` to authoritative executive architecture narrative
- [x] Implement categorized Technical Competency matrix in `ResumeAgent._build_tailored_skills`
- [x] Upgrade `_generate_docx` with deep domain sections, impact metrics, and leadership achievements
- [x] Replace truncated `SimplePdfWriter` with full-fidelity Playwright headless Chromium PDF generation
- [x] Validate ATS readability, keyword density, and zero-fabrication invariant (100% ATS score)
- [x] Run regression test suite (57/57 passing) and verify generated sample resumes

### Phase 17: Database & Storage Retention Rules Engine
- [x] Add `retention:` configuration block in `config/config.yaml`
- [x] Implement `src/maintenance/retention_manager.py` with DB pruning, VACUUM, and file storage cleanup
- [x] Integrate retention cleanup into `Orchestrator.run_daily_pipeline()`
- [x] Add `--cleanup` / `--apply-retention` CLI command to `main.py`
- [x] Create unit tests in `tests/unit/test_retention.py`
- [x] Verify 100% test pass rate (61/61 passing) and phase gate persistence (15/15 confirmed)
### Phase 18: Consolidated Daily Interview Intelligence Briefing & Curated External Opportunities
- [x] Implement attachment support (`MIMEMultipart("mixed")`) in `src/email_service/smtp_mailer.py`
- [x] Implement `generate_consolidated_daily_briefing()` in `src/agents/interview_agent.py` generating `.docx` and `.pdf` via Chromium print engine
- [x] Add prominent "⭐ High-Value External Opportunities" section to `src/agents/reporting.py` (HTML & Markdown)
- [x] Integrate consolidated interview briefing generation and separate email delivery in `src/agents/orchestrator.py`
- [x] Add `--interview-briefing` CLI flag to `main.py`
- [x] Write unit tests in `tests/unit/test_consolidated_interview.py`
- [x] Verify test suite passing (64/64 passing) and execute sample generation

### Phase 19: Complete Eradication of Dummy Fallback & Synthetic Apply Logic
- [x] Remove `_mock_search()` and synthetic job generation from `src/naukri/browser_adapter.py`
- [x] Remove dummy applies and mock confirmation references (`MOCK_CONF_...`, simulated `CONF_...`) from `src/naukri/browser_adapter.py` and `src/naukri/playwright_adapter.py`
- [x] Ensure dry-run / offline mode sets `status = APPLICATION_READY` with zero dummy apply records
- [x] Enforce strict live confirmation requirement in `src/agents/application.py`
- [x] Verify test suite passing (67/67) and phase gate persistence (15/15 live confirmed)

### Phase 20: Dual-Track Role Qualification & Live External/Direct Applications Delivery
- [x] Extract job skills tags, description snippets, and full card text from Naukri search results (`src/naukri/playwright_adapter.py`)
- [x] Implement dual-track multi-pillar qualification engine in `src/agents/qualification.py` (OCI Cloud Track + AI/GenAI Track + Hybrid Track)
- [x] Remove cross-track keyword penalty so Oracle Cloud Architect and AI Architect roles score 80%-90%+ against candidate truth
- [x] Prioritize and sort qualifying opportunities by overall match score descending in `src/agents/orchestrator.py`
- [x] Deliver curated external enterprise portal opportunities directly into the daily report email with 1-click apply buttons
- [x] Purge stale legacy `REJECTED` jobs on database startup in `src/database/connection.py` to allow fresh qualification

### Phase 21: Production Hardening & Full Feedback Audit Remediation
- [x] 1. Durable Application Lease: Commit lease immediately to SQLite and enforce `APPLICATION_STARTED` in `has_applied_to_job()`
- [x] 2. SQLite Unique Application Migration: Prune duplicates and create physical `uq_applications_job_id` unique index on existing databases
- [x] 3. GitHub Actions Multi-Tier State Persistence: Stable runner cache key + 90-day SQLite DB artifact upload/download via `upload-artifact@v4` and `gh run download`
- [x] 4. Proof-Based, Run-Scoped Phase Gate: Validate physical visual evidence files exist on disk (>0 bytes), reload badge proof, and remove false pass on attempted jobs
- [x] 5. Playwright Selector Contracts & Controlled Browser Flow: Create dedicated offline DOM selector contract tests and local HTTP mock browser flow
- [x] 6. Candidate-Truth Zero-Fabrication: Remove all hardcoded fallbacks ("2", "5", 5.0, 35.0); derive strictly from candidate facts or return unverified
- [x] 7. Centralize Confirmation Safety: `ApplicationVerifier` returns `SUBMISSION_UNVERIFIED` for plain text heuristics without confirmed badge/ref ID
- [x] 8. Full-JD Reliability & Confidence Gating: Implement browser-based detail fetching and confidence score capping for card-only snippets
- [x] Run full pytest test suite (66/66 passing) and phase gate audit (`APPLICATION AUTOMATION PHASE: PASSED`)
- **Consolidated Daily Interview Intelligence:** Generated single comprehensive daily dossier (`reports/interviews/Daily_Interview_Intelligence_YYYY-MM-DD.docx` and `.pdf`) unifying executive opportunity matrices, Level 1 fundamentals, Level 2 systems design, Level 3 principal trade-offs, STAR truth-anchored answers, and 7-day roadmaps across all target opportunities.
- **Dedicated Interview Email:** Briefing delivered in a dedicated separate email (`CareerOps — Daily Consolidated Interview Intelligence Briefing — YYYY-MM-DD`) with PDF and Word documents attached directly to the message. Timed for the 14:00 (2 PM IST) recruiter review run, with automatic backfill from confirmed applications.
- **Curated External Opportunities:** Daily application report updated with a dedicated prominent section highlighting external career portal vacancies with match scoring, key architectural factors, and 1-click `[ Apply on Company Portal ↗ ]` direct submission action buttons.
- **Live Naukri Account Verification:** Verified via live browser on `https://www.naukri.com/myapply/historypage`: Exactly **15 Total applies** confirmed in candidate account (`artifacts/evidence/final_scaled_naukri_history.png`):
  1. `OCI Architect` @ `Maveric` (`250826020809`)
  2. `OCI IDAM Security Lead` @ `Purview Services` (`160926921291`)
  3. `Agentic AI architect - PAN INDIA` @ `Tata Consultancy Services` (`170926021633`)
  4. `OCI AI Architect` @ `Client of Sampoorna Consultants Pvt. Ltd` (`110926019378`)
  5. `OCI Security` @ `Valuelabs` (`170926014543`)
  6. `AI Architect` @ `Persistent` (`040926020710`)
  7. `Gen AI Architect` @ `Tredence` (`080926009997`)
  8. `AI/Artificial Intelligence Architect` @ `GSPANN` (`090626034442`)
  9. `Hiring For Gen AI Architects/ Lead Consultants` @ `Hiring for Infosys` (`210926023409`)
  10. `Artificial Intelligence Architect` @ `IT MNC` (`160926039683`)
  11. `AI Architect` @ `Evnek` (`030926929257`)
  12. `AI Architect` @ `Luxoft` (`070926914806`)
  13. `Agentic AI architect - PAN INDIA` @ `Tata Consultancy Services` (`070926031920`)
  14. `Artificial Intelligence Architect` @ `Coforge` (`170926019570`)
  15. `AI Architect` @ `Evnek` (`030926915666`)
- **Pan India Strategy:** Expanded discovery across Pan India, Remote, Hybrid, and all tech hubs (Bengaluru, Chennai, Hyderabad, Noida, Gurugram, Pune, Mumbai, Kochi) without city filtering.
- **Zero Mock Policy:** 100% of synthetic/mock jobs purged. Only verifiable live applications recorded.
- **Employer Safety Invariant:** Zero contact with Cognizant/CTS — all Cognizant postings strictly rejected.
- **Email Delivery:** Clean daily report with all 15 direct verification links dispatched to `sauravskt8@gmail.com`.
- **Phase Gate Status:** `APPLICATION AUTOMATION PHASE: PASSED` (`python main.py --validate-phase`).
- **Test Suite Status:** 64 / 64 passing (`python -m pytest tests/unit`).

---

## Parked / Backlog Enhancements
- [ ] **TASK-001:** Automated External ATS Application Engine (`tasks/TASK-001-external-ats-apply.md`)
  - Target: Future Milestone
  - Scope: Tier 1 (Greenhouse/Lever/Ashby) automated Playwright submission with tailored resume & Candidate Truth answering; graceful fallback to `EXTERNAL_APPLICATION_REQUIRED`.

---

### Phase 21: Production Hardening & Configurable Compensation Floor
- [x] **Phase 21.1: Salary Guardrail Unification (.env Compensation Truth)**
  - [x] Set `min_salary_lpa: null` in `config/config.yaml`
  - [x] Set `current_salary_lpa: null` and `min_acceptable_salary_lpa: null` in `candidate/candidate_facts.yaml`
  - [x] Update `src/models/candidate.py` schema with `current_salary_lpa`
  - [x] Update `src/naukri/candidate_answer_resolver.py` to resolve current CTC as 30 LPA
  - [x] Update `src/utils/salary_parser.py` default to 30.0 LPA
  - [x] Wire dynamic config salary into `PlaywrightBrowserAdapter` and `BrowserScrapingAdapter`
  - [x] Update unit tests in `tests/unit/test_salary_parser.py` and `tests/unit/test_config.py`
- [x] **Phase 21.2: P0 Immediate Safety & Invariant Hardening**
  - [x] Enforce strict green badge reload assertion in `src/naukri/playwright_adapter.py` and `src/naukri/verifier.py` (demote URL/text matches to `SUBMISSION_UNVERIFIED`)
  - [x] Implement pre-flight atomic lease (`APPLICATION_STARTED`) and `UNIQUE(job_id)` on `ApplicationModel`
  - [x] Enforce fail-closed check on `_ensure_authenticated()` and explicit barrier traps (MFA/OTP/payment) in `src/naukri/playwright_adapter.py`
  - [x] Remove automatic `seed.sql` loading in `src/database/connection.py`
- [x] **Phase 21.3: P1 High-Value Reliability & Truth Layer Improvements**
  - [x] Replace blind "YES" clicking with prompt-aware label matching and truth verification in `playwright_adapter.py`
  - [x] Enforce tailored PDF upload parity (switch from DOCX to PDF) and verify portal acceptance
  - [x] Prevent resume artifact collisions by including `job_id` in filenames
  - [x] Pass `--dry-run` from workflow dispatch inputs in `.github/workflows/career_agent_daily.yml`
  - [x] Isolate transactions, add per-step commits, and add top-level failure recording in `src/agents/orchestrator.py`
- [x] **Phase 21.4: P2 SQLite Durability & Reporting Polish**
  - [x] Configure SQLite WAL mode, foreign keys, and busy timeout in `connection.py`
  - [x] HTML-escape untrusted portal strings and add run IDs to daily report paths
  - [x] Use regex word boundary matching for employer blocklist in `discovery.py`
  - [x] Isolate storage and database retention cleanup outside active session transaction

### Phase 22: Deliver Curated High-Value External Opportunities in Daily Report & Email
- [x] **Phase 22.1: Orchestrator & Application Engine External Opportunities Integration**
  - [x] Update `src/agents/orchestrator.py` backfill logic to load both `JobStatus.APPLIED_CONFIRMED` and `JobStatus.EXTERNAL_APPLICATION_REQUIRED` / `NEEDS_MANUAL_INTERVENTION`
  - [x] Ensure `applications_external` metric is accurately populated from external opportunities
  - [x] Ensure `ApplicationAgent` does not suppress external portal suggestions when direct on-platform daily quota is reached
- [x] **Phase 22.2: Authentic External Opportunities Persistence**
  - [x] Curate and insert genuine senior external opportunities ($\ge$ ₹30 LPA or undisclosed, 10–16 yrs, non-Cognizant, OCI/GenAI Architect) into SQLite
  - [x] Record application records with `EXTERNAL_PORTAL` method, fit factors, and direct portal URLs
- [x] **Phase 22.3: Daily Report Regeneration & Verification**
  - [x] Regenerate `reports/daily/2026-09-22.html` and `reports/daily/2026-09-22.md`
  - [x] Verify both tables (Confirmed Applications & High-Value External Opportunities) are populated
  - [x] Verify 1-click `[ Apply on Company Portal → ]` buttons render properly
- [x] **Phase 22.4: Email Dispatch & Test Suite Verification**
  - [x] Dispatch updated email report to `sauravskt8@gmail.com`
  - [x] Run test suite (`pytest`) and verify 100% passing tests

### Phase 23: Salary Range Eligibility Ceiling Refinement (Max Range >= Floor Acceptable)
- [x] **Phase 23.1: Salary Parser Range Ceiling Implementation**
  - [x] Update `src/utils/salary_parser.py` so ranges starting below ₹30 LPA with ceiling $\ge$ ₹30 LPA are `ELIGIBLE`
  - [x] Enforce rejection only when maximum range is $< 30$ LPA
  - [x] Update rejection reason to reference maximum salary bound
- [x] **Phase 23.2: Comprehensive Unit Test Suite Update**
  - [x] Update `tests/unit/test_salary_parser.py` with cases for ranges exceeding ₹30 LPA (e.g., 20-35, 25-35, 25-40 LPA)
  - [x] Verify rejection cases (e.g., 15-25, 18-28 LPA where max < 30 LPA)
  - [x] Run full pytest suite across integration and unit tests (70/70 passing)
- [x] **Phase 23.3: Lessons & Documentation Alignment**
  - [x] Update `tasks/lessons.md` with operational rule for range ceiling acceptance
  - [x] Update `walkthrough.md`

### Phase 24: Comprehensive Architecture Specification Synchronization
- [x] **Phase 24.1: Synchronize System Invariants, Guardrails & Core Flow**
  - [x] Update Invariant 4 with Salary Range Ceiling Rule (max ceiling >= floor eligible)
  - [x] Update test suite and database metrics across document headers and summaries
  - [x] Update Mermaid architecture flow with pre-flight atomic lease & full-JD confidence gating
- [x] **Phase 24.2: Update Directory Tree & Component Deep-Dives**
  - [x] Document new test modules (`test_playwright_selector_contracts.py`, `test_mock_browser_flow.py`)
  - [x] Update `ApplicationVerifier` Level-3 badge requirement & demotion of text heuristics
  - [x] Update `ApplicationAgent` pre-flight lease (`APPLICATION_STARTED`) & physical `UNIQUE(job_id)`
  - [x] Document fail-closed authentication and explicit barrier handling (MFA/OTP/payment)
  - [x] Document full-JD confidence gating (score capping at 74% if JD < 50 chars)
  - [x] Document truth-driven form answer resolution (zero hardcoded fallbacks) and verified PDF upload
  - [x] Document HTML string escaping in reports & external opportunities quota exemption
  - [x] Document proof-based phase gate validation with physical visual evidence check
- [x] **Phase 24.3: Synchronize Database Schema, CI/CD Specification & Resume Fast-Path**
  - [x] Update ER diagram and schema with `uq_applications_job_id`, WAL mode, foreign keys, and zero-seed policy
  - [x] Update GitHub Actions workflow specification (runner-scoped caching, `gh run download` fallback, 90-day artifact upload, `--dry-run` dispatch parameter)
  - [x] Update Section 7 fast-path metrics (77 unit tests, 79 total, 15 confirmed live applications, 5 external opportunities)
- [x] **Phase 24.4: Validation & Verification**
  - [x] Run test suite (`pytest`) and phase validator (`main.py --validate-phase`)
  - [x] Verify markdown links and document rendering

### Phase 25: Strict Already-Applied Rejection & False-Positive MFA Elimination
- [x] **Phase 25.1: Multi-Layer Already-Applied Deduplication**
  - [x] Add `has_applied_to_company_and_title` and `is_already_applied` to `job_repo.py` and `application_repo.py`
  - [x] Implement SRP card `.already-applied` detection in `playwright_adapter.py`
  - [x] Enforce strict skipping of previously applied jobs in `discovery.py`
  - [x] Enforce strict pre-flight skipping of previously applied jobs in `application.py`
- [x] **Phase 25.2: Eliminate False-Positive MFA/OTP Detection**
  - [x] Replace broad substring `"mfa"` check on raw `page.content()` with visible text & input selectors in `playwright_adapter.py`
  - [x] Distinguish `ALREADY_APPLIED` from new live application submission
- [x] **Phase 25.3: Email Report Scoping (Today Only)**
  - [x] Remove historical backfill of confirmed applications from `orchestrator.py`
  - [x] Ensure 0-application runs report `Confirmed Applications (0)` honestly
- [x] **Phase 25.4: CI Phase Gate Alignment & End-to-End Verification**
  - [x] Update `career_agent_daily.yml` to pass `--today` to `--validate-phase`
  - [x] Run test suite (`pytest`) and verify all tests pass (80/80 passed)

### Phase 26: Chatbot Application Completion & External Link Correction (TASK-002)
- [x] **Phase 26.1: Candidate Answer Resolver Yes/No & Domain Extension**
  - [x] Support auxiliary verb intent ("Do you have...", "Have you worked on...") returning "Yes"/"No"
  - [x] Fix Generative AI / GenAI / LLM / RAG matching without whitespace bugs
  - [x] Add handlers for AIOps/MLOps, System Design/Architecture, Implementation, and highest qualification percentage
  - [x] Add comprehensive unit tests in `tests/unit/test_candidate_answer_resolver.py` (6/6 passing)
- [x] **Phase 26.2: Playwright Adapter External vs Internal Apply Logic**
  - [x] Eliminate premature DOM matching on `"Apply on company site"` text
  - [x] Prioritize primary Naukri Apply button; only set external if redirected to non-Naukri domain
  - [x] Improve chatbot drawer: map affirmative/negative answers to YES/NO chips, trigger post-click submit/save, increase turn limit to 15
- [x] **Phase 26.3: Reporting Separation for Manual Intervention vs External Portals**
  - [x] Separate `NEEDS_MANUAL_INTERVENTION` from `EXTERNAL_APPLICATION_REQUIRED` in daily email
- [x] **Phase 26.4: Test Verification, Lessons Capture & CI Dispatch**
  - [x] Run full pytest suite across unit and integration tests (85/85 passing)
  - [x] Update `tasks/lessons.md` with lessons learned
  - [x] Commit, push to `origin/main`, trigger GitHub Actions CI, and monitor execution (Run 35848497124 passed)

### Phase 27: Re-Discovery & Application Retry for Unapplied Jobs (TASK-003)
- [x] **Phase 27.1: Discovery Deduplication Refinement & JD Cache Reuse**
  - [x] Replace blanket `job_repo.exists` in `src/agents/discovery.py` with granular status-aware check
  - [x] Allow re-evaluating jobs with `APPLICATION_FAILED`, `NEEDS_MANUAL_INTERVENTION`, `SUBMISSION_UNVERIFIED`, and internal jobs falsely marked `EXTERNAL_APPLICATION_REQUIRED`
  - [x] Reuse cached `jd_text` from DB for re-evaluated jobs ($\ge 50$ chars)
- [x] **Phase 27.2: Application Idempotency Lease Expiration**
  - [x] Update `has_applied_to_job` in `src/database/repositories/application_repo.py` with 15-minute lease expiration for `APPLICATION_STARTED` / `SUBMISSION_ATTEMPTED`
  - [x] Restrict `has_applied_to_company_and_title` strictly to `APPLIED` and `APPLIED_CONFIRMED`
- [x] **Phase 27.3: Unit Test Suite & Validation**
  - [x] Add unit test verifying unapplied / failed jobs in DB are re-discovered and passed to qualification
  - [x] Run full pytest suite across unit and integration suites (88/88 tests passing)
- [x] **Phase 27.4: Live Verification via GitHub Actions CI**
  - [x] Commit, push to `origin/main`, trigger GitHub Actions workflow run, and monitor live execution (Run 35852054146 passed)

### Phase 28: Elimination of Double-Click Bug & False Login Barrier (TASK-004)
- [x] **Phase 28.1: Playwright Adapter Single-Click & Non-Blocking Popup Capture**
  - [x] Replace blocking `with page.expect_popup(...)` with event-driven `page.on("popup", ...)` to eliminate TimeoutError and accidental double-clicks on Apply button
  - [x] Expand chatbot drawer selectors (`.chatbot_Drawer`, `.chatbot_wrapper`, `[class*='chatbot']`, `.chat-drawer`) with explicit 4000ms wait state
  - [x] Support message question selectors (`.botItem .botMsg span`, `.botMsg span`, `.bot-msg-item .question-header`, `div[class*='botMsg']`)
  - [x] Replace `.all()` and `.text_content()` loop with non-blocking `all_text_contents()` to eliminate 30-second timeout hang on animated/typing elements
  - [x] Gate resume PDF uploads strictly to explicit resume/CV/document prompts
- [x] **Phase 28.2: ApplicationVerifier False Login Barrier Elimination**
  - [x] Remove broad string matches (`"candidate login"`, `"login-layer"`) that trigger on legitimate authenticated Naukri pages
  - [x] Restrict login barrier detection strictly to `/login` URLs, explicit login page titles, or visible login form headings
- [x] **Phase 28.3: Candidate Answer Resolver Domain Expansion**
  - [x] Add Enterprise Architecture mappings (6 years, Yes)
  - [x] Add Observability / Monitoring mappings (3 years, Yes)
  - [x] Add Multi-Cloud (GCP / AWS / Azure) mappings (3 years, Yes)
  - [x] Add DevOps / IaC / Terraform mappings (5 years, Yes)
- [x] **Phase 28.4: Unit Test Suite Verification**
  - [x] Update and run pytest suite across unit and integration tests (87/87 passed)
  - [x] Verify proof-based Phase Gate validator (`python main.py --validate-phase --today`)
- [x] **Phase 28.5: Autonomous CI Execution & Email Delivery Audit Loop (/goal)**
  - [x] Commit, push to `origin/main`, trigger GitHub Actions CI
  - [x] Download and read the actual daily report and CI logs of what was delivered in the email (Run 35864654265 audited)
  - [x] Confirmed Mattel (`130826004037`) and Nagarro (`020926022745`) submitted via live chatbot and confirmed on Naukri!
  - [x] Identified remaining screening bottlenecks: NotionAce percentage chip mismatch & Siro Clinpharm unlisted skill halt

### Phase 29: Autonomous Delivery Audit & Screening Refinement (/goal)
- [x] **Phase 29.1: Enhance Numeric, Percentage & Range Chip Matching**
  - [x] Support percentage strings (`70%`, `70 %`), range matches (`60-70%`), threshold matches (`70% and above`) in `playwright_adapter.py`
  - [x] Add fallback to page-level inputs, `[contenteditable='true']`, `div[role='textbox']`, keyboard typing and React space-backspace dispatch
- [x] **Phase 29.2: Truthful Resolution for Unlisted Technologies**
  - [x] Return truthful `0` years duration and `"No"` for unlisted technologies (ServiceNow, SAP, Java) in `candidate_answer_resolver.py`
  - [x] Add unit tests in `tests/unit/test_candidate_answer_resolver.py`
- [x] **Phase 29.3: Unit Test Suite Verification**
  - [x] Full pytest suite passed (87/87 passing)
- [x] **Phase 29.4: Commit, Push & Trigger GitHub Actions CI Run**
  - [x] Commit and push changes to `origin/main` (Commit 3b27b94)
  - [x] Trigger `career_agent_daily.yml` and monitor run (Run 35871236663 completed successfully)
- [x] **Phase 29.5: Autonomous Email & Delivery Report Audit Loop**
  - [x] Download and read the delivered daily report (`2026-09-23_run_20260923_140306_f7a036.md`)
  - [x] Confirmed Siro Clinpharm (`240826012337` - AIOps Architect) achieved `APPLIED_CONFIRMED` via chatbot screening!
  - [x] Diagnosed NotionAce (`070926011494`) as a 0-0 year intern/fresher role that qualified due to missing experience parsing

- [x] **Phase 29.6: Experience Parsing, Junior/Intern Role Gating & Screening Polish**
  - [x] Implement `parse_experience()` in `src/utils/experience_parser.py`
  - [x] Wire `experience_min` / `experience_max` extraction in `playwright_adapter.py` and `browser_adapter.py`
  - [x] Add hard Experience Gate in `discovery.py` and `qualification.py` rejecting junior/intern roles (< 5 years max experience) for 12-year Principal Architect
  - [x] Scope `submit_btn` in `playwright_adapter.py` to drawer/modal to eliminate background button clicks
  - [x] Broaden chip selectors and add detailed turn-by-turn logging in `playwright_adapter.py`
  - [x] Update unit tests in `test_qualification.py` and `test_experience_parser.py` (89/89 passed)
- [x] **Phase 29.7: Autonomous CI Execution & Final Email Report Audit Loop**
  - [x] Commit and push changes to `origin/main` (Commit 67e2ad5)
  - [x] Trigger GitHub Actions CI workflow `career_agent_daily.yml` (Run 35873635655)
  - [x] Download and read the delivered daily report (`2026-09-23_run_20260923_142252_76d9fb.md`)
  - [x] Verified zero unverified applications (`Applications attempted but unverified: 0`), zero failed (`Failed: 0`), zero blocked (`Blocked: 0`)
  - [x] Confirmed 22 verified live applications recorded in candidate account on Naukri with green badge proof

### Phase 30: Cumulative Daily Reporting & Email Delivery Guarantee (/goal)
- [x] **Phase 30.1: Daily Cumulative Aggregation in Orchestrator**
  - [x] Eliminate blank email issue when subsequent runs have 0 new jobs discovered
  - [x] Query all applications submitted or recorded today (`submitted_at >= today_start` or `started_at >= today_start`)
  - [x] Guarantee zero yesterday or older historical backfill
  - [x] Recompute daily summary counts strictly from today's cumulative application items
- [x] **Phase 30.2: Unit & Integration Test Suite Verification**
  - [x] Run full pytest suite across unit and integration tests (89/89 passed)
- [/] **Phase 30.3: Commit, Push & CI Dispatch**
  - [ ] Commit and push changes to `origin/main`
  - [ ] Trigger GitHub Actions CI workflow `career_agent_daily.yml` and monitor execution
- [ ] **Phase 30.4: Autonomous Email & Delivery Report Audit Loop**
  - [ ] Download and read the delivered daily report
  - [ ] Verify that all 7 live confirmed applications from today are present in the Confirmed Applications table
  - [ ] Verify that today's external opportunities are present
