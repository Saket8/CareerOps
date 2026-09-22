# Lessons & Patterns Registry

## Operational Principles
1. **Candidate Truth Invariant**: Never allow any module to invent, extrapolate, or falsify experience, job titles, or skills.
2. **Salary Eligibility Precision**: Disclosed minimum salary must be $\ge$ 20 LPA. Any range with a lower minimum (e.g. 15-25 LPA) must be rejected immediately without considering the upper bound.
3. **Safe Automation**: Never attempt to bypass CAPTCHA, MFA, or rate limits. Halting and logging `BLOCKED` preserves account integrity.
4. **Idempotency**: Every job processing step must be idempotent and recoverable from SQLite state.

---

## Log of Lessons Learned
- **Target Role Focus**: Prioritize Oracle Cloud Administrator / Architect and LLMOps / AI Architect roles specifically across search and qualification.
- **Salary Floor Adjustment**: Minimum compensation floor updated from ₹20 LPA to ₹25 LPA (with no upper ceiling; undisclosed allowed).
- **Application Transparency**: Explicitly distinguish between verification/offline test runs and live employer submissions in reports so the user has zero ambiguity about applied roles.
- **Recruiter Engagement Timing (2x Daily Schedule)**: Running twice daily at 09:00 IST (03:30 UTC - morning Resdex login & overnight job postings) and 14:00 IST (08:30 UTC - post-lunch candidate screening) ensures maximum visibility and top-of-inbox placement for recruiter screening batches.
- **Current Employer Safety Invariant**: Candidates must NEVER apply to or be visible to their current employer (Cognizant/CTS). Enforce hard blocklists in config, discovery, qualification, and application engines, and ensure current employer records are immediately blocked from all pipeline activity.
- **Production Database & Reporting Cleanliness (Zero Mock Pollution)**: Never allow offline test fixtures, unit test records, or mock application IDs to be written to or remain in the production SQLite database (`naukri_career_agent.sqlite`). Production database and reports must ONLY contain real live applications submitted through authenticated browser automation that exist in the user's Naukri account history (`https://www.naukri.com/myapply/historypage`). Test suites must ALWAYS use an in-memory database (`sqlite:///:memory:`) or isolated test database, ensuring zero mock pollution.
- **Precise DOM Matching & Live Account History Verification**: Never use loose substring matches (e.g. `span:has-text('Applied')`) because Naukri pages contain substrings like "Early Applicant", "Applicants: 50+", or "Applications viewed". Instead, strictly verify specific CSS classes (`.already-applied`, `span.already-applied`) and exact text matches. The ultimate ground truth is the live account history page (`https://www.naukri.com/myapply/historypage`); an application is only deemed successfully submitted if it increments the user's live Naukri application counter and displays on the history timeline.
- **Pan India Filter & Location Boundary Freedom**: Restricting job discovery to a single city or rigid set of metro locations artificially throttles opportunity discovery in senior architecture domains (OCI Architect, GenAI/Agentic AI Lead). Removing location restrictions and adopting Pan India / Remote / Hybrid defaults expands the discovery pool to high-yield national opportunities (e.g. TCS Pan India openings, multi-hub enterprises, remote architectures). Candidates open to national mobility should have screening questions automatically answered as Pan India / Relocation: Yes.
- **Executive Resume Depth & Non-Truncating PDF Generation**: Senior profiles (10–15+ years) cannot use simplified single-paragraph summaries or flattened bullet lists. They require an executive summary articulating enterprise scale and leadership, domain-categorized competencies, and bold lead-in bullet points with concrete metrics (~60% deployment reduction, ~40% incident reduction, ~50% DBA reduction). PDF generation must NEVER use character-slicing or bullet-capping; headless Chromium print rendering guarantees 100% text fidelity, exact pagination, and 100% ATS score.
- **Database & Storage Retention Invariant**: Continuous autonomous execution generates ephemeral data (unqualified jobs, debug inspect screenshots, log files, unapplied draft resumes). Retention rules must safely prune stale records and execute SQLite VACUUM to reclaim disk space while enforcing permanent immutability on confirmed applications (`APPLIED_CONFIRMED`), legal visual evidence (`*_already_applied.png`), and master resumes (`resumes/master/`).


