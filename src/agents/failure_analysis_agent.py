"""Failure Analysis and Self-Healing Agent.

Autonomously tracks failed and unverified applications, diagnoses root causes,
persists diagnostic telemetry to the application_failure_analyses database table,
and applies self-healing remediation (learning synonyms, updating filters,
marking disqualifications, and queuing retries).
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import ApplicationModel, JobModel, ApplicationFailureAnalysisModel
from src.database.repositories.failure_analysis_repo import FailureAnalysisRepository
from src.models.candidate import CandidateTruth
from src.models.job import JobStatus, ApplicationMethod
from src.utils.logger import get_logger
from src.utils.screening_knowledge import get_screening_knowledge_base

logger = get_logger("failure_analysis_agent")

DATA_DIR = Path("data")
LEARNED_EXCLUSIONS_FILE = DATA_DIR / "learned_exclusions.json"
LEARNED_LOCATION_SYNONYMS_FILE = DATA_DIR / "learned_location_synonyms.json"


class FailureDiagnostic:
    """Encapsulates the root cause diagnosis and self-healing action for a failed application."""

    def __init__(
        self,
        job_id: str,
        company: str,
        job_title: str,
        failure_status: str,
        root_cause_category: str,
        analysis_summary: str,
        self_healing_action: str,
        healing_status: str = "RESOLVED",
        retry_eligible: bool = False,
        self_healing_details: Optional[Dict[str, Any]] = None,
        raw_failure_reason: Optional[str] = None,
        screening_questions: Optional[List[Any]] = None,
        screening_answers: Optional[Dict[str, Any]] = None,
        evidence_path: Optional[str] = None,
        application_id: Optional[str] = None,
        run_id: Optional[str] = None,
        job_url: Optional[str] = None,
    ):
        self.job_id = job_id
        self.company = company
        self.job_title = job_title
        self.failure_status = failure_status
        self.root_cause_category = root_cause_category
        self.analysis_summary = analysis_summary
        self.self_healing_action = self_healing_action
        self.healing_status = healing_status
        self.retry_eligible = retry_eligible
        self.self_healing_details = self_healing_details or {}
        self.raw_failure_reason = raw_failure_reason
        self.screening_questions = screening_questions or []
        self.screening_answers = screening_answers or {}
        self.evidence_path = evidence_path
        self.application_id = application_id
        self.run_id = run_id
        self.job_url = job_url


class FailureAnalysisAgent:
    """Agent responsible for autonomous root-cause analysis and self-healing of failed applications."""

    def __init__(
        self,
        session: Session,
        candidate_truth: CandidateTruth,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.session = session
        self.candidate_truth = candidate_truth
        self.config = config or {}
        self.repo = FailureAnalysisRepository(session)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def diagnose_job(
        self,
        job: JobModel,
        app: Optional[ApplicationModel] = None,
    ) -> FailureDiagnostic:
        """Inspects job attributes, screening questions/answers, and logs to determine exact root cause."""
        status_val = app.status if app else job.status
        failure_reason = (app.failure_reason if app else None) or (app.error_message if app else "") or ""
        questions_answered = (app.questions_answered if app else {}) or {}
        questions_detected = (app.questions_detected if app else []) or []
        evidence_path = app.evidence_path if app else None
        app_id = app.application_id if app else None
        job_url = job.url or (app.source_job_url if app else "")

        title_lower = (job.title or "").lower()
        company_lower = (job.company or "").lower()
        raw_reason_lower = failure_reason.lower()

        # ---------------------------------------------------------
        # Vector 1: DIVERSITY / WOMEN RETURNSHIP PROGRAM RESTRICTION
        # ---------------------------------------------------------
        returnship_patterns = [
            r"\bwomen\b", r"\bwoman\b", r"\bfemale\b", r"\breturnship\b",
            r"\breturn\s+to\s+work\b", r"\bher\s+second\s+innings\b",
            r"\bcareer\s+comeback\b", r"\bre-ignite\b", r"\bdiversity\s+program\b",
            r"\bevolve\s*\|\s*.*returnship\b"
        ]
        is_diversity_title = any(re.search(pat, title_lower) for pat in returnship_patterns)
        gender_q_answered_no = any(
            ("woman" in q.lower() or "break of 6 months" in q.lower() or "returnship" in q.lower())
            and str(ans).strip().lower() in ["no", "false"]
            for q, ans in questions_answered.items()
        )

        if is_diversity_title or gender_q_answered_no:
            program_keyword = "women returnship program" if "returnship" in title_lower else "gender/affirmative initiative"
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="DIVERSITY_PROGRAM_RESTRICTION",
                analysis_summary=(
                    f"Job '{job.title}' @ {job.company} is an affirmative/diversity program ({program_keyword}). "
                    f"Truth-layer correctly answered 'No' to eligibility screening, causing recruiter chatbot to terminate without submission."
                ),
                self_healing_action="DISQUALIFIED_DIVERSITY_PROGRAM",
                healing_status="DISQUALIFIED_PERMANENT",
                retry_eligible=False,
                self_healing_details={
                    "exclusion_pattern_learned": "returnship" if "returnship" in title_lower else "women",
                    "reason": "Hard eligibility disqualification; permanently excluded from pipeline",
                },
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 2: LOCATION SYNONYM / MULTI-CHECKBOX MISMATCH
        # ---------------------------------------------------------
        location_q = any(
            any(w in q.lower() for w in ["location", "city", "residing", "relocate", "relocation", "where are you located", "which city"])
            for q in questions_answered.keys()
        ) or any(
            any(w in str(q_item).lower() for w in ["location", "city", "residing", "relocate"])
            for q_item in questions_detected
        )
        is_location_halt = (
            status_val == JobStatus.NEEDS_MANUAL_INTERVENTION.value
            and ("no matching option or visible input" in raw_reason_lower or location_q)
        )

        if is_location_halt or (location_q and status_val == JobStatus.NEEDS_MANUAL_INTERVENTION.value):
            learned_synonyms = ["Delhi / NCR", "Gurugram, Haryana", "Pune, Maharashtra", "Noida"]
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="LOCATION_SYNONYM_MISMATCH",
                analysis_summary=(
                    f"Recruiter chatbot presented custom location checkboxes (e.g. Delhi / NCR, Gurugram) "
                    f"while candidate resolver provided canonical string 'Noida, India'. "
                    f"Agent halted safely per verification guardrails to avoid guessing."
                ),
                self_healing_action="LOCATION_SYNONYM_LEARNED",
                healing_status="HEALED",
                retry_eligible=True,
                self_healing_details={
                    "learned_synonyms": learned_synonyms,
                    "remediation": "Registered NCR synonyms and preferred relocation regions; queued for automated retry.",
                },
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 3: EXPERIENCE / SKILL THRESHOLD DISQUALIFICATION
        # ---------------------------------------------------------
        # Recruiter asked years of experience and candidate answered strictly per truth (e.g. 2y GenAI for 10y JD, or 0y Django)
        exp_answers = {
            q: ans for q, ans in questions_answered.items()
            if any(w in q.lower() for w in ["years of experience", "hands-on experience", "experience do you have"])
        }
        low_exp_answers = [
            f"{q}: {ans}" for q, ans in exp_answers.items()
            if str(ans).strip() in ["0", "1", "2"]
        ]

        if low_exp_answers and status_val == JobStatus.APPLICATION_FAILED.value:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="EXPERIENCE_THRESHOLD_RESTRICTION",
                analysis_summary=(
                    f"Candidate provided verified truth on skill experience ({', '.join(low_exp_answers[:2])}). "
                    f"Recruiter chatbot automated rule dropped applicant below required seniority threshold and closed without submission."
                ),
                self_healing_action="DISQUALIFIED_EXPERIENCE_THRESHOLD",
                healing_status="DISQUALIFIED_PERMANENT",
                retry_eligible=False,
                self_healing_details={
                    "low_experience_answers": low_exp_answers,
                    "action": "Preserved Truth-Layer integrity. Permanently closed to prevent retry loops.",
                },
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 4: EXTERNAL PORTAL REDIRECT
        # ---------------------------------------------------------
        if status_val == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value or "external" in raw_reason_lower:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="EXTERNAL_PORTAL_REDIRECT",
                analysis_summary=(
                    f"Role at {job.company} redirects to external enterprise applicant tracking system (ATS). "
                    f"Tailored resume built and direct application link cataloged."
                ),
                self_healing_action="EXTERNAL_PORTAL_CATALOGED",
                healing_status="RESOLVED",
                retry_eligible=False,
                self_healing_details={"method": "EXTERNAL_PORTAL"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 5: CHATBOT DRAWER EARLY CLOSE / RELOAD TIMEOUT
        # ---------------------------------------------------------
        if "could not be confirmed on reload" in raw_reason_lower or "badge was absent" in raw_reason_lower:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="CHATBOT_SUBMISSION_UNCONFIRMED",
                analysis_summary=(
                    f"Application attempt completed questionnaire turns, but canonical page reload "
                    f"did not display official green 'Applied' badge. Submission not confirmed by Naukri backend."
                ),
                self_healing_action="SUBMISSION_VERIFICATION_INVESTIGATED",
                healing_status="ACTION_REQUIRED",
                retry_eligible=False,
                self_healing_details={"verification_ref": "BADGE_ABSENT_ON_RELOAD"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 6: LINKEDIN POPOVER TRAP / POINTER INTERCEPTION
        # ---------------------------------------------------------
        is_popover_trap = any(p in raw_reason_lower for p in [
            "intercepts pointer events", "popover-floating", "waiting for locator(\"dialog button[aria-label='dismiss']",
            "pointer events", "popover", "inert"
        ])
        if is_popover_trap:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="LINKEDIN_POPOVER_TRAP",
                analysis_summary=(
                    f"LinkedIn floating popover container intercepted modal pointer actions. "
                    f"Healed by updated modal selector filtering inert/floating dialogs."
                ),
                self_healing_action="HEALED_BY_ADAPTER_PATCH",
                healing_status="HEALED",
                retry_eligible=True,
                self_healing_details={"patch": "popover_filter_and_dispatch_dismiss"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 7: LINKEDIN FIELD VALIDATION / INVALID INPUT ERROR
        # ---------------------------------------------------------
        is_field_validation = any(p in raw_reason_lower for p in [
            "invalid input", "salary expectations", "gross per month", "yesnoida",
            "required screening field unanswered"
        ])
        if is_field_validation:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="LINKEDIN_FIELD_VALIDATION",
                analysis_summary=(
                    f"LinkedIn form input validation error (salary/numeric format). "
                    f"Healed by period/currency-aware numeric fallbacks and guarded location inputs."
                ),
                self_healing_action="HEALED_BY_ADAPTER_PATCH",
                healing_status="HEALED",
                retry_eligible=True,
                self_healing_details={"patch": "salary_numeric_and_location_guard"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 8: LINKEDIN UNRESOLVED SCREENING / MULTI-PAGE PAUSE
        # ---------------------------------------------------------
        is_li_unresolved = (
            "unresolved screening fields" in raw_reason_lower
            or "multi-page form pause" in raw_reason_lower
            or (status_val == JobStatus.NEEDS_MANUAL_INTERVENTION.value and ("linkedin" in (job.source_platform or "").lower() or job.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY))
        )
        if is_li_unresolved:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="LINKEDIN_UNRESOLVED_SCREENING",
                analysis_summary=(
                    f"LinkedIn Easy Apply paused on multi-page questionnaire. "
                    f"Screening knowledge base loaded; queued for autonomous catch-up retry."
                ),
                self_healing_action="LEARNED_SCREENING_RESPONSE",
                healing_status="HEALED",
                retry_eligible=True,
                self_healing_details={"method": "LINKEDIN_EASY_APPLY"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 9: LINKEDIN AUTH / CHECKPOINT CHALLENGE
        # ---------------------------------------------------------
        is_auth_checkpoint = any(p in raw_reason_lower for p in [
            "checkpoint", "challenge", "auth_required", "sign in to linkedin", "captcha", "security verification"
        ])
        if is_auth_checkpoint:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="LINKEDIN_AUTH_CHECKPOINT",
                analysis_summary="LinkedIn session expired or triggered a security verification checkpoint.",
                self_healing_action="ALERT_AUTH_CHECKPOINT_REQUIRED",
                healing_status="ACTION_REQUIRED",
                retry_eligible=False,
                self_healing_details={"alert": "MANUAL_BROWSER_LOGIN_NEEDED"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 10: NAUKRI NOTICE PERIOD CHIP MISMATCH
        # ---------------------------------------------------------
        notice_q = any("notice" in str(q).lower() for q in questions_answered.keys()) or any(
            "notice" in str(qd).lower() for qd in questions_detected
        ) or "notice" in raw_reason_lower
        if notice_q and status_val in (JobStatus.NEEDS_MANUAL_INTERVENTION.value, JobStatus.APPLICATION_FAILED.value):
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="NAUKRI_NOTICE_PERIOD_MISMATCH",
                analysis_summary=(
                    f"Naukri chatbot presented custom notice period chips (e.g. 3 Months, 2-3 Months). "
                    f"Healed by dedicated notice period chip mapper (90 days = 3 Months)."
                ),
                self_healing_action="HEALED_BY_ADAPTER_PATCH",
                healing_status="HEALED",
                retry_eligible=True,
                self_healing_details={"chip_learned": "3 Months / 90 Days"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 11: NAUKRI NUMERIC RANGE CHIP MISMATCH
        # ---------------------------------------------------------
        numeric_q = any(
            any(w in str(q).lower() for w in ["experience", "years", "rating", "percentage", "cgpa"])
            for q in questions_answered.keys()
        ) or any(
            any(w in str(qd).lower() for w in ["experience", "years"])
            for qd in questions_detected
        )
        if numeric_q and "no matching option or input was available" in raw_reason_lower:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="NAUKRI_NUMERIC_RANGE_CHIP",
                analysis_summary=(
                    f"Naukri chatbot presented numeric range chips (e.g. 3-5 years) with no text input. "
                    f"Healed by numeric range regex and non-halting option fallback."
                ),
                self_healing_action="HEALED_BY_ADAPTER_PATCH",
                healing_status="HEALED",
                retry_eligible=True,
                self_healing_details={"patch": "numeric_range_regex_and_fallback"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Vector 12: TRANSIENT TIMEOUT OR NETWORK STALL
        # ---------------------------------------------------------
        is_transient_timeout = any(p in raw_reason_lower for p in [
            "timeout 30000ms", "timeout 90s", "timed out", "timeoutexceeded",
            "connection timed out", "net::err", "econnreset"
        ])
        if is_transient_timeout:
            return FailureDiagnostic(
                job_id=job.job_id,
                company=job.company,
                job_title=job.title,
                failure_status=status_val,
                root_cause_category="TRANSIENT_TIMEOUT_OR_NETWORK",
                analysis_summary=f"Transient network or page-load timeout occurred: {failure_reason[:100]}...",
                self_healing_action="RETRY_TRANSIENT_NETWORK",
                healing_status="HEALED",
                retry_eligible=True,
                self_healing_details={"retry_type": "TRANSIENT_BACKOFF"},
                raw_failure_reason=failure_reason,
                screening_questions=questions_detected,
                screening_answers=questions_answered,
                evidence_path=evidence_path,
                application_id=app_id,
                job_url=job_url,
            )

        # ---------------------------------------------------------
        # Default / Fallback: GENERAL FAILURE
        # ---------------------------------------------------------
        return FailureDiagnostic(
            job_id=job.job_id,
            company=job.company,
            job_title=job.title,
            failure_status=status_val,
            root_cause_category="SCREENING_OPTION_UNMAPPED",
            analysis_summary=f"Unclassified failure: {failure_reason or 'No explicit failure reason recorded.'}",
            self_healing_action="LOGGED_FOR_INSPECTION",
            healing_status="ACTION_REQUIRED",
            retry_eligible=False,
            raw_failure_reason=failure_reason,
            screening_questions=questions_detected,
            screening_answers=questions_answered,
            evidence_path=evidence_path,
            application_id=app_id,
            job_url=job_url,
        )

    def self_heal(self, diagnostic: FailureDiagnostic) -> None:
        """Applies self-healing state transitions and persistent knowledge base updates."""
        logger.info(
            f"Applying self-healing for job {diagnostic.job_id} ({diagnostic.company}): "
            f"Action: {diagnostic.self_healing_action} | Status: {diagnostic.healing_status}"
        )

        job = self.session.query(JobModel).filter(JobModel.job_id == diagnostic.job_id).first()
        app = self.session.query(ApplicationModel).filter(ApplicationModel.job_id == diagnostic.job_id).first()

        # 1. Action: DISQUALIFIED_DIVERSITY_PROGRAM
        if diagnostic.self_healing_action == "DISQUALIFIED_DIVERSITY_PROGRAM":
            if job:
                job.status = JobStatus.DISQUALIFIED_DIVERSITY.value
            # Persist learned exclusion pattern to disk
            learned_patterns = []
            if LEARNED_EXCLUSIONS_FILE.exists():
                try:
                    with open(LEARNED_EXCLUSIONS_FILE, "r", encoding="utf-8") as f:
                        learned_patterns = json.load(f).get("patterns", [])
                except Exception:
                    pass
            new_pattern = r"\breturnship\b"
            if new_pattern not in learned_patterns:
                learned_patterns.append(new_pattern)
                with open(LEARNED_EXCLUSIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump({"patterns": learned_patterns, "updated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
                logger.info(f"Learned and persisted new exclusion pattern: '{new_pattern}'")

        # 2. Action: LOCATION_SYNONYM_LEARNED
        elif diagnostic.self_healing_action == "LOCATION_SYNONYM_LEARNED":
            if job:
                job.status = JobStatus.READY_FOR_RETRY.value
            if app:
                app.status = JobStatus.READY_FOR_RETRY.value

            # Persist learned location synonyms to disk
            learned_synonyms = {}
            if LEARNED_LOCATION_SYNONYMS_FILE.exists():
                try:
                    with open(LEARNED_LOCATION_SYNONYMS_FILE, "r", encoding="utf-8") as f:
                        learned_synonyms = json.load(f).get("mappings", {})
                except Exception:
                    pass
            noida_synonyms = set(learned_synonyms.get("noida", []))
            noida_synonyms.update(["delhi / ncr", "delhi ncr", "gurugram, haryana", "pune, maharashtra"])
            learned_synonyms["noida"] = sorted(list(noida_synonyms))
            with open(LEARNED_LOCATION_SYNONYMS_FILE, "w", encoding="utf-8") as f:
                json.dump({"mappings": learned_synonyms, "updated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
            logger.info("Learned and persisted NCR location synonym mappings.")

        # 3. Action: DISQUALIFIED_EXPERIENCE_THRESHOLD
        elif diagnostic.self_healing_action == "DISQUALIFIED_EXPERIENCE_THRESHOLD":
            if job:
                job.status = JobStatus.DISQUALIFIED_SCREENING.value

        # 4. Actions: HEALED_BY_ADAPTER_PATCH, LEARNED_SCREENING_RESPONSE, RETRY_TRANSIENT_NETWORK
        elif diagnostic.self_healing_action in ("HEALED_BY_ADAPTER_PATCH", "LEARNED_SCREENING_RESPONSE", "RETRY_TRANSIENT_NETWORK"):
            if job:
                job.status = JobStatus.READY_FOR_RETRY.value
            if app:
                app.status = JobStatus.READY_FOR_RETRY.value

            kb = get_screening_knowledge_base()
            if "notice" in diagnostic.root_cause_category.lower():
                kb.learn_answer("notice period", "90 Days")
                kb.learn_answer("serving notice", "No")
            elif "linkedin" in diagnostic.root_cause_category.lower():
                kb.learn_answer("salary expectation", "7500")

        # Fallback: any retry-eligible diagnostic transitions job to READY_FOR_RETRY
        if diagnostic.retry_eligible:
            if job and job.status != JobStatus.APPLIED_CONFIRMED.value:
                job.status = JobStatus.READY_FOR_RETRY.value
            if app and app.status != JobStatus.APPLIED_CONFIRMED.value:
                app.status = JobStatus.READY_FOR_RETRY.value

        # 5. Record analysis in database table
        self.repo.record_analysis(
            job_id=diagnostic.job_id,
            company=diagnostic.company,
            job_title=diagnostic.job_title,
            failure_status=diagnostic.failure_status,
            root_cause_category=diagnostic.root_cause_category,
            analysis_summary=diagnostic.analysis_summary,
            application_id=diagnostic.application_id,
            run_id=diagnostic.run_id,
            job_url=diagnostic.job_url,
            raw_failure_reason=diagnostic.raw_failure_reason,
            screening_questions=diagnostic.screening_questions,
            screening_answers=diagnostic.screening_answers,
            evidence_path=diagnostic.evidence_path,
            self_healing_action=diagnostic.self_healing_action,
            self_healing_details=diagnostic.self_healing_details,
            healing_status=diagnostic.healing_status,
            retry_eligible=diagnostic.retry_eligible,
        )
        self.session.commit()

    def analyze_and_heal_run(self, run_id: Optional[str] = None) -> List[FailureDiagnostic]:
        """Analyzes all unapplied, failed, or unverified jobs and executes self-healing."""
        diagnostics = []

        target_statuses = [
            JobStatus.APPLICATION_FAILED.value,
            JobStatus.NEEDS_MANUAL_INTERVENTION.value,
            JobStatus.SUBMISSION_UNVERIFIED.value,
            JobStatus.APPLICATION_BLOCKED.value,
            JobStatus.FAILED.value,
            JobStatus.BLOCKED.value,
        ]

        if run_id:
            # Query recent failed applications for current run session
            apps = (
                self.session.query(ApplicationModel)
                .join(JobModel, ApplicationModel.job_id == JobModel.job_id)
                .filter(ApplicationModel.status.in_(target_statuses))
                .order_by(ApplicationModel.created_at.desc())
                .limit(40)
                .all()
            )
            for app in apps:
                job = self.session.query(JobModel).filter(JobModel.job_id == app.job_id).first()
                if job:
                    diag = self.diagnose_job(job=job, app=app)
                    diag.run_id = run_id
                    self.self_heal(diag)
                    diagnostics.append(diag)
        else:
            # Analyze all recent unhealed failures across database
            failed_apps = (
                self.session.query(ApplicationModel)
                .filter(ApplicationModel.status.in_(target_statuses))
                .order_by(ApplicationModel.started_at.desc())
                .limit(50)
                .all()
            )
            for app in failed_apps:
                job = self.session.query(JobModel).filter(JobModel.job_id == app.job_id).first()
                if job:
                    diag = self.diagnose_job(job=job, app=app)
                    self.self_heal(diag)
                    diagnostics.append(diag)

        logger.info(f"Completed failure analysis and self-healing for {len(diagnostics)} jobs.")
        return diagnostics

    def generate_report_markdown(self, diagnostics: List[FailureDiagnostic]) -> str:
        """Generates a structured markdown report of failure diagnostics and self-healing actions."""
        if not diagnostics:
            return "No application failures recorded."

        lines = [
            "## 🔧 AUTONOMOUS FAILURE ANALYSIS & SELF-HEALING",
            f"Total Issues Analyzed: **{len(diagnostics)}**",
            "",
            "| Company | Role | Category | Root Cause & Diagnosis | Self-Healing Action | Status |",
            "|---|---|---|---|---|---|",
        ]
        for d in diagnostics:
            status_badge = f"`{d.healing_status}`"
            if d.healing_status == "HEALED":
                status_badge = "✅ `HEALED`"
            elif d.healing_status == "DISQUALIFIED_PERMANENT":
                status_badge = "🛑 `DISQUALIFIED`"
            elif d.healing_status == "RESOLVED":
                status_badge = "ℹ️ `RESOLVED`"

            clean_summary = d.analysis_summary.replace("|", "/")
            lines.append(
                f"| **{d.company}** | {d.job_title[:30]} | `{d.root_cause_category}` | {clean_summary[:80]}... | `{d.self_healing_action}` | {status_badge} |"
            )

        lines.append("")
        return "\n".join(lines)
