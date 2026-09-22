# Project Roadmap: Autonomous Naukri Career Agent

## Phase Breakdown

### Phase 1: Foundation & Candidate Truth Layer
- Directory tree setup & Git initialization.
- Source resume preservation & verification (`resumes/master/`).
- Parsing master resume into `candidate/candidate_facts.yaml`.
- Core configuration (`config/config.yaml`).
- Database abstraction & SQLAlchemy models (SQLite backend).
- Logging with credential sanitization.
- Unit tests for models, config, and candidate truth parser.

### Phase 2: Discovery & Salary Eligibility Engine
- Salary parsing & strict filter implementation ($\ge$ ₹20 LPA or undisclosed).
- Search query runner (30+ targeted queries).
- Deduplication and state hashing.
- Naukri client interface and browser adapter scaffold.
- Unit tests for salary parser and discovery deduplication.

### Phase 3: Qualification & Evidence Extraction Engine
- Multi-dimensional scoring (Cloud, OCI, GenAI, Agentic AI, Multi-cloud, K8s, Security, Architecture weight).
- JD evidence extraction (Observed, Inferred, Generated).
- Candidate gap analysis.
- Unit tests for scoring algorithms.

### Phase 4: ATS Resume Engine & Validator
- Template-driven ATS resume generator (DOCX & PDF).
- Truthful keyword tailoring from JD requirements.
- ATS compliance validator (extractability, headers, zero-fabrication invariant).
- Version tracking in database.
- Unit tests for resume generation and ATS validator.

### Phase 5: Application Engine, Safety Boundaries & Idempotency
- Application state machine with full lifecycle transitions.
- Standard application question answering engine (facts-grounded).
- Safety guards (CAPTCHA, MFA, payment, external redirect handling).
- Idempotency layer (preventing duplicate submissions).
- DRY_RUN mode implementation.
- Daily application rate limiter (max 10/day).
- Integration tests in dry-run mode.

### Phase 6: Interview Intelligence Agent & Simulator
- JD-specific interview preparation pack generator (`interviews/<company>/<role>/`).
- 3-level question generation: Knowledge, Architecture, Principal Architect.
- 7-day preparation plan generator.
- Interactive terminal interview simulator script.

### Phase 7: Market Signal Engine & Weekly Career Intelligence
- Market data aggregation across all collected JDs.
- Trend classification ($\uparrow$ Increasing, $\downarrow$ Decreasing, $\rightarrow$ Stable, NEW, DISAPPEARING).
- Candidate positioning recommendations and new search query discovery.

### Phase 8: Daily & Weekly Reporting + Email Dispatcher
- Responsive daily HTML & Markdown report builder.
- Friday weekly career intelligence report builder.
- SMTP email dispatcher with retry handling.
- Artifact persistence in `reports/`.

### Phase 9: GitHub Actions Scheduling & CI/CD
- GitHub Actions workflow (`.github/workflows/career_agent_daily.yml`).
- Mon–Fri 09:00 IST schedule with concurrency control.
- Secrets mapping and artifact storage.
- Comprehensive end-to-end dry run verification.

### Phase 10: Automated External ATS Application Engine (PARKED / BACKLOG)
- Detailed specification in `tasks/TASK-001-external-ats-apply.md`.
- External ATS classification (Greenhouse, Lever, Ashby, SmartRecruiters vs. Workday, Taleo).
- Tier 1 public form auto-submission via Playwright with tailored PDF upload and candidate truth answering.
- Graceful fallback to `EXTERNAL_APPLICATION_REQUIRED` with 1-click apply links when CAPTCHA or custom unresolvable questions are encountered.

