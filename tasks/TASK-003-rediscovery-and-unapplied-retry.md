# TASK-003: Re-Discovery & Application Retry for Unapplied Jobs

> **Status:** DONE  
> **Created:** 2026-09-23  
> **Target Release:** Immediate  
> **Priority:** Critical  

---

## 1. Objective

1. Resolve the discovery deduplication gap in `src/agents/discovery.py` where a blanket `self.job_repo.exists(listing.job_id)` check skipped all previously discovered but unapplied jobs (including `APPLICATION_FAILED`, `NEEDS_MANUAL_INTERVENTION`, `SUBMISSION_UNVERIFIED`, and internal jobs falsely categorized as `EXTERNAL_APPLICATION_REQUIRED`).
2. Allow eligible unapplied jobs (specifically Nagarro `020926022745`, Quest Global `150926009635`, Siro Clinpharm `240826012337`, Tredence `010926009746`, and InApp `030726500156`) to be re-evaluated, qualified, and submitted via the updated Playwright adapter and candidate answer resolver.
3. Reuse cached `jd_text` from existing DB records during re-discovery to prevent redundant network latency and ensure high scoring confidence ($\ge 50$ chars).
4. Guard `ApplicationRepository.has_applied_to_job` and `has_applied_to_company_and_title` so that unapplied statuses (`APPLICATION_READY`, expired `APPLICATION_STARTED`) do not falsely block application submission across pipeline runs.

---

## 2. Scope & Technical Architecture

### 2.1. Discovery Deduplication Refinement (`src/agents/discovery.py`)
- Replace blanket `self.job_repo.exists(listing.job_id)` with granular status-aware inspection of `existing_job`:
  - **Skip Duplicate:**
    - `existing_job.status in (JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value)` (already submitted).
    - `existing_job.status == JobStatus.SALARY_REJECTED.value` (immutable compensation threshold rejection).
    - `existing_job.company` matches blocked employer (Cognizant/CTS).
    - `existing_job.status == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value` AND URL is an authentic external domain (non-`naukri.com`).
    - `existing_job.status == JobStatus.REJECTED.value` with full JD text ($\ge 50$ chars).
    - `existing_job.status in (JobStatus.SALARY_ELIGIBLE.value, JobStatus.DISCOVERED.value)` (already discovered without failure).
  - **Eligible for Retry / Re-evaluation:**
    - `APPLICATION_FAILED` (e.g. chatbot failure resolved in Phase 26).
    - `NEEDS_MANUAL_INTERVENTION` (e.g. screening questions resolved in Phase 26).
    - `SUBMISSION_UNVERIFIED` / expired `APPLICATION_STARTED`.
    - `EXTERNAL_APPLICATION_REQUIRED` where URL is a `naukri.com` internal domain (false external classification prior to Phase 26).
- When eligible for retry and `existing_job.jd_text` exists with $\ge 50$ chars, reuse cached JD text to avoid network overhead.

### 2.2. Application Idempotency Lease Expiration (`src/database/repositories/application_repo.py`)
- In `has_applied_to_job(job_id)`:
  - Return `True` if `status in (APPLIED, APPLIED_CONFIRMED)`.
  - For `APPLICATION_STARTED` or `SUBMISSION_ATTEMPTED`, return `True` ONLY if `started_at` was within the last 15 minutes (active run lease). If older, lease has expired and job can be retried.
  - Retain `APPLICATION_READY` support for idempotency in dry-run mode.
- In `has_applied_to_company_and_title(company, title)`:
  - Strictly check `status.in_([APPLIED, APPLIED_CONFIRMED])`.

---

## 3. Inputs & Outputs

### Inputs
- Naukri job listings from live search.
- Restored SQLite database cache containing prior job records.

### Outputs
- Eligible unapplied jobs re-admitted to `result.eligible_jobs`.
- Successful application attempts on previously failed/unapplied jobs.
- Zero duplicate applications to confirmed jobs (`APPLIED_CONFIRMED`).

---

## 4. Dependencies
- `src/agents/discovery.py`
- `src/database/repositories/application_repo.py`
- `tests/unit/test_discovery.py`
- `tests/unit/test_application_agent.py`

---

## 5. Validation Criteria
- 100% test pass rate across pytest unit and integration suites.
- Unit test verifying unapplied / failed jobs in DB are re-discovered and eligible for qualification.
- Unit test verifying `has_applied_to_job` handles active leases and unapplied statuses correctly.
- Live CI pipeline run confirms discovery of unapplied jobs.

---

## 6. Rollback Considerations & Risk Impact
- **Rollback:** Revert git commits on `main`.
- **Risk Impact:** Zero risk to already applied jobs (strict `.already-applied` card badge and `APPLIED_CONFIRMED` checks remain inviolate). High positive impact by unlocking stalled applications.

---

## 7. Validation Evidence
- **Targeted Unit Tests:** 6/6 passing in `test_discovery.py` and `test_application_agent.py`.
- **New Re-discovery Test:** `test_discovery_retries_failed_and_unapplied_jobs` passed, confirming that Nagarro (`APPLICATION_FAILED`), Quest Global (`NEEDS_MANUAL_INTERVENTION`), and InApp (internal `EXTERNAL_APPLICATION_REQUIRED`) are returned in `eligible_jobs` with cached JD text reused, while confirmed applied (`APPLIED_CONFIRMED`) and genuine external (`EXTERNAL_APPLICATION_REQUIRED`) jobs are skipped as duplicates.
- **Unit Suite:** 86/86 passed in 15.26 seconds.
- **Integration Suite:** 2/2 passed in 12.39 seconds.
- **Total Test Suite:** 88/88 passed (100% pass rate).
- **Proof-Based Phase Validator:** `python main.py --validate-phase` returned `>>> APPLICATION AUTOMATION PHASE: PASSED <<<` with 16 confirmed applications verified on disk.

