"""Interview Intelligence Agent.

Generates comprehensive 7-document interview preparation packs operating across
Level 1 (Knowledge), Level 2 (Architecture), and Level 3 (Principal Architect).
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from src.models.job import JobListing
from src.models.score import JobScore, JobEvidence
from src.models.candidate import CandidateTruth
from src.database.repositories.interview_repo import InterviewRepository
from src.utils.logger import get_logger

logger = get_logger("interview_agent")


class InterviewAgent:
    """Generates 7-file interview intelligence packages for top-tier matched opportunities."""

    def __init__(self, interview_repo: InterviewRepository, candidate_truth: CandidateTruth, base_dir: Path = Path("interviews")):
        self.interview_repo = interview_repo
        self.candidate_truth = candidate_truth
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def generate_interview_pack(self, job: JobListing, score: JobScore, evidence: JobEvidence) -> Path:
        """Generates the full 7-file preparation suite for an eligible job."""
        safe_company = re.sub(r"[^\w\-]", "_", job.company).strip("_")
        safe_role = re.sub(r"[^\w\-]", "_", job.title).strip("_")
        pack_dir = self.base_dir / safe_company / safe_role
        pack_dir.mkdir(parents=True, exist_ok=True)

        cand = self.candidate_truth.candidate

        # 1. JD.md
        jd_content = f"""# Job Description: {job.title}
**Company:** {job.company}  
**Location:** {job.location} ({job.work_mode})  
**Salary:** {job.salary.raw_text or 'Not Disclosed'} ({job.salary.eligibility.value})  
**Source Query:** {job.source_query}  
**Platform:** {job.source_platform}  
**Job URL:** {job.url}  

---

## Complete Job Specification
{job.jd_text}
"""
        (pack_dir / "JD.md").write_text(jd_content, encoding="utf-8")

        # 2. match-analysis.md
        match_content = f"""# Match Analysis: {job.title} @ {job.company}

## Overall Fit Score: {score.overall_score}% ({'HIGH MATCH' if score.overall_score >= 85 else 'QUALIFIED'})

### Dimension Breakdown
| Dimension | Score | Assessment |
|---|---|---|
| Architecture Responsibility | {score.architecture_score}% | High enterprise design focus |
| Cloud Infrastructure (OCI/Multi-cloud) | {score.cloud_score}% | 6+ years OCI + cross-cloud interconnectivity |
| OCI Specialization | {score.oci_score}% | Deep platform mastery, 6 Oracle Certifications |
| AI / GenAI / Platform | {score.ai_score}% | GenAI CloudOps, LangChain, MCP server modernization |
| Agentic AI Frameworks | {score.agentic_ai_score}% | Autonomous database ops (ODAOS), local LLMs |
| Kubernetes Platform (OKE) | {score.kubernetes_score}% | Production private OKE, FSS storage, RBAC |
| Security, IAM & Governance | {score.security_score}% | Air-gapped landing zones, SAML/SSO federation |
| Multi-Cloud Interconnect | {score.multicloud_score}% | AWS, Azure, GCP monitoring & Palo Alto firewalls |
| Experience Alignment | {score.experience_alignment}% | 12+ years enterprise IT tenure |

### Identified Strengths
{chr(10).join(f"- **{s}**" for s in score.strengths)}

### Observed Market Signals
{chr(10).join(f"- {fact}" for fact in evidence.observed_facts)}
"""
        (pack_dir / "match-analysis.md").write_text(match_content, encoding="utf-8")

        # 3. likely-questions.md
        questions_content = f"""# Comprehensive Interview Questions: {job.title}

## LEVEL 1: Technology Concepts & Fundamentals (Knowledge)
1. **OCI Networking & Hub-and-Spoke Topology**
   - *Why interviewer asks:* To verify fundamental understanding of enterprise cloud networking.
   - *Topic:* VCN, DRG, LPG, FastConnect, Private DNS zones.
