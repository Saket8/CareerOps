# TASK-002: Complete Chatbot Applications & Eliminate False External Classifications

> **Status:** DONE  
> **Created:** 2026-09-23  
> **Target Release:** Immediate  
> **Priority:** High  

---

## 1. Objective

1. Resolve `APPLICATION_FAILED` on jobs with recruiter chatbots (e.g., Nagarro `Architect- Generative AI` `020926022745`) by properly distinguishing Yes/No vs numeric questions, mapping chip options affirmatively/negatively, and completing all turns to reach verified submission (`.already-applied` badge).
2. Eliminate false `EXTERNAL_APPLICATION_REQUIRED` classifications for internal Naukri jobs that contain screening questions. Ensure that external classification occurs ONLY when the apply action navigates to a non-Naukri domain.
3. Separate unhandled screening questions (`NEEDS_MANUAL_INTERVENTION`) from genuine external ATS opportunities (`EXTERNAL_APPLICATION_REQUIRED`) in the daily report email.

---

## 2. Scope & Technical Architecture

### 2.1. Candidate Answer Resolver (`src/naukri/candidate_answer_resolver.py`)
- Distinguish between inquiry type:
  - Auxiliary verb questions (`"Do you have..."`, `"Have you worked on..."`, `"Are you certified..."`) return `"Yes"` or `"No"`.
  - Duration inquiries (`"How many years..."`, `"Total years..."`) return numeric string.
- Expand skill coverage:
  - Generative AI / GenAI / LLM / RAG -> 2 years
  - AIOps / MLOps -> 2 years
  - System Design / Solutioning / Architecture -> 6 years
  - Implementation / Delivery -> 6 years
  - Highest qualification percentage (B.Tech) -> 70%

### 2.2. Playwright Adapter (`src/naukri/playwright_adapter.py`)
- Remove premature DOM matching of `"Apply on company site"` text.
- Prioritize locating and clicking the primary Naukri Apply button.
- Only assign `EXTERNAL_APPLICATION_REQUIRED` if the primary action navigates to an external non-Naukri hostname.
- In chatbot drawer:
  - Match affirmative answers (`"yes"`, positive numbers) to `YES` chips.
  - Match negative answers (`"no"`, `"0"`) to `NO` chips.
  - Click submit/save/continue/sendMsg after selecting chips.
  - Increase turn limit to 15 turns.

### 2.3. Daily Report Generator (`src/agents/reporting.py`)
- Only include true `JobStatus.EXTERNAL_APPLICATION_REQUIRED` in "External Opportunities".
- Render `JobStatus.NEEDS_MANUAL_INTERVENTION` under a distinct section "Screening Review Required".

---

## 3. Inputs & Outputs

### Inputs
- Candidate facts: `candidate/candidate_facts.yaml`
- Job listings with recruiter chatbots or screening modals
- Playwright page interactions

### Outputs
- `ApplicationRecord` marked `APPLIED_CONFIRMED` with screenshot evidence when chatbot completes.
- Accurate job status and URLs.
- Clear daily report email.

---

## 4. Dependencies
- `src/naukri/candidate_answer_resolver.py`
- `src/naukri/playwright_adapter.py`
- `src/agents/reporting.py`
- `tests/unit/test_candidate_answer_resolver.py`

---

## 5. Validation Criteria
- 100% test pass rate in pytest suite.
- Test cases covering all new question patterns and yes/no distinctions.
- Live verification via GitHub Actions pipeline run.

---

## 6. Rollback Considerations & Risk Impact
- **Rollback:** `git revert` cleanly restores prior adapter and resolver state.
- **Risk Impact:** Low risk of false negatives; significantly increases successful application rate on Naukri.

---

## 7. Validation Evidence
- **Candidate Answer Resolver Tests:** 6/6 passed in `tests/unit/test_candidate_answer_resolver.py` (covering yes/no auxiliary inquiry, duration extraction, Generative AI, AIOps, System Design, Implementation, highest qualification percentage 70%, and school qualification guards).
- **Unit Suite:** 83/83 tests passing across all core modules.
- **Integration Suite:** 2/2 tests passing (`test_mock_browser_apply_flow_and_badge_verification`, `test_end_to_end_dry_run_pipeline`).
- **Total Suite:** 85/85 tests passed in 24 seconds.
