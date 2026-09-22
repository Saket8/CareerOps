# RE-RUN AND VALIDATE THE JOB APPLICATION PIPELINE END-TO-END

We are now at the **real application validation phase**.

Do NOT treat this run as a simulation, dummy run, mock application, or email-only test.

The objective of this phase is to prove that the system can actually discover eligible jobs, open the real job listing, complete the required application workflow, submit the application, and provide verifiable evidence that the application was successfully submitted.

## 1. PHASE PASS/FAIL CRITERIA

This phase is considered **PASSED only when real applications have actually been submitted successfully**.

A job should NOT be reported as:

* Applied
* Application successful
* Submitted

merely because:

* the job was discovered
* the job URL opened
* the resume was generated
* an application form was opened
* an email notification was generated
* the browser reached the final page
* a button was clicked

The system must verify that the application was actually submitted.

If this cannot be verified, the status must NOT be `APPLIED`.

Use states such as:

* DISCOVERED
* ELIGIBLE
* APPLICATION_STARTED
* FORM_COMPLETED
* SUBMISSION_ATTEMPTED
* APPLIED_CONFIRMED
* APPLICATION_FAILED
* APPLICATION_BLOCKED
* EXTERNAL_APPLICATION_REQUIRED
* NEEDS_MANUAL_INTERVENTION

Only:

`APPLIED_CONFIRMED`

counts as a successful application.

Until at least one real application has been successfully verified end-to-end, this phase must remain **FAILED / NOT PASSED**.

---

# 2. DO NOT SEND DUMMY EMAILS

The email report must reflect the actual application database.

Do NOT generate an email saying:

> Application submitted

unless the underlying application record contains verified submission evidence.

The email must be generated from actual application state.

For example:

```text
Job: Principal Cloud Architect – AI
Company: XYZ
URL: <actual job URL>

Application status:
APPLIED_CONFIRMED

Evidence:
- Application submission detected
- Confirmation page detected
- Timestamp recorded
- Resume uploaded
- Application reference captured where available
```

If submission could not be verified:

```text
Status:
APPLICATION_FAILED / APPLICATION_BLOCKED

Reason:
Unable to verify final submission.
```

Never represent this as `APPLIED`.

---

# 3. EVERY JOB LINK MUST BE VALIDATED

For every job included in the report:

1. Open the actual URL.
2. Verify the page belongs to the intended job.
3. Verify:

   * company
   * job title
   * location where available
   * job ID where available
4. Confirm the listing is still active.
5. Confirm the application workflow corresponds to that job.
6. Store the canonical URL.
7. Store the timestamp when validated.

Do not send stale, malformed, redirected-to-homepage, or unrelated URLs.

If the original search URL redirects to another valid job URL, store the final canonical URL as well as the original URL.

Example:

```text
source_url
canonical_job_url
application_url
external_application_url
```

These are separate fields.

---

# 4. REAL APPLICATION VERIFICATION

The application agent must distinguish between:

### A. Form opened

NOT applied.

### B. Form completed

NOT applied.

### C. Submit button clicked

NOT necessarily applied.

### D. Confirmation detected

Potentially applied.

### E. Confirmation independently verified

`APPLIED_CONFIRMED`

Look for evidence such as:

* confirmation message
* application submitted page
* application reference/ID
* Naukri applied state
* application history entry
* confirmation URL
* external ATS confirmation
* application-success UI

Capture evidence where practical.

For browser automation, save:

* final URL
* page title
* confirmation text
* timestamp
* screenshot where appropriate
* application reference
* browser/network evidence where appropriate

Do not claim success based only on a click.

---

# 5. Naukri DIRECT APPLICATION FLOW

Some Naukri jobs can be applied to directly inside Naukri.

The workflow may look like:

```text
Open job
   ↓
Click Apply
   ↓
Application questions
   ↓
Resume selection/upload
   ↓
Additional questions
   ↓
Review
   ↓
Submit
   ↓
Confirmation
```

The automation must support this complete flow.

Do not assume:

`Click Apply = Application Submitted`

Instead:

