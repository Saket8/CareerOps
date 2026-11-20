# CareerOps Agent Directives & Standing Rules

## 1. Candidate Identity & Profile Invariants (Single Source of Truth)

All outgoing emails, cover letters, outreach drafts, ATS form submissions, and signatures MUST strictly use the following verified identity facts:

- **Full Name:** `Saket Saurav`
- **Email:** `sauravskt8@gmail.com`
  > **STRICT INVARIANT:** Never use any Cognizant email (`@cognizant.com`) or temporary email.
- **Phone:** `+91-7028481800`
- **LinkedIn Profile URL:** `https://www.linkedin.com/in/saket-saurav-31326b57/`
  > **CRITICAL INVARIANT:** The profile URL MUST include the exact identifier suffix `-31326b57/`.  
  > Never use truncated URLs (`saket-saurav`) or synthetic slugs (`saket-saurav-cloud`).
- **GitHub Profile URL:** `https://github.com/Saket8`
- **Current Employer / Role:** `Cognizant` (Principal Cloud Architect / Nov 2024 – Present)
- **Current Location / Hometown:** `Noida, India` (`Delhi NCR`)
- **Total Experience:** `12 Years`
- **Relevant Cloud / OCI / Security Architecture:** `6.5 Years`
- **Official Notice Period:** `90 Days` (Official / Negotiable)

---

## 2. Inviolable Operational Rules

1. **Git Policy:**
   - Commit and push to GitHub only when explicitly authorized or requested by the user. Ensure no credentials, temporary session artifacts, or sqlite databases are ever staged.

2. **Zero False Applies Invariant (Verification Policy):**
   - An application is **ONLY** marked as `APPLIED_CONFIRMED` when the canonical job listing page is reloaded and confirms the official green `Applied` badge (`LEVEL_2_BADGE_RELOAD`).
   - If the job listing still shows an active `Apply` button after reload, it is strictly non-confirmed (`APPLICATION_FAILED` or `SUBMISSION_UNVERIFIED`). Never mark it confirmed based on clicks or intermediate drawer messages.

3. **LinkedIn Pipeline Status:**
   - LinkedIn applications remain disabled (`linkedin.enabled: false`). Never discover or attempt automated applications on LinkedIn until explicitly requested by the user. Focus exclusively on Naukri direct submissions.

4. **External Email Dispatch:**
   - Always verify candidate facts, contact links (especially LinkedIn profile URL), and thread references before transmitting emails to recruiters or external hiring managers.

5. **Mailbox Retention Invariant:**
   - At any given time, there must NEVER be more than 3 CareerOps system report emails retained in `INBOX` and `[Gmail]/Sent Mail` (retaining only the latest 3 days).
   - Older system reports are automatically purged to `[Gmail]/Bin` and permanently expunged from Trash. All recruiter correspondence, personal emails, and external communications are strictly protected and never touched.
