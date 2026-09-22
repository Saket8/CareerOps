# TASK-001: Automated External ATS Application Engine

> **Status:** PARKED / BACKLOG  
> **Created:** 2026-09-22  
> **Target Release:** Future Milestone (Post-Naukri Core Stabilization)  
> **Priority:** Low / Future Enhancement  

---

## 1. Objective

Enable the autonomous agent to automatically fill and submit candidate applications when a job posting redirects to third-party corporate Applicant Tracking Systems (ATS), while strictly adhering to the **Candidate Truth Layer**, **Current Employer Safety Gate**, and **Zero-Mock Policy**.

---

## 2. Scope & Technical Architecture

### 2.1. Tiered ATS Taxonomy
External listings will be classified into three operational tiers based on friction and feasibility:

1. **Tier 1: Frictionless Public ATS (High Feasibility, 85–95% Unattended)**
   - **Platforms:** Greenhouse (`boards.greenhouse.io`), Lever (`jobs.lever.co`), Ashby (`jobs.ashbyhq.com`), SmartRecruiters (`smartrecruiters.com`).
   - **Characteristics:** Single-page public web forms, no candidate login/account creation required, standardized DOM schemas.
   - **Scope:** Automated Playwright filling of core identity fields, document upload (tailored `.pdf` resume), deterministic screening questions via `CandidateAnswerResolver`.

2. **Tier 2: Enterprise Multi-Step ATS (Medium Feasibility, 40–60% Unattended)**
   - **Platforms:** Workday (`*.myworkdayjobs.com`), Oracle Cloud Recruiting / Taleo, SAP SuccessFactors, iCIMS.
   - **Characteristics:** Mandatory user registration, email verification, 5–8 step wizard forms, aggressive session timeouts.
   - **Scope:** Dedicated session handler with candidate credentials (`WORKDAY_GLOBAL_PASSWORD`) or pre-authenticated state.

3. **Tier 3: Bespoke Corporate Portals (Low Unattended Feasibility)**
   - **Platforms:** Proprietary enterprise portals (e.g. Infosys, TCS, Wipro, Accenture, Deloitte).
   - **Characteristics:** Complex multi-factor auth, Aadhaar/PAN checks, arbitrary bot mitigation.
   - **Scope:** Semi-automated Human-in-the-Loop (HITL) assistance; generate tailored resume and pre-populate answer packet for 1-click manual submission.

---

## 3. Inputs & Outputs

### Inputs
- Discovered job record with `application_method == "EXTERNAL_PORTAL"` and `external_application_url`.
- Candidate truth facts: `candidate/candidate_facts.yaml`.
- Tailored ATS resume: `resumes/generated/Saket_Saurav_<Company>_<JobID>.pdf`.
- Candidate authentication credentials for Tier 2 ATS (if configured via GitHub Secrets / environment).

### Outputs
- `ApplicationRecord` with:
  - `status = JobStatus.APPLIED_CONFIRMED` (if verified) or `JobStatus.EXTERNAL_APPLICATION_REQUIRED` (if blocked/unsupported).
  - `application_method = "EXTERNAL_ATS_AUTO"`.
  - `confirmation_reference = <Extracted Confirmation or Application ID>`.
  - `evidence_path = artifacts/evidence/<job_id>_external_confirmed.png`.
- Visual proof screenshot capturing the vendor thank-you / confirmation page.

---

## 4. Dependencies
- `src/naukri/candidate_answer_resolver.py` (Extended to handle common ATS screening prompts).
- `src/agents/resume_agent.py` (Providing verified headless-printed PDF resumes).
- `src/agents/qualification.py` (Re-verifying company safety and role match prior to external submission).
- Playwright Chromium browser runtime with stealth configurations.

---

## 5. Non-Negotiable Invariants & Guardrails
1. **Candidate Truth Invariant:** Zero guessing or LLM fabrication on screening questions. If a question cannot be resolved from `candidate_facts.yaml`, the agent must abort auto-apply and revert to `EXTERNAL_APPLICATION_REQUIRED`.
2. **Current Employer Safety Gate:** Immediate hard rejection if the redirected URL or landing page matches `Cognizant` or `CTS`.
3. **Proof Verification:** Only applications showing authentic vendor confirmation screens / application references can be marked `APPLIED_CONFIRMED`.
4. **Anti-CAPTCHA Gate:** Never attempt hacky CAPTCHA bypasses that jeopardize IP reputation. If Cloudflare Turnstile or reCAPTCHA is presented, gracefully fall back to `EXTERNAL_APPLICATION_REQUIRED`.

---

## 6. Validation Criteria (Definition of Done when Unparked)
- [ ] ATS Vendor detector accurately identifies Greenhouse, Lever, Ashby, and Workday from target URLs.
- [ ] End-to-end sandbox test on live Greenhouse job posting submits valid application with tailored resume.
- [ ] Captured screenshot in `artifacts/evidence/` shows authentic "Application Submitted" state.
- [ ] Database record created with `status = APPLIED_CONFIRMED` and verifiable external URL.
- [ ] Graceful fallback tested: when unknown question or CAPTCHA is present, job is flagged `EXTERNAL_APPLICATION_REQUIRED` with zero crash.
- [ ] Full unit test suite passes with $\ge 90\%$ branch coverage on external ATS adapters.

---

## 7. Risks & Rollback Considerations
- **Risk:** Vendor DOM changes breaking selectors.  
  *Mitigation:* Schema-agnostic fallback to semantic HTML attributes (`input[type='email']`, `input[autocomplete]`, label association).
- **Risk:** IP rate-limiting or bot blocking on third-party domains.  
  *Mitigation:* Random jitter (3–7s delay), realistic browser headers, and strict concurrency limits.
- **Rollback:** Feature flag `features.external_auto_apply: false` in `config/config.yaml` to instantly revert to current behavior (recording URL and presenting 1-click button in daily report).
