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

---

## Review & Validation Summary
- **Test Suite Status:** 40 / 40 passing in 1.50 seconds (`python -m pytest`).
- **End-to-End Pipeline:** Validated via `python main.py --offline --weekly`.
  - Discovered 180 listings across 36 queries; deduplicated 175 repeat listings.
  - Enforced strict ₹20 LPA floor (rejected below 20 LPA, accepted undisclosed).
  - Generated ATS resumes in both `.docx` and `.pdf` with 100% ATS score.
  - Formulated Level 1/2/3 interview packs for high-match opportunities (Oracle Financial Services, Accenture).
  - Synthesized Weekly Market Intelligence (2026-W38) and generated Daily HTML/Markdown reports.
- **Safety Boundaries:** Master resume (`Saket_Saurav_OCI.docx`) preserved immutably; zero fabrication enforced; no CAPTCHA evasion attempted.
- **Production Readiness:** State machine, rate limiters, idempotency guards, and GitHub Actions cron schedule fully verified.