2. **Kubernetes Private OKE Architecture**
   - *Why interviewer asks:* Tests container orchestration security fundamentals.
   - *Topic:* Worker node isolation, private API endpoints, network security groups.
3. **Model Context Protocol (MCP) & Agent Architecture**
   - *Why interviewer asks:* Validates modern AI tooling knowledge beyond simple prompting.
   - *Topic:* MCP client-server architecture, local LLM integration, tool calling.

---

## LEVEL 2: Enterprise Systems Architecture (Design)
1. **Air-Gapped Cloud Platform Architecture**
   - *Scenario:* Design an air-gapped OCI landing zone for regulated telecom billing.
   - *Topic:* Isolation boundaries, bastion patterns, zero internet egress, FSS persistent volumes.
2. **RAG & GenAI CloudOps Architecture**
   - *Scenario:* Design an offline AI-assisted diagnostics system for platform incident triaging.
   - *Topic:* Local vector storage, LangChain orchestration, privacy-preserving LLMs.
3. **Multi-Cloud Identity Federation**
   - *Scenario:* Federate OCI IAM with Azure Active Directory using SAML and SCIM.
   - *Topic:* SSO, SCIM group synchronization, IAM policies, privileged access management.

---

## LEVEL 3: Principal Architect Strategy & Cross-Questioning (Trade-offs)
1. **Provider Strategy: Why OCI GenAI vs Hyperscaler Alternatives?**
   - *Question:* Why deploy on OCI GenAI instead of OpenAI / AWS Bedrock?
   - *Follow-up 1:* How do you guarantee data residency and sovereignty?
   - *Follow-up 2:* How do you control inference token costs at enterprise scale?
   - *Follow-up 3:* What is the failover strategy if model endpoints degrade?
2. **Platform Scalability & Blast Radius Containment**
   - *Question:* How do you architect multi-tenant Kubernetes platforms to survive catastrophic node pool failure?
   - *Follow-up:* What storage trade-offs exist between Block Volumes and FSS in high-throughput database workloads?
"""
        (pack_dir / "likely-questions.md").write_text(questions_content, encoding="utf-8")

        # 4. model-answers.md
        answers_content = f"""# Model Answers Grounded in Candidate Experience

## 1. Air-Gapped OCI Architecture
**Interviewer:** "How have you architected secure, air-gapped environments on Oracle Cloud Infrastructure?"  
**Candidate Answer:**  
> *"In my role as Principal Cloud Engineer for KPN's telecom billing modernization, I owned the end-to-end architecture of a production-grade, air-gapped OCI landing zone. We established a strict hub-and-spoke VCN topology with centralized Network Firewalls and delegated private DNS zones. For container workloads, we provisioned private OKE clusters segmented from database and storage tiers. Storage persistence was engineered using OCI FSS with custom StorageClasses and PVCs. Access was restricted through native RBAC without external identity dependencies, achieving zero external exposure while cutting platform incidents by 40%."*

## 2. GenAI CloudOps & Model Context Protocol (MCP)
**Interviewer:** "Describe your practical hands-on experience with GenAI and AI platform operations."  
**Candidate Answer:**  
> *"Rather than viewing GenAI theoretically, I delivered a GenAI-powered CloudOps Dashboard that unified OCI Monitoring, cost analytics, and automated remediation. In air-gapped environments where internet LLM APIs are prohibited, I developed an offline ChatOps CLI leveraging LangChain and local models for intelligent incident triaging. Additionally, I modernized existing cloud automation APIs by integrating Model Context Protocol (MCP) servers, enabling secure context streaming to AI assistants and accelerating infrastructure operations."*

## 3. Infrastructure as Code & Drift Prevention
**Interviewer:** "How do you enforce multi-environment consistency across dev, staging, and production?"  
**Candidate Answer:**  
> *"At both Cognizant and Emerson, I standardized Terraform modular architectures. By isolating environment-specific variables from reusable platform modules, we eliminated configuration drift, reduced release cycle times by 60%, and automated resource tagging via OCI CLI and Bash automation across hundreds of enterprise resources."*
"""
        (pack_dir / "model-answers.md").write_text(answers_content, encoding="utf-8")

        # 5. architecture-exercises.md
        exercises_content = f"""# Whiteboard Architecture Exercises