```text
JOB_OPENED
→ APPLY_CLICKED
→ QUESTIONS_DETECTED
→ QUESTIONS_ANSWERED
→ RESUME_SELECTED
→ REVIEW
→ SUBMIT
→ CONFIRMATION_DETECTED
→ APPLIED_CONFIRMED
```

---

# 6. PRE-APPLICATION QUESTIONS

Naukri may ask questions before the final application submission.

The application agent must dynamically inspect the page and identify:

* text fields
* dropdowns
* radio buttons
* checkboxes
* yes/no questions
* experience questions
* notice period
* salary
* location
* relocation
* work authorization
* certification questions
* skill questions
* employer questions
* years-of-experience questions

Do NOT assume a fixed form.

The browser agent must inspect the actual rendered form.

---

# 7. ANSWERING APPLICATION QUESTIONS

Create a structured candidate-answer profile.

Example:

```yaml
candidate_answers:

  notice_period:
    value: "<configured value>"
    source: candidate_profile

  current_location:
    value: "<configured value>"
    source: candidate_profile

  work_authorization:
    value: "<configured value>"
    source: candidate_profile

  willing_to_relocate:
    value: "<configured value>"
    source: candidate_profile
```

The application agent may automatically answer questions when the answer is explicitly known and verified.

It must NOT guess.

For example:

If the question is:

> How many years of production AWS MLOps experience do you have?

and the verified candidate profile does not contain this experience:

DO NOT invent an answer.

Mark:

```text
APPLICATION_BLOCKED
reason:
UNVERIFIED_CANDIDATE_INFORMATION
```

The system must never fabricate qualifications merely to complete an application.

---

# 8. HANDLING QUESTIONS THAT ARE NOT IN THE PROFILE

If a question is encountered that cannot be answered confidently from verified candidate information:

1. Stop submission for that application.
2. Preserve the application state.
3. Record the exact question.
4. Record the URL.
5. Record the job ID.
6. Record the point at which the workflow stopped.
7. Mark:

`NEEDS_MANUAL_INTERVENTION`

Do NOT submit an invented answer.

The system should still continue processing other eligible jobs.

---

# 9. EXTERNAL CAREER PORTALS

Some Naukri listings do NOT complete the application inside Naukri.

They may redirect to:

* company career portal
* Workday
* Greenhouse
* Lever
* Oracle Recruiting
* SAP SuccessFactors
* Taleo
* other ATS platforms

The application architecture must explicitly support this.

Do NOT treat:

> "Apply on company website"

as a successful application.

Instead:

```text
Naukri job
   ↓
External application detected
   ↓
Open external application URL
   ↓
Identify ATS/platform
   ↓
Start external application workflow
   ↓
Complete supported fields
   ↓
Upload tailored resume
   ↓
Answer supported questions
   ↓
Submit
   ↓
Verify confirmation
   ↓
APPLIED_CONFIRMED
```

---

# 10. EXTERNAL APPLICATION STATE

Add:

```text
application_method

NAUKRI_DIRECT
EXTERNAL_PORTAL
MANUAL_REQUIRED
```

And:

```text
external_portal
external_application_url
external_application_id
external_confirmation
```

The job report should clearly indicate where the application actually occurred.

Example:

```text
Role:
Principal Cloud Architect

Source:
Naukri

Application method:
External Portal

ATS:
Workday

Naukri status:
Redirected

External status:
APPLIED_CONFIRMED
```

---

# 11. EXTERNAL PORTAL AUTHENTICATION

Do NOT assume the user is already authenticated to every external ATS.

The system should detect:

* login page
* account creation requirement
* OTP
* MFA
* CAPTCHA
* authentication wall

If authentication is required and cannot be completed using configured credentials/session:

mark:

`NEEDS_MANUAL_INTERVENTION`

Do not fabricate credentials.

Do not bypass authentication.

Do not attempt to bypass CAPTCHA/MFA.

---

# 12. EXTERNAL PORTAL ACCOUNT CREATION

Do NOT automatically create accounts on external career sites unless this behavior is explicitly configured and supported.

If account creation is required:

```text
EXTERNAL_ACCOUNT_REQUIRED
```

