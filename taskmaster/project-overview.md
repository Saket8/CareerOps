# Project Overview: Autonomous Naukri Career & Career-Intelligence Agent

## 1. Scope & Objective
Build a production-quality, long-running personal career automation and intelligence system that:
- Periodically searches Naukri for high-tier Cloud & AI architecture roles.
- Strictly filters on salary (Disclosed $\ge$ ₹30 LPA or Undisclosed; reject Disclosed $< 30$ LPA).
- Scores jobs against verified candidate facts extracted from [`Saket_Saurav_OCI.docx`](file:///c:/Users/2016tu/Desktop/Projects/Naukri/Saket_Saurav_OCI.docx).
- Automatically tailors truthful, ATS-optimized resumes (DOCX & PDF).
- Autonomously applies to qualifying opportunities (match $\ge$ 75%) without manual approval friction.
- Safely halts at anti-bot/CAPTCHA/MFA barriers without evasion.
- Generates 3-level interview preparation packs (Knowledge, Architecture, Principal Architect) for top matches.
- Analyzes actual job market signals (skill trends, emerging tech, salary distributions).
- Delivers daily & weekly HTML intelligence reports via email.
- Runs autonomously Mon–Fri at 09:00 IST via GitHub Actions.

## 2. Key Constraints & Non-Negotiables
1. **Zero Hallucination / Zero Fabrication**: Candidate truth layer (`candidate/candidate_facts.yaml`) is the supreme boundary. Never fabricate experience, titles, skills, or certifications.
2. **Master Resume Immutability**: [`Saket_Saurav_OCI.docx`](file:///c:/Users/2016tu/Desktop/Projects/Naukri/Saket_Saurav_OCI.docx) is read-only and preserved in `resumes/master/`.
3. **Hard Salary Filter**: Immediate rejection of any disclosed minimum salary under ₹30 LPA (e.g. ₹25–35 LPA rejected). Undisclosed salary is accepted.
4. **Safety & Compliance**: No CAPTCHA bypassing, bot cloaking, or credential sharing. Transition blocked applications to `BLOCKED` status.
5. **Dry Run Safety**: Default `DRY_RUN=true` to test discovery, scoring, resume generation, and reporting without posting live applications.
6. **Idempotency**: Prevent duplicate applications across runs using Naukri Job ID, canonical URL, and company/title hashes.

## 3. Measurable Success Criteria
- [ ] Candidate facts accurately parsed and validated against master resume.
- [ ] Salary parsing engine handles disclosed and undisclosed ranges with 100% precision against edge cases.
- [ ] Multi-dimensional scoring transparently scores Cloud, GenAI, OCI, Multi-cloud, K8s, and Security alignment.
- [ ] ATS resume engine generates valid, non-fabricated DOCX and PDF documents.
- [ ] Database abstraction (SQLite) tracks jobs, scores, evidence, applications, resumes, and runs.
- [ ] Daily and weekly HTML email reports format cleanly.
- [ ] Full automated test suite passes with high coverage.
- [ ] End-to-end dry run executes seamlessly.