## Exercise 1: Resilient Telecom GenAI CloudOps Platform
- **Objective:** Draw the end-to-end dataflow for an intelligent alerting pipeline that analyzes OCI logs, routes events to an air-gapped local LLM, and triggers automated remediation.
- **Key Components:** OCI Service Connector Hub, ONS (Notifications), Private OKE Worker Nodes, LangChain ChatOps agent, OCI Vault for secrets, Terraform IaC definitions.

## Exercise 2: Hybrid Multi-Cloud Network with Palo Alto VM-Series
- **Objective:** Design network topology connecting on-prem data centers to OCI and Azure with centralized egress inspection.
- **Key Components:** Dynamic Routing Gateway (DRG), IPSec VPN tunnels, Palo Alto VM-Series firewalls in inspection VCN, NLB route tables, FastConnect redundancy.
"""
        (pack_dir / "architecture-exercises.md").write_text(exercises_content, encoding="utf-8")

        # 6. candidate-gaps.md
        gaps_content = f"""# Gap Analysis & Strategic Talking Points

## Identified Gaps & Mitigation Strategy
{chr(10).join(f"### Gap: {g}" for g in score.gaps) if score.gaps else "### No Major Technical Gaps Identified"}

### Positioning Strategy:
1. **Highlight Core Depth:** Emphasize that telecom-grade OCI architecture and private OKE environments are among the most stringent cloud deployments in the industry.
2. **Transferable Multi-Cloud Principles:** Demonstrate that networking topologies (VCN vs VPC), IAM policies (SAML SSO, RBAC), and IaC (Terraform) translate seamlessly across AWS, Azure, and GCP.
3. **Pragmatic AI Ops:** Position GenAI experience not as speculative R&D, but as real-world CloudOps automation (MCP, LangChain, local air-gapped LLMs).
"""
        (pack_dir / "candidate-gaps.md").write_text(gaps_content, encoding="utf-8")

        # 7. 7-day-preparation-plan.md
        plan_content = f"""# 7-Day Interview Preparation Roadmap: {job.title}

- **Day 1: Platform & OCI Fundamentals**
  - Review OCI landing zone best practices, VCN routing, DRG cross-tenancy, and IAM policy inheritance.
- **Day 2: Kubernetes (OKE) & Storage Deep Dive**
  - Review private cluster ingress (NLB/ALB), FSS persistent storage lifecycle, and RBAC isolation.
- **Day 3: GenAI, RAG & Model Context Protocol (MCP)**
  - Rehearse LangChain orchestration, offline ChatOps design, and MCP server integration talking points.
- **Day 4: Security, Identity & Compliance**
  - Prepare answers on air-gapped network boundaries, SAML SSO federation with Azure AD, and PAM hardening.
- **Day 5: Whiteboard Architecture Exercises**
  - Practice sketching Exercise 1 & 2 from `architecture-exercises.md` within a 20-minute timebox.
- **Day 6: Principal Architect Strategy & Trade-offs**
  - Practice cross-questioning on cost governance, scalability, high availability, and multi-cloud trade-offs.
- **Day 7: Mock Interview & Executive Presence**
  - Run the interactive simulator (`python scripts/interview_simulator.py`) and refine concise delivery.
"""
        (pack_dir / "7-day-preparation-plan.md").write_text(plan_content, encoding="utf-8")

        # Record in database
        self.interview_repo.save_pack(
            job_id=job.job_id,
            company=job.company,
            role=job.title,
            directory_path=str(pack_dir),
            question_count=8,
        )

        logger.info(f"Generated 7-document Interview Pack for {job.company} -> {pack_dir}")
        return pack_dir