and record:

* company
* portal
* URL
* job
* reason

The application should not be falsely marked as submitted.

---

# 13. BROWSER AUTOMATION ARCHITECTURE

The browser automation must use Playwright or the existing supported browser environment.

Do not tightly couple application logic to Playwright.

Use an abstraction such as:

```text
BrowserAdapter
    ↓
PlaywrightBrowserAdapter
```

Application logic should call operations such as:

```text
open_job()
click_apply()
detect_application_form()
fill_question()
upload_resume()
submit_application()
verify_confirmation()
```

The Playwright implementation performs the actual browser actions.

This allows the same application logic to run:

* locally
* in development
* in CI
* in GitHub Actions
* eventually in another browser execution environment

---

# 14. CRITICAL QUESTION: HOW WILL PLAYWRIGHT WORK FROM GITHUB ACTIONS?

Do NOT assume that a local browser session will magically exist on a GitHub Actions runner.

GitHub Actions runners are ephemeral.

Therefore design two execution modes.

## MODE A — LOCAL / DEVELOPMENT

Used for:

* debugging
* selector development
* initial Naukri validation
* inspecting forms
* troubleshooting

Playwright launches a browser locally.

---

## MODE B — GITHUB ACTIONS / CI

The workflow must explicitly provision the browser environment.

For example:

```text
GitHub Actions runner
    ↓
Checkout repository
    ↓
Install Python/Node dependencies
    ↓
Install Playwright
    ↓
Install required browser binaries
    ↓
Load secrets
    ↓
Start Playwright
    ↓
Execute automation
    ↓
Store screenshots/logs/artifacts
    ↓
Generate report
```

Do not depend on a browser installed manually on the developer machine.

---

# 15. AUTHENTICATION IN GITHUB ACTIONS

Do not commit browser session cookies or authentication state to GitHub.

Use one of the following supported approaches:

1. Login using credentials stored in GitHub Secrets, if permitted by the target site.
2. Use an approved persistent browser/session mechanism if supported securely.
3. If MFA/OTP is required, stop and report manual intervention.

Never store:

* passwords in source code
* cookies in Git
* session tokens in repository files
* authentication state in reports

Secrets must be injected into the GitHub Actions runtime.

---

# 16. GITHUB ACTIONS BROWSER ENVIRONMENT

Create a dedicated workflow/job for browser automation.

Conceptually:

```text
job_application:

  runner:
    ubuntu-latest

  steps:

    checkout

    setup_runtime

    install_dependencies

    install_playwright

    install_browser

    load_secrets

    run_discovery

    run_application_agent

    collect_browser_artifacts

    run_verification

    generate_report

    send_email
```

Browser failures must produce useful artifacts.

Where appropriate, save:

```text
artifacts/
  screenshots/
  browser_logs/
  failed_pages/
  application_evidence/
```

Do not store sensitive authentication information in these artifacts.

---

# 17. BROWSER FAILURE HANDLING

If Playwright encounters:

* selector not found
* page timeout
* unexpected redirect
* application form changed
* browser crash
* network failure
* CAPTCHA
* MFA
* bot detection

do not report application success.

Instead:

```text
APPLICATION_FAILED
```

or:

```text
APPLICATION_BLOCKED
```

with the exact reason.

The system should preserve enough diagnostic evidence to troubleshoot the problem.

---

# 18. DYNAMIC FORM HANDLING

Do NOT hard-code one application form.

Application forms can change by:

* company
* job
* ATS
* Naukri workflow
* application questions
* location
* candidate profile
* job requirements

The agent should inspect the DOM and identify form elements dynamically.

Use robust selectors based on:

* labels
* accessible names
* semantic roles
* stable attributes
* surrounding text

Avoid fragile selectors such as:

```text
div:nth-child(17)
```

where possible.

---

# 19. APPLICATION CONFIRMATION

Build a dedicated:

`ApplicationVerifier`

It must determine whether submission actually succeeded.

Possible verification hierarchy:

### Level 1

Explicit success/confirmation page.

### Level 2

Application reference/ID.

### Level 3

Naukri application history indicates applied.

