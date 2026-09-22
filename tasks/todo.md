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

---

## Review & Validation Summary
- **Test Suite Status:** 57 / 57 passing in 1.20 seconds (`python -m pytest`).
- **Phase Gate Status:** `APPLICATION AUTOMATION PHASE: PASSED` (`python main.py --validate-phase`).
  - Total Eligible Jobs in DB: 52
  - Applications Attempted: 11
  - APPLIED_CONFIRMED: 9 (including real live Maveric OCI Architect submission with Level 3 green 'Applied' badge verification)
- **Live Submission & Proof:** Application submitted live under `sauravskt8@gmail.com`. Reloading the canonical URL loads the official green **"Applied"** badge (`.already-applied`).
- **Email Report:** Sent to `sauravskt8@gmail.com` with direct verification link: `Verify on Naukri (Applied) ->`.
- **Employer Safety Block:** Cognizant / CTS block enforced across discovery, qualification, and application layers with regression test verification.



