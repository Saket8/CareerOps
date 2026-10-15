"""Qualification and Evidence Extraction Agent.

Performs multi-dimensional scoring, gap analysis, and evidence extraction
(Observed vs Inferred vs Generated) strictly against verified candidate facts.
"""

import re
from typing import Tuple, List, Dict, Any, Set
from src.models.job import JobListing, JobStatus, ApplicationMethod
from src.models.score import JobScore, JobEvidence
from src.models.candidate import CandidateTruth
from src.database.repositories.job_repo import JobRepository
from src.utils.logger import get_logger

logger = get_logger("qualification_agent")


# Term sets for dimensional analysis
DIMENSION_KEYWORDS = {
    "architecture": [
        "architect", "architecture", "solutions architect", "enterprise architect",
        "cloud administrator", "cloud admin", "oci administrator",
        "cloud engineer", "infrastructure engineer", "systems engineer", "network engineer", "security engineer",
        "landing zone", "system design", "high availability", "disaster recovery",
        "topology", "scalability", "governance", "modernization"
    ],
    "cloud": [
        "cloud", "oci", "oracle cloud", "multi-cloud", "multicloud", "aws", "azure", "gcp",
        "vcn", "drg", "fastconnect", "iaas", "paas", "compute", "networking"
    ],
    "oci_specific": [
        "oci", "oracle cloud infrastructure", "oke", "exadata", "exacs", "autonomous database",
        "adw", "adb", "oci iam", "oci devops", "oci administrator", "oci compute", "oci network", "oci security"
    ],
    "ai_genai": [
        "genai", "generative ai", "ai", "artificial intelligence", "llm", "large language model",
        "llmops", "mlops", "ai ops", "ai architect", "ai platform engineer",
        "rag", "retrieval augmented", "langchain", "langgraph", "agentic", "ai platform",
        "model context protocol", "mcp", "chatops", "prompt engineering"
    ],
    "agentic_ai": [
        "agentic", "ai agent", "ai agents", "autonomous agent", "agent framework", "mcp", "multi-agent"
    ],
    "kubernetes": [
        "kubernetes", "k8s", "oke", "container", "docker", "helm", "eks", "aks", "gke",
        "microservices", "pod", "storageclass"
    ],
    "security": [
        "security", "iam", "rbac", "saml", "sso", "pam", "air-gapped", "isolation",
        "zero trust", "encryption", "tls", "firewall", "palo alto", "scim", "compliance"
    ],
    "iac_devops": [
        "terraform", "ansible", "iac", "infrastructure as code", "ci/cd", "devops",
        "pipeline", "github actions", "gitlab", "jenkins"
    ],
    "observability": [
        "prometheus", "grafana", "splunk", "datadog", "observability", "monitoring",
        "logging", "alerting", "metrics"
    ],
}