### Level 4

External ATS application history/confirmation.

### Level 5

Other reliable application confirmation evidence.

If no reliable evidence exists:

DO NOT mark APPLIED_CONFIRMED.

Use:

`SUBMISSION_UNVERIFIED`

---

# 20. JOB LINK VALIDATION

Every report entry must pass URL validation.

For each application:

```text
source_job_url
canonical_job_url
application_url
final_url
```

Validate:

* URL reachable
* correct company
* correct role
* correct job
* no homepage redirect
* no expired listing
* no unrelated job

If the URL cannot be validated:

do not include it as a successful application.

---

# 21. REPORTING RULE

The email must distinguish:

### APPLIED

Verified successful applications.

### APPLICATION_ATTEMPTED

Submission was attempted but confirmation has not yet been established.

### BLOCKED

Automation was prevented.

### FAILED

Technical or application failure.

### EXTERNAL_APPLICATION_REQUIRED

Naukri redirected to another portal and the workflow could not complete it.

### SKIPPED

Did not meet eligibility criteria.

Never collapse these statuses into "Applied."

---

# 22. DAILY EMAIL EXAMPLE

The daily email should look approximately like:

CAREER AGENT — APPLICATION REPORT
Date: YYYY-MM-DD

Jobs discovered: 184

Salary rejected:
67

Qualified:
29

Applications confirmed:
8

Applications attempted but unverified:
1

Blocked:
2

Failed:
1

External portal applications:
4

CONFIRMED APPLICATIONS

1. Principal Cloud Architect – AI
   Company: ABC
   Salary: Not disclosed
   Match: 94%
   Method: Naukri Direct
   Status: APPLIED_CONFIRMED

2. AI Platform Architect
   Company: XYZ
   Salary: ₹25–35 LPA
   Match: 91%
   Method: External Portal / Workday
   Status: APPLIED_CONFIRMED

UNVERIFIED

1. Cloud Architect – GenAI
   Status: SUBMISSION_UNVERIFIED
   Reason: No confirmation detected

BLOCKED

1. Enterprise AI Architect
   Status: APPLICATION_BLOCKED
   Reason: MFA required

Every job listed as APPLIED_CONFIRMED must have corresponding evidence in the application database.

---

# 23. DATABASE CHANGES

Ensure the database contains enough information to prove what happened.

Application record should include:

```text
application_id
job_id
application_method
source_job_url
canonical_job_url
application_url
external_application_url
external_portal
started_at
submitted_at
status
resume_version
questions_detected
questions_answered
confirmation_detected
confirmation_text
confirmation_reference
final_url
verification_method
error_code
error_message
evidence_path
```

---

# 24. PHASE GATE

Implement an explicit validation command/report:

```text
career-agent validate-application-phase
```

It should inspect actual application records.

The phase passes only when:

* at least one eligible job was found
* at least one real application was attempted
* at least one application has `APPLIED_CONFIRMED`
* job URL was validated
* application method was recorded
* resume version was recorded
* confirmation evidence exists

Otherwise:

```text
PHASE STATUS: FAILED
```

Do not claim the phase passed.

---

# 25. RE-RUN PROCEDURE

Now re-run the complete workflow.

Before running:

1. Inspect current implementation.
2. Inspect existing resume.
3. Inspect current database/state.
4. Inspect previous run results.
5. Identify why previous applications were not actually submitted.
6. Fix the application workflow.
7. Fix reporting so dummy/false application success cannot occur.
8. Test browser workflow.
9. Run real application validation.
10. Verify actual submission.
11. Generate email only from verified state.

Do NOT simply rerun the same broken workflow.

---

# 26. IMPORTANT: REAL APPLICATIONS VS DRY RUN

For this specific validation phase:

Do NOT use:

```text
DRY_RUN=true
```

for the actual end-to-end application test.

Use the configured production application mode.

However, first verify that:

* the correct account is being used
* the correct candidate profile is loaded
* the correct resume is selected
* the salary filter is active
* the application threshold is active
* duplicate protection is active
* the application verifier is active

Then perform the real test.

---

# 27. DO NOT OVER-APPLY DURING VALIDATION

Do not immediately submit dozens of applications just to prove automation works.

Use a small number of genuinely eligible jobs for initial validation.

For example:

```text
Validation target:
1–3 real eligible applications
```

Once the complete workflow is proven:

* increase to normal configured daily limit
* monitor success rate
* monitor failures
* refine selectors and ATS adapters

---

# 28. EXTERNAL ATS ADAPTER ARCHITECTURE

Design external applications as adapters.

Example:

```text
ApplicationEngine
      |
      +-- NaukriDirectAdapter
      |
      +-- WorkdayAdapter
      |
      +-- GreenhouseAdapter
      |
      +-- LeverAdapter
      |
      +-- GenericExternalPortalAdapter
```

Initially implement:

1. Naukri direct
2. Generic external portal

Then add ATS-specific adapters as real jobs reveal the need.

Do not pretend an ATS is supported when it isn't.

If an external portal is unsupported:

`EXTERNAL_APPLICATION_REQUIRED`

---

# 29. GENERIC EXTERNAL PORTAL DETECTION

Detect the external portal based on:

* domain
* page structure
* known ATS patterns
* URL patterns
* page title
* form structure

Store:

```text
detected_platform
confidence
external_domain
```

If confidence is low:

use generic handling or stop safely.

---

# 30. GITHUB ACTIONS AND LONG-RUNNING BROWSER JOBS

The GitHub Actions workflow must account for:

* browser startup time
* login time
* page navigation
* slow external ATS pages
* retries
* job timeouts
* network failures
* runner cleanup

Configure appropriate:

* job timeout
* page timeout
* navigation timeout
* retry policy

Do not allow one broken job to block the entire daily run indefinitely.

Each application should have an isolated execution context where practical.

---

# 31. CONCURRENCY

Do not run multiple application agents against the same account simultaneously unless explicitly supported.

Use GitHub Actions concurrency controls.

Ensure:

```text
daily run A
```

cannot overlap with:

```text
daily run B
```

and create duplicate applications.

---

# 32. FINAL VALIDATION REPORT

At the end of this phase, produce a technical validation report containing:

### Environment

* runner
* browser
* Playwright version
* application mode
* timestamp

### Jobs

* discovered
* eligible
* rejected
* URLs validated

### Applications

* attempted
* confirmed
* failed
* blocked
* external
* unverified

### Browser

* successful sessions
* failed sessions
* selector failures
* authentication issues

### Evidence

For every confirmed application:

* job URL
* application URL
* company
* role
* application method
* timestamp
* confirmation evidence
* resume version
* verification method

### Final result

Either:

```text
APPLICATION AUTOMATION PHASE: PASSED
```

or:

```text
APPLICATION AUTOMATION PHASE: FAILED
```

Do not use ambiguous wording.

---

# 33. MOST IMPORTANT RULE

The system's definition of success is:

> A real eligible job was opened, the correct application workflow was completed, the correct resume was submitted, required questions were answered truthfully, the final submission actually occurred, and reliable evidence confirms that the application was submitted.

Anything less is NOT a successful application.

A generated email is NOT evidence.

A clicked button is NOT evidence.

An opened form is NOT evidence.

A redirected URL is NOT evidence.

A generated resume is NOT evidence.

Only verified application submission counts.

---

# 34. EXECUTE NOW

Do not merely explain how this should work.

Inspect the current project and implement the changes.

Then:

1. Run the application discovery.
2. Select genuinely eligible jobs.
3. Open their real job pages.
4. Validate their URLs.
5. Determine whether each application is:

   * Naukri Direct
   * External Portal
6. Execute the correct workflow.
7. Handle pre-application questions dynamically.
8. Upload the correct ATS resume.
9. Submit the application.
10. Verify confirmation.
11. Record evidence.
12. Generate the report.
13. Send the email based ONLY on verified application records.
14. Run the phase validation.
15. Report PASS or FAIL.

If the phase fails, clearly identify the exact failure point and fix it before declaring the system operational.

Do not tell me the system is working merely because the code executed successfully.

The objective is **real-world end-to-end application success**.