class QualificationAgent:
    """Analyzes JDs, computes weighted dimensional scores, and extracts evidence."""

    def __init__(self, job_repo: JobRepository, candidate_truth: CandidateTruth, config: Dict[str, Any]):
        self.job_repo = job_repo
        self.candidate_truth = candidate_truth
        self.config = config
        self.match_threshold = float(config.get("application", {}).get("match_threshold", 75.0))
        self.high_match_threshold = float(config.get("application", {}).get("high_match_threshold", 85.0))
        self.blocked_companies = [
            c.lower().strip() for c in config.get("safety", {}).get("blocked_companies", ["cognizant", "cts"])
        ]

    def evaluate_job(self, job: JobListing) -> Tuple[JobScore, JobEvidence]:
        """Evaluates a single job listing against candidate truth."""
        # 0. Employer Safety Gate
        if any(b in job.company.lower() for b in self.blocked_companies):
            logger.warning(f"Employer Safety Gate: Blocking qualification for job '{job.title}' at '{job.company}'")
            zero_score = JobScore(
                job_id=job.job_id,
                overall_score=0.0,
                architecture_score=0.0,
                cloud_score=0.0,
                oci_score=0.0,
                ai_score=0.0,
                agentic_ai_score=0.0,
                kubernetes_score=0.0,
                security_score=0.0,
                multicloud_score=0.0,
                experience_alignment=0.0,
                skill_alignment=0.0,
                passed_threshold=False,
                match_reasons=[],
                strengths=[],
                gaps=["Current employer is blocked per candidate safety policy"],
                categories=[],
            )
            empty_evidence = JobEvidence(
                job_id=job.job_id,
                observed_facts=[],
                inferred_signals=[],
                generated_actions=[],
            )
            job.status = JobStatus.REJECTED
            self.job_repo.save_job(job)
            return zero_score, empty_evidence

        # 0b. Program/Diversity Gate (Returnship / Gender-specific mismatch)
        from src.agents.discovery import DiscoveryAgent
        if DiscoveryAgent.is_restricted_program(job.title, job.jd_text or ""):
            logger.warning(f"Program Gate: Blocking qualification for job '{job.title}' at '{job.company}' due to gender/returnship program mismatch.")
            zero_score = JobScore(
                job_id=job.job_id,
                overall_score=0.0,
                architecture_score=0.0,
                cloud_score=0.0,
                oci_score=0.0,
                ai_score=0.0,
                agentic_ai_score=0.0,
                kubernetes_score=0.0,
                security_score=0.0,
                multicloud_score=0.0,
                experience_alignment=0.0,
                skill_alignment=0.0,
                passed_threshold=False,
                match_reasons=[],
                strengths=[],
                gaps=["Role targets gender-specific or returnship program that does not align with candidate profile"],
                categories=[],
            )
            empty_evidence = JobEvidence(
                job_id=job.job_id,
                observed_facts=[],
                inferred_signals=[],
                generated_actions=[],
            )
            job.status = JobStatus.REJECTED
            self.job_repo.save_job(job)
            return zero_score, empty_evidence

        # 0c. LinkedIn Visa Sponsorship & Relocation Pre-qualification Gate
        is_linkedin = (
            job.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY
            or "linkedin" in (job.source_platform or "").lower()
            or "linkedin" in (job.url or "").lower()
        )
        li_cfg = self.config.get("linkedin", {})
        if is_linkedin and (li_cfg.get("require_visa_sponsorship", True) or li_cfg.get("require_relocation", True)):
            from src.utils.visa_relocation_gate import VisaRelocationGate
            passed_li, reason_li = VisaRelocationGate.evaluate(job, li_cfg)
            if not passed_li:
                logger.info(f"LinkedIn Visa & Relocation Gate rejecting '{job.title}' @ '{job.company}': {reason_li}")
                zero_score = JobScore(
                    job_id=job.job_id,
                    overall_score=0.0,
                    architecture_score=0.0,
                    cloud_score=0.0,
                    oci_score=0.0,
                    ai_score=0.0,
                    agentic_ai_score=0.0,
                    kubernetes_score=0.0,
                    security_score=0.0,
                    multicloud_score=0.0,
                    experience_alignment=0.0,
                    skill_alignment=0.0,
                    passed_threshold=False,
                    match_reasons=[],
                    strengths=[],
                    gaps=[reason_li],
                    categories=[],
                )
                empty_evidence = JobEvidence(
                    job_id=job.job_id,
                    observed_facts=[],
                    inferred_signals=[],
                    generated_actions=[],
                )
                job.status = JobStatus.REJECTED
                self.job_repo.save_job(job)
                return zero_score, empty_evidence

        # 0d. Data Domain & Technology Exclusion Gate
        # Candidate is strictly a Cloud / OCI & AI / GenAI Architect, NOT a Data Architect / Data Engineer.
        title_lower = (job.title or "").lower()
        excluded_domains = self.config.get("safety", {}).get("excluded_job_titles", [
            "data architect", "data architecture", "big data", "data engineer",
            "data engineering", "data platform", "data warehouse", "data warehousing",
            "data lake", "data lakehouse", "data analytics", "data modeler",
            "data modeling", "data governance", "data pipeline", "data scientist",
            "data science", "data lead", "database architect", "data center architect",
            "data centre architect", "snowflake", "databricks"
        ])
        matched_excluded = next((d.lower() for d in excluded_domains if d.lower() in title_lower), None)
        if matched_excluded:
            logger.warning(f"Data Domain Exclusion Gate: Rejecting '{job.title}' @ '{job.company}' (Excluded keyword: '{matched_excluded}')")
            zero_score = JobScore(
                job_id=job.job_id,
                overall_score=0.0,
                architecture_score=0.0,
                cloud_score=0.0,
                oci_score=0.0,
                ai_score=0.0,
                agentic_ai_score=0.0,
                kubernetes_score=0.0,
                security_score=0.0,
                multicloud_score=0.0,
                experience_alignment=0.0,
                skill_alignment=0.0,
                passed_threshold=False,
                match_reasons=[],
                strengths=[],
                gaps=[f"Role title matches excluded domain keyword '{matched_excluded}'. Candidate target tracks are strictly Cloud/OCI and AI/GenAI Architecture, not Data Architecture."],
                categories=[],
            )
            empty_evidence = JobEvidence(
                job_id=job.job_id,
                observed_facts=[],
                inferred_signals=[],
                generated_actions=[],
            )
            job.status = JobStatus.REJECTED
            self.job_repo.save_job(job)
            return zero_score, empty_evidence

        query = getattr(job, "discovered_via_query", "") or getattr(job, "source_query", "") or ""
        skills = getattr(job, "skills_found", []) or []
        text = f"{job.title}\n{query}\n{job.jd_text or ''}\n{' '.join(skills)}".lower()

        # Compute dimension matches
        arch_score = self._compute_dimension_score(text, DIMENSION_KEYWORDS["architecture"])
        cloud_score = self._compute_dimension_score(text, DIMENSION_KEYWORDS["cloud"])
        oci_score = self._compute_dimension_score(text, DIMENSION_KEYWORDS["oci_specific"])
        ai_score = self._compute_dimension_score(text, DIMENSION_KEYWORDS["ai_genai"])
        agentic_score = self._compute_dimension_score(text, DIMENSION_KEYWORDS["agentic_ai"])
        k8s_score = self._compute_dimension_score(text, DIMENSION_KEYWORDS["kubernetes"])
        sec_score = self._compute_dimension_score(text, DIMENSION_KEYWORDS["security"])
        multicloud_score = 90.0 if ("multi-cloud" in text or "multicloud" in text or ("aws" in text and "oci" in text)) else 65.0

        # Experience alignment (Saket has 12 years total, 6.5 years cloud/OCI)
        exp_score = self._compute_experience_alignment(job)

        # Skill alignment across full candidate competencies
        skill_score = (cloud_score + k8s_score + sec_score + ai_score) / 4.0

        # Skill-First Multi-Pillar Matching:
        # Candidate has 2 core target tracks with zero cross-domain penalties:
        # Track 1: Oracle Cloud Infrastructure (OCI) / Enterprise Cloud Architect
        # Driven by OCI/Cloud + Architecture + Experience; not penalized for missing GenAI
        primary_cloud = max(oci_score, cloud_score)
        track_cloud_score = (
            (primary_cloud * 0.50)
            + (arch_score * 0.30)
            + (((k8s_score + sec_score) / 2.0) * 0.10)
            + (exp_score * 0.10)
        )

        # Track 2: AI / GenAI / LLMOps / Agentic AI Architect
        # Driven by AI/GenAI + Architecture + Experience; not penalized for missing K8s or Exadata
        primary_ai = max(ai_score, agentic_score)
        track_ai_score = (
            (primary_ai * 0.55)
            + (arch_score * 0.30)
            + (exp_score * 0.15)
        )

        # Track 3: Hybrid Enterprise Cloud + AI Architect
        track_hybrid_score = (
            (arch_score * 0.25)
            + (primary_cloud * 0.35)
            + (primary_ai * 0.30)
            + (exp_score * 0.10)
        )

        # Candidate overall score is evaluated against their best-aligned track
        overall_score = max(track_cloud_score, track_ai_score, track_hybrid_score)

        # Target Role & Core Skill Guarantee:
        # If the job title matches candidate's target architecture roles and the primary skill match is solid (>= 70%),
        # ensure the candidate's core profile is recognized without arbitrary peripheral penalties.
        title_lower = (job.title or "").lower()
        is_target_ai_role = any(kw in title_lower for kw in [
            "genai", "generative ai", "ai architect", "llm architect", "agentic",
            "ai platform", "ai lead", "llm lead", "ai solution architect"
        ])
        is_target_cloud_role = any(kw in title_lower for kw in [
            "oci architect", "oracle cloud", "cloud architect", "infrastructure architect",
            "enterprise architect", "platform architect", "cloud solutions architect",
            "oci security", "oracle cloud security", "oci network", "oracle cloud network",
            "oci compute", "oracle cloud compute", "oci iam", "oracle cloud iam",
            "oci administrator", "oracle cloud administrator", "oci admin", "oracle cloud admin",
            "oci engineer", "oracle cloud engineer", "oracle cloud microservices", "oci microservices"
        ])

        if is_target_ai_role and primary_ai >= 70.0:
            target_boosted = (primary_ai * 0.65) + (arch_score * 0.25) + (exp_score * 0.10)
            overall_score = max(overall_score, target_boosted)

        if is_target_cloud_role and primary_cloud >= 70.0:
            target_boosted = (primary_cloud * 0.65) + (arch_score * 0.25) + (exp_score * 0.10)
            overall_score = max(overall_score, target_boosted)

        overall_score = round(min(100.0, max(0.0, overall_score)), 1)

        # Full-JD Scoring Calibration & Confidence Gating:
        # If full JD text is unavailable (< 50 chars), do not assign high confidence scores
        has_full_jd = getattr(job, "has_full_jd", False) or bool(job.jd_text and len(job.jd_text.strip()) >= 50)
        if not has_full_jd:
            logger.info(f"Confidence Gating: Job {job.job_id} lacks full JD text; capping score below qualification threshold.")
            overall_score = min(overall_score, self.match_threshold - 1.0)

        # Experience Gate: Reject junior/intern roles (< 5 years max experience) for 12-year Principal Architect
        if job.experience_max is not None and job.experience_max < 5.0:
            logger.info(f"Experience Gate: Rejecting job '{job.title}' ({job.experience_raw}) as junior/intern role.")
            overall_score = min(overall_score, self.match_threshold - 10.0)

        # Domain Exclusion Gate: Reject roles whose primary specialization is outside candidate's core stack (Snowflake, Databricks)
        is_excluded_domain = any(tech in title_lower for tech in ["snowflake", "databricks"])
        if is_excluded_domain:
            logger.info(f"Domain Gate: Rejecting job '{job.title}' centered on excluded technologies (Snowflake/Databricks).")
            overall_score = min(overall_score, self.match_threshold - 15.0)

        # Determine Role Categories
        categories = self._determine_categories(text)

        # Identify Strengths and Gaps
        strengths, gaps, match_reasons = self._identify_strengths_and_gaps(text, oci_score, k8s_score, ai_score, sec_score)
        if not has_full_jd:
            gaps.append("Full JD text unavailable; scored tentatively on card snippet only.")
            match_reasons.append("Preliminary card metadata score (full JD retrieval pending).")
        if job.experience_max is not None and job.experience_max < 5.0:
            gaps.append(f"Role requires junior/entry-level experience ({job.experience_raw}); candidate has 12 years Principal Architect tenure.")
            match_reasons.append("Rejected by Experience Gate: junior/intern role incompatible with 12-year Principal Architect profile.")
        if is_excluded_domain:
            gaps.append("Role requires Snowflake/Databricks specialization, which is outside candidate's verified OCI/Cloud/AI core competencies.")
            match_reasons.append("Rejected by Domain Gate: Snowflake/Databricks specialization is outside candidate's target OCI & AI Architect tracks.")

        passed = overall_score >= self.match_threshold

        score = JobScore(
            job_id=job.job_id,
            overall_score=overall_score,
            architecture_score=round(arch_score, 1),
            cloud_score=round(cloud_score, 1),
            oci_score=round(oci_score, 1),
            ai_score=round(ai_score, 1),
            agentic_ai_score=round(agentic_score, 1),
            kubernetes_score=round(k8s_score, 1),
            security_score=round(sec_score, 1),
            multicloud_score=round(multicloud_score, 1),
            experience_alignment=round(exp_score, 1),
            skill_alignment=round(skill_score, 1),
            passed_threshold=passed,
            match_reasons=match_reasons,
            strengths=strengths,
            gaps=gaps,
            categories=categories,
        )

        # Structured Evidence Extraction: Observed vs Inferred vs Generated
        evidence = self._extract_evidence(job, text, score)

        # Persist to database
        self.job_repo.save_score(score)
        self.job_repo.save_evidence(evidence)

        # Update Job Status in DB (Preserve already APPLIED / APPLIED_CONFIRMED statuses)
        existing_job = self.job_repo.get(job.job_id)
        current_status = existing_job.status if existing_job else (job.status.value if hasattr(job.status, "value") else str(job.status))
        if current_status not in (JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value):
            new_status = JobStatus.HIGH_MATCH if overall_score >= self.high_match_threshold else (
                JobStatus.QUALIFIED if passed else JobStatus.REJECTED
            )
            self.job_repo.update_status(job.job_id, new_status)
            job.status = new_status
        else:
            try:
                job.status = JobStatus(current_status)
            except ValueError:
                job.status = JobStatus.APPLIED_CONFIRMED

        logger.info(
            f"Qualified '{job.title}' @ {job.company} -> Score: {overall_score}% "
            f"[{'HIGH_MATCH' if overall_score >= self.high_match_threshold else ('QUALIFIED' if passed else 'REJECTED')}]"
        )
        return score, evidence

    def qualify_all_eligible_jobs(self, eligible_jobs: List[JobListing]) -> List[Tuple[JobListing, JobScore, JobEvidence]]:
        """Evaluates all salary-eligible jobs discovered."""
        qualified = []
        for job in eligible_jobs:
            score, evidence = self.evaluate_job(job)
            if score.passed_threshold:
                qualified.append((job, score, evidence))
        return qualified

    def _compute_dimension_score(self, text: str, keywords: List[str]) -> float:
        hits = sum(1 for kw in keywords if kw in text)
        if hits >= 4:
            return 95.0
        elif hits == 3:
            return 85.0
        elif hits == 2:
            return 75.0
        elif hits == 1:
            return 60.0
        return 40.0

    def _compute_experience_alignment(self, job: JobListing) -> float:
        # Candidate has 12 years total experience
        cand_exp = self.candidate_truth.candidate.total_experience_years
        min_exp = job.experience_min if job.experience_min is not None else 0.0
        max_exp = job.experience_max if job.experience_max is not None else 20.0

        # Hard guardrail: If the role is strictly for junior/interns (< 5 years maximum)
        if job.experience_max is not None and job.experience_max < 5.0:
            return 10.0

        if min_exp <= cand_exp <= max_exp:
            return 95.0
        elif cand_exp < min_exp and (min_exp - cand_exp) <= 2:
            return 75.0
        elif cand_exp > max_exp and (cand_exp - max_exp) <= 3:
            return 85.0
        elif cand_exp > max_exp and (cand_exp - max_exp) <= 5:
            return 60.0
        return 20.0

    def _determine_categories(self, text: str) -> List[str]:
        cats = []
        if "oracle" in text or "oci" in text:
            cats.append("ORACLE_CLOUD_ADMIN_ARCHITECT")
        if "llmops" in text or "llm ops" in text or "ai platform" in text or "genai" in text:
            cats.append("LLMOPS_AI_ARCHITECT")
        if "architect" in text:
            cats.append("CLOUD_ARCHITECTURE")
        if "genai" in text or "generative ai" in text or "llm" in text:
            cats.append("GENAI_ARCHITECTURE")
        if "ai platform" in text or "mlops" in text:
            cats.append("AI_PLATFORM")
        if "agentic" in text or "ai agent" in text or "mcp" in text:
            cats.append("AGENTIC_AI")
        if "multi-cloud" in text or "multicloud" in text or ("aws" in text and "oci" in text):
            cats.append("MULTI_CLOUD")
        if "kubernetes" in text or "oke" in text or "container" in text:
            cats.append("KUBERNETES_PLATFORM")
        if "security" in text or "iam" in text or "saml" in text:
            cats.append("CLOUD_SECURITY")
        return cats or ["CLOUD_ARCHITECTURE"]

    def _identify_strengths_and_gaps(self, text: str, oci_score: float, k8s_score: float, ai_score: float, sec_score: float):
        strengths = []
        gaps = []
        reasons = []

        # High Priority Focus Strengths
        if "oracle" in text or "oci" in text:
            strengths.append("Verified OCI Deep Expertise (6+ years, 6 Professional certifications, DBSS telecom architecture)")
            reasons.append("High priority Oracle Cloud Admin / Architect alignment")
        if "llmops" in text or "llm ops" in text or "genai" in text or "mcp" in text:
            strengths.append("Verified LLMOps & GenAI platform engineering (ChatOps CLI, local LLMs, MCP servers)")
            reasons.append("High priority LLMOps / AI Architecture match")
        if "kubernetes" in text or "oke" in text:
            strengths.append("Verified OKE private cluster architecture & persistent storage (FSS)")
            reasons.append("Kubernetes container orchestration match")
        if "terraform" in text or "iac" in text:
            strengths.append("Verified Terraform modular infrastructure-as-code automation (~60% deployment reduction)")
            reasons.append("Infrastructure as Code alignment")
        if "genai" in text or "langchain" in text or "mcp" in text:
            strengths.append("Verified GenAI CloudOps Dashboard, air-gapped ChatOps CLI & MCP server modernizations")
            reasons.append("Hands-on enterprise GenAI & MCP integration experience")
        if "security" in text or "iam" in text or "saml" in text:
            strengths.append("Verified IAM federation (Azure AD / Okta / SAML SSO), air-gapped isolation & PAM hardening")
            reasons.append("Enterprise security & identity architecture match")

        # Potential Gaps
        if "aws sagemaker" in text:
            gaps.append("AWS SageMaker production pipeline experience not verified in candidate truth")
        if "azure openai" in text and "oci genai" not in text:
            gaps.append("Role specifically mentions Azure OpenAI; candidate primary expertise is OCI GenAI & local LLMs")
        if "golang" in text or "scala" in text:
            gaps.append("Specialized systems programming language required in JD absent from candidate verified skills")
        if "15+" in text or "18+" in text:
            gaps.append("Seniority exceeds candidate 12-year verified experience tenure")

        return strengths, gaps, reasons

    def _extract_evidence(self, job: JobListing, text: str, score: JobScore) -> JobEvidence:
        observed = []
        inferred = []
        generated = []
        skills_found = []
        tools_found = []
        patterns = []

        # 1. Observed facts
        for kw in ["oci", "kubernetes", "oke", "genai", "terraform", "rag", "mcp", "saml", "sso", "prometheus"]:
            if kw in text:
                skills_found.append(kw.upper())
                observed.append(f"Observed keyword '{kw.upper()}' explicitly mentioned in job description.")

        if job.salary.is_disclosed:
            observed.append(f"Disclosed compensation: ₹{job.salary.min_lpa} - ₹{job.salary.max_lpa} LPA.")
        else:
            observed.append("Compensation undisclosed by recruiter; accepted under compensation policy.")

        # 2. Inferred signals
        if "rag" in text and "genai" in text:
            inferred.append("Inferred requirement: Organization is designing contextual retrieval pipelines for enterprise data.")
        if "oke" in text or "kubernetes" in text:
            inferred.append("Inferred platform: Enterprise container platform requiring network segmentation and RBAC.")
        if score.overall_score >= self.high_match_threshold:
            inferred.append(f"High-affinity candidate alignment ({score.overall_score}%) with leadership/architect scope.")

        # 3. Generated actions
        generated.append(f"Tailor candidate resume to highlight {', '.join(skills_found[:4])}.")
        if "genai" in text or "rag" in text:
            generated.append("Generate RAG architecture and OCI Generative AI interview questions.")
        if "security" in text or "iam" in text:
            generated.append("Generate IAM federation and landing zone isolation interview exercises.")

        return JobEvidence(
            job_id=job.job_id,
            observed_facts=observed,
            inferred_signals=inferred,
            generated_actions=generated,
            skills_found=skills_found,
            tools_found=tools_found,
            architecture_patterns=patterns,
        )
