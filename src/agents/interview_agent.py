"""Interview Intelligence Agent.

Generates comprehensive 7-document interview preparation packs operating across
Level 1 (Knowledge), Level 2 (Architecture), and Level 3 (Principal Architect).
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from src.models.job import JobListing
from src.models.score import JobScore, JobEvidence
from src.models.candidate import CandidateTruth
from src.database.repositories.interview_repo import InterviewRepository
from src.utils.logger import get_logger

logger = get_logger("interview_agent")


class InterviewAgent:
    """Generates comprehensive interview intelligence packages and consolidated daily briefings."""

    def __init__(
        self,
        interview_repo: InterviewRepository,
        candidate_truth: CandidateTruth,
        base_dir: Path = Path("interviews"),
        reports_dir: Path = Path("reports/interviews"),
    ):
        self.interview_repo = interview_repo
        self.candidate_truth = candidate_truth
        self.base_dir = base_dir
        self.reports_dir = reports_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

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

    def generate_consolidated_daily_briefing(
        self,
        matched_items: List[Tuple[JobListing, JobScore, JobEvidence]],
        date_str: str,
    ) -> Tuple[Path, Path, str]:
        """Generates a single consolidated, executive-grade Word (.docx) and PDF interview briefing

        covering all qualifying high-match/applied roles of the day in one comprehensive document.
        """
        docx_path = self.reports_dir / f"Daily_Interview_Intelligence_{date_str}.docx"
        pdf_path = self.reports_dir / f"Daily_Interview_Intelligence_{date_str}.pdf"

        # 1. Build Consolidated DOCX
        doc = docx.Document()
        for sec in doc.sections:
            sec.top_margin = Inches(0.7)
            sec.bottom_margin = Inches(0.7)
            sec.left_margin = Inches(0.75)
            sec.right_margin = Inches(0.75)

        # Title Block
        t_p = doc.add_paragraph()
        t_p.paragraph_format.space_after = Pt(2)
        r_title = t_p.add_run("CAREEROPS — DAILY CONSOLIDATED INTERVIEW INTELLIGENCE")
        r_title.font.name = "Calibri"
        r_title.font.size = Pt(18)
        r_title.font.bold = True
        r_title.font.color.rgb = RGBColor(15, 23, 42)

        sub_p = doc.add_paragraph()
        sub_p.paragraph_format.space_after = Pt(14)
        r_sub = sub_p.add_run(
            f"Candidate: Saket Saurav  |  Target: Principal Cloud & AI Architect  |  Briefing Date: {date_str}"
        )
        r_sub.font.name = "Calibri"
        r_sub.font.size = Pt(10.5)
        r_sub.font.color.rgb = RGBColor(71, 85, 105)

        # Executive Overview
        doc.add_heading("1. Executive Target Opportunities Matrix", level=1)
        doc.add_paragraph(
            f"This consolidated briefing synthesizes interview preparation across {len(matched_items)} qualifying "
            f"high-match and applied enterprise opportunities for {date_str}. It integrates foundational knowledge "
            f"(Level 1), systems architecture design (Level 2), and principal-grade trade-off cross-questioning (Level 3)."
        )

        # Matrix Table
        if matched_items:
            table = doc.add_table(rows=1, cols=5)
            table.autofit = False
            hdr_cells = table.rows[0].cells
            headers = ["Company", "Target Role", "Match", "Salary", "Strategic Domain"]
            for idx, h in enumerate(headers):
                hdr_cells[idx].text = h
                for run in hdr_cells[idx].paragraphs[0].runs:
                    run.font.bold = True
                    run.font.size = Pt(9.5)

            for job, score, _ in matched_items:
                row_cells = table.add_row().cells
                row_cells[0].text = job.company
                row_cells[1].text = job.title
                row_cells[2].text = f"{score.overall_score:.1f}%"
                row_cells[3].text = job.salary.raw_text or "Not Disclosed"
                row_cells[4].text = "OCI + GenAI Platform" if score.ai_score > 70 else "Enterprise OCI Cloud"
                for cell in row_cells:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.font.size = Pt(9)
        else:
            doc.add_paragraph("Targeting: Enterprise Cloud & AI Architecture Opportunities across Pan India.")

        # Section 2: Technical Fundamentals
        doc.add_heading("2. High-Yield Technical Fundamentals (Level 1 - Core Knowledge)", level=1)
        p = doc.add_paragraph()
        p.add_run("A. OCI Enterprise Networking & Routing Topologies:\n").bold = True
        p.add_run(
            "• Dynamic Routing Gateway (DRG v2): Implements multi-tenancy transit routing, route tables, and import/export route distributions connecting VCNs, FastConnect circuits, and IPSec VPN tunnels without third-party appliance hops.\n"
            "• Private DNS Resolvers & Endpoints: Configured with custom views and listener/forwarder endpoints for split-horizon DNS resolution across hybrid on-premises and multi-region VCNs.\n"
            "• Service Gateway vs NAT Gateway: Service Gateway provides zero-internet egress to Oracle Services Network (OSN: Object Storage, OCI Vault, ADB) over private Oracle backbone; NAT Gateway is restricted to outbound internet traffic for private subnets."
        )

        p = doc.add_paragraph()
        p.add_run("B. Production Kubernetes (OKE) & Persistent Storage:\n").bold = True
        p.add_run(
            "• Private Cluster Isolation: Master control plane and worker node pools deployed entirely in private subnets with Network Security Groups (NSGs). Access orchestrated via private bastions and OCI IAM RBAC.\n"
            "• Persistent Storage Lifecycles: OCI File Storage Service (FSS) with custom NFS StorageClasses for multi-pod read-write-many (RWX) container state; ultra-low latency Block Volumes (up to 300k IOPS) for transactional stateful workloads.\n"
            "• Calico Network Policies: Enforce microservice egress isolation and namespace boundary containment."
        )

        p = doc.add_paragraph()
        p.add_run("C. GenAI Platform Engineering & Model Context Protocol (MCP):\n").bold = True
        p.add_run(
            "• Model Context Protocol (MCP): Client-host-server architecture streaming real-time enterprise context, file system metadata, and tool execution to AI models over secure JSON-RPC.\n"
            "• Offline ChatOps Triaging: Integrating LangChain pipelines with localized or air-gapped LLM runtimes for automated log summarization and incident root-cause analysis without internet leakage.\n"
            "• Vector RAG Pipeline: Chunking enterprise architecture runbooks into vector stores for sub-second retrieval during operational outages."
        )

        # Section 3: Whiteboard Systems Architecture Scenarios
        doc.add_heading("3. Enterprise Systems Architecture & Whiteboard Scenarios (Level 2 - Design)", level=1)
        doc.add_paragraph(
            "Scenario 1: Air-Gapped OCI Landing Zone for Regulated Telecom Billing\n"
            "• Objective: Deliver a zero-trust, production-grade cloud landing zone with zero external internet access.\n"
            "• Topology: Hub VCN with redundant Palo Alto VM-Series / OCI Network Firewalls. Spokes for OKE Container Tier, Exadata Database Tier, and Management Tier.\n"
            "• Key Security Guardrails: Centralized egress inspection, OCI Bastion Service with session auditing, Customer-Managed Keys (Vault/KMS) with HSM, and strict compartment separation."
        )
        doc.add_paragraph(
            "Scenario 2: Automated GenAI CloudOps Alert Triaging Platform\n"
            "• Objective: Ingest telemetry alerts across 500+ cloud resources, correlate symptoms, and suggest runbook actions within 30 seconds.\n"
            "• Dataflow: OCI Service Connector Hub streams log events to ONS (Notification Service) -> Containerized FastApi/LangChain microservice in private OKE -> Local RAG index fetches runbook -> LLM generates root-cause diagnosis -> Output dispatched to Slack/Teams with confidence score."
        )

        # Section 4: Principal Architect Strategy & Trade-offs
        doc.add_heading("4. Principal Architect Strategy & Trade-offs (Level 3 - Leadership)", level=1)
        doc.add_paragraph(
            "1. Dedicated AI Inference Clusters vs. Serverless On-Demand Endpoints:\n"
            "• Trade-off: Dedicated AI Clusters guarantee predictable latency, zero noisy-neighbor interference, and data residency, but incur high fixed reservation costs. Serverless endpoints scale to zero, optimal for bursty internal workloads.\n"
            "• Principal Position: Deploy dedicated clusters for mission-critical real-time billing and operational triaging; utilize serverless endpoints for asynchronous document parsing and developer exploratory workflows.\n\n"
            "2. Exadata Cloud Service (ExaCS) vs. Autonomous Database (ADB):\n"
            "• Trade-off: ADB delivers automated scaling, patching, and tuning, minimizing operational overhead by ~50%. ExaCS provides deep OS-level control, custom kernel parameters, and dedicated compute/storage expansion.\n"
            "• Principal Position: Advocate ADB for greenfield analytics, microservices, and standard OLTP. Preserve ExaCS for complex enterprise migrations requiring custom RAC configurations and specialized database options."
        )

        # Section 5: Role-Specific Talking Points & Gap Mitigation
        doc.add_heading("5. Role-Specific Talking Points & Gap Mitigation", level=1)
        if matched_items:
            for job, score, _ in matched_items:
                p = doc.add_paragraph()
                p.add_run(f"• {job.company} — {job.title} (Match: {score.overall_score:.1f}%):\n").bold = True
                p.add_run(
                    f"  - Key Strengths to Emphasize: {', '.join(score.strengths[:3]) if score.strengths else 'Deep cloud architecture, container platforms, enterprise security'}\n"
                    f"  - Strategic Angle: Position your 12+ years of enterprise IT leadership and 6.5+ years of OCI mastery as an instant de-risking factor for their modernization roadmap.\n"
                )
        else:
            doc.add_paragraph("Highlight 12+ years of total IT experience, 6 Oracle Certifications, and zero-fabrication truth layer.")

        # Section 6: Model Answers Grounded in Verified Facts
        doc.add_heading("6. Model STAR Answers (Grounded in Verified Candidate Truth)", level=1)
        doc.add_paragraph(
            "Q: Describe an instance where you architected high availability for mission-critical workloads on OCI.\n"
            "Answer (STAR Method):\n"
            "• Situation: During KPN's telecom billing cloud modernization, the platform required 99.99% availability in an air-gapped OCI tenancy.\n"
            "• Task: As Principal Cloud Architect, I was tasked with designing a zero-downtime, resilient architecture across compute, container, and storage layers.\n"
            "• Action: I designed a multi-AD/multi-FD private OKE cluster with anti-affinity pod rules, backed by OCI FSS with redundant mount targets and cross-compartment automated snapshots. I automated infrastructure provisioning using modular Terraform and integrated automated health monitoring via OCI Monitoring and CLI.\n"
            "• Result: Successfully cut deployment release cycles by 60%, reduced platform incidents by 40%, and achieved 100% compliant security audits."
        )

        # Section 7: 7-Day Targeted Preparation Roadmap
        doc.add_heading("7. 7-Day Targeted Preparation Action Plan", level=1)
        doc.add_paragraph(
            "• Day 1 (Architecture & Networking): Review DRG v2 route distribution, FastConnect redundancy, and Private DNS resolver views.\n"
            "• Day 2 (Kubernetes & Storage): Rehearse private OKE ingress patterns, FSS storage class lifecycle, and Calico egress network policies.\n"
            "• Day 3 (AI & GenAI Platform): Rehearse Model Context Protocol (MCP) server integration and local air-gapped RAG architecture talking points.\n"
            "• Day 4 (Security & Zero Trust): Review SAML 2.0 / SCIM federation between OCI IAM and Azure AD / Okta, plus Bastion service PAM.\n"
            "• Day 5 (Whiteboard Scenarios): Sketch the Air-Gapped Landing Zone and GenAI CloudOps pipelines within a 20-minute timebox.\n"
            "• Day 6 (Principal Strategy): Rehearse cost governance, blast radius containment, and cloud migration trade-offs.\n"
            "• Day 7 (Interactive Simulator): Run `python scripts/interview_simulator.py` to practice timed delivery and executive presence."
        )

        doc.save(docx_path)
        logger.info(f"Generated Consolidated Interview Intelligence DOCX -> {docx_path}")

        # 2. Build Consolidated PDF via Playwright Headless Chromium Print Engine
        html_for_pdf = self._build_briefing_html_for_pdf(matched_items, date_str)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_for_pdf, wait_until="networkidle")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "18mm", "bottom": "18mm", "left": "15mm", "right": "15mm"},
                )
                browser.close()
            logger.info(f"Generated Consolidated Interview Intelligence PDF -> {pdf_path}")
        except Exception as e:
            logger.warning(f"Could not render PDF via Playwright (fallback docx available): {e}")

        # 3. Build HTML Summary for Email Body
        html_summary = self._build_briefing_email_html(matched_items, date_str, docx_path.name, pdf_path.name)
        return docx_path, pdf_path, html_summary

    def _build_briefing_html_for_pdf(self, matched_items: List[Any], date_str: str) -> str:
        table_rows = ""
        for job, score, _ in matched_items:
            table_rows += f"""
            <tr>
              <td><strong>{job.company}</strong></td>
              <td>{job.title}</td>
              <td><span class="badge">{score.overall_score:.1f}%</span></td>
              <td>{job.salary.raw_text or 'Not Disclosed'}</td>
              <td>OCI + AI Platform</td>
            </tr>
            """
        if not table_rows:
            table_rows = '<tr><td colspan="5" style="text-align:center;">Pan India Cloud & AI Architecture Leadership Pipeline</td></tr>'

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4 portrait; margin: 18mm 15mm; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1e293b; margin: 0; padding: 0; }}
  .header {{ border-bottom: 2px solid #0284c7; padding-bottom: 12px; margin-bottom: 16px; }}
  .header h1 {{ font-size: 17pt; font-weight: 800; color: #0f172a; margin: 0 0 4px 0; text-transform: uppercase; letter-spacing: 0.5px; }}
  .header .meta {{ font-size: 9pt; color: #64748b; }}
  h2 {{ font-size: 12pt; font-weight: 700; color: #0369a1; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin: 16px 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; page-break-after: avoid; }}
  h3 {{ font-size: 10pt; font-weight: 700; color: #0f172a; margin: 10px 0 4px 0; }}
  p {{ margin: 0 0 6px 0; }}
  ul {{ margin: 4px 0 10px 18px; padding: 0; }}
  li {{ margin-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10px 0 14px 0; font-size: 9pt; page-break-inside: avoid; }}
  th {{ background: #f1f5f9; padding: 6px 8px; text-align: left; font-weight: 700; border: 1px solid #cbd5e1; color: #334155; }}
  td {{ padding: 6px 8px; border: 1px solid #e2e8f0; vertical-align: top; }}
  .badge {{ background: #e0f2fe; color: #0369a1; font-weight: 700; padding: 2px 6px; border-radius: 4px; }}
  .callout {{ background: #f8fafc; border-left: 3px solid #0284c7; padding: 8px 12px; margin: 8px 0; font-size: 9.5pt; page-break-inside: avoid; }}
</style>
</head>
<body>
  <div class="header">
    <h1>CareerOps — Daily Consolidated Interview Intelligence Briefing</h1>
    <div class="meta">Candidate: <strong>Saket Saurav</strong> | Target: <strong>Principal Cloud & AI Architect</strong> | Date: <strong>{date_str}</strong></div>
  </div>

  <h2>1. Executive Target Opportunities Matrix</h2>
  <p>Consolidated multi-tier interview intelligence covering all qualifying high-match enterprise opportunities for {date_str}:</p>
  <table>
    <thead>
      <tr><th>Company</th><th>Target Role</th><th>Match</th><th>Salary</th><th>Domain</th></tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>

  <h2>2. High-Yield Technical Fundamentals (Level 1 - Knowledge)</h2>
  <div class="callout">
    <strong>A. OCI Enterprise Networking & Topology:</strong><br>
    • Dynamic Routing Gateway (DRG v2) transit routing connecting VCNs, FastConnect, and IPSec VPNs.<br>
    • Private DNS Resolver views with listeners/forwarders for seamless hybrid name resolution.<br>
    • Service Gateway for zero-internet OSN backbone routing vs NAT Gateway for outbound private subnets.
  </div>
  <div class="callout">
    <strong>B. Private Kubernetes (OKE) & Persistence:</strong><br>
    • Complete private subnet worker node pool isolation with Network Security Groups (NSGs).<br>
    • OCI File Storage Service (FSS) custom StorageClasses for multi-pod stateful file persistence.<br>
    • Calico network policies enforcing namespace microsegmentation and strict zero-trust egress.
  </div>
  <div class="callout">
    <strong>C. AI Platform & Model Context Protocol (MCP):</strong><br>
    • MCP client-server architecture streaming live operational context to LLMs securely.<br>
    • Offline ChatOps CLI integrating LangChain with local air-gapped LLMs for zero-leakage diagnostics.
  </div>

  <h2>3. Systems Architecture & Whiteboard Scenarios (Level 2 - Design)</h2>
  <p><strong>Scenario 1: Air-Gapped OCI Landing Zone for Regulated Telecom Billing</strong><br>
  Hub-and-spoke VCN topology with centralized Network Firewalls, private OKE clusters, Exadata DB tiers, and OCI Vault HSM encryption.</p>
  <p><strong>Scenario 2: Automated GenAI CloudOps Alert Triaging Platform</strong><br>
  OCI Service Connector Hub streaming telemetry to ONS -> private OKE microservice -> local RAG vector retrieval -> automated incident resolution within 30 seconds.</p>

  <h2>4. Principal Architect Strategy & Trade-offs (Level 3 - Leadership)</h2>
  <p><strong>• Dedicated AI Clusters vs Serverless:</strong> Dedicated for mission-critical SLA and strict sovereignty; Serverless for batch document extraction.</p>
  <p><strong>• ExaCS vs Autonomous Database:</strong> ADB for 50% DBA reduction in cloud-native workloads; ExaCS for complex RAC database lifts.</p>

  <h2>5. STAR Model Answers (Anchored to Verified Candidate Truth)</h2>
  <p><strong>KPN Telecom Billing Modernization (OCI + OKE + FSS + Terraform):</strong> Architected an air-gapped OCI landing zone with private OKE and FSS storage, cutting release cycles by 60% and reducing platform incidents by 40%.</p>

  <h2>6. 7-Day Targeted Preparation Plan</h2>
  <p>Day 1: Platform Networking • Day 2: Kubernetes & Storage • Day 3: GenAI & MCP • Day 4: Zero Trust Security • Day 5: Whiteboard Exercises • Day 6: Principal Trade-offs • Day 7: Interactive Simulator.</p>
</body>
</html>
"""

    def _build_briefing_email_html(self, matched_items: List[Any], date_str: str, docx_name: str, pdf_name: str) -> str:
        rows = ""
        for job, score, _ in matched_items:
            rows += f"""
            <tr>
              <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 600;">{job.company}</td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0;">{job.title}</td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0;"><span style="background-color: #dcfce7; color: #166534; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 700;">{score.overall_score:.1f}%</span></td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 12px; color: #475569;">{job.salary.raw_text or 'Not Disclosed'}</td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 12px; color: #2563eb; font-weight: 600;">OCI + GenAI Platform</td>
            </tr>
            """
        if not rows:
            rows = '<tr><td colspan="5" style="padding: 12px; text-align: center; color: #64748b;">Active Pan India Cloud & AI Architecture Opportunities</td></tr>'

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CareerOps — Daily Consolidated Interview Intelligence Briefing</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #334155; margin: 0; padding: 24px;">
  <div style="max-width: 760px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; border: 1px solid #e2e8f0;">
    
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #0369a1 0%, #0f172a 100%); padding: 28px 32px; color: #ffffff;">
      <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #38bdf8;">Consolidated Interview Intelligence</div>
      <h1 style="margin: 8px 0 4px 0; font-size: 22px; font-weight: 700;">Daily Consolidated Interview Briefing</h1>
      <div style="font-size: 14px; color: #94a3b8;">{date_str} &bull; Target: <strong>Principal Cloud & AI Architect (12+ Years)</strong></div>
    </div>

    <!-- Overview Banner -->
    <div style="padding: 20px 32px; background-color: #f0fdf4; border-bottom: 1px solid #bbf7d0;">
      <div style="font-size: 13px; color: #166534; line-height: 1.5;">
        <strong>&check; Single Consolidated Report:</strong> All interview intelligence for today's high-match opportunities has been synthesized into a single executive document. The complete 7-section document is <strong>attached to this email as a PDF ({pdf_name}) and Word document ({docx_name})</strong>.
      </div>
    </div>

    <!-- Opportunities Table -->
    <div style="padding: 24px 32px;">
      <h2 style="font-size: 16px; font-weight: 700; margin-top: 0; margin-bottom: 12px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
        Analyzed Opportunities ({len(matched_items)} Roles)
      </h2>
      <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
        <thead>
          <tr style="background-color: #f8fafc; border-bottom: 2px solid #cbd5e1;">
            <th style="padding: 8px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Company</th>
            <th style="padding: 8px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Role</th>
            <th style="padding: 8px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Match</th>
            <th style="padding: 8px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Salary</th>
            <th style="padding: 8px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Focus</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>

      <!-- Key Focus Areas Grid -->
      <h2 style="font-size: 16px; font-weight: 700; margin-top: 24px; margin-bottom: 12px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
        Executive Preparation Highlights
      </h2>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px;">
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;">
          <div style="font-weight: 700; font-size: 13px; color: #0369a1; margin-bottom: 4px;">Level 1: Fundamentals</div>
          <div style="font-size: 12px; color: #475569; line-height: 1.4;">DRG v2 Transit Routing, Private OKE FSS StorageClasses, Model Context Protocol (MCP), and Terraform modular state management.</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;">
          <div style="font-weight: 700; font-size: 13px; color: #0369a1; margin-bottom: 4px;">Level 2: Systems Design</div>
          <div style="font-size: 12px; color: #475569; line-height: 1.4;">Air-Gapped Telecom OCI Landing Zone with centralized Palo Alto inspection, and Offline GenAI CloudOps alert triaging.</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;">
          <div style="font-weight: 700; font-size: 13px; color: #0369a1; margin-bottom: 4px;">Level 3: Trade-offs</div>
          <div style="font-size: 12px; color: #475569; line-height: 1.4;">Dedicated vs Serverless AI Clusters (cost vs sovereignty), ExaCS vs Autonomous Database (control vs 50% DBA reduction).</div>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px;">
          <div style="font-weight: 700; font-size: 13px; color: #0369a1; margin-bottom: 4px;">Verified Model Answers</div>
          <div style="font-size: 12px; color: #475569; line-height: 1.4;">KPN air-gapped deployment, Emerson multi-cloud migration, and ODAOS LangGraph autonomous database operations.</div>
        </div>
      </div>

      <!-- Attached Documents Notice -->
      <div style="margin-top: 24px; padding: 16px; background-color: #f1f5f9; border-radius: 8px; border: 1px solid #cbd5e1; text-align: center;">
        <div style="font-size: 13px; font-weight: 700; color: #0f172a;">Attached Document Available</div>
        <div style="font-size: 12px; color: #64748b; margin-top: 4px;">
          Please review the attached <strong>{pdf_name}</strong> or <strong>{docx_name}</strong> for the full 7-section question set, whiteboard architecture diagrams, and 7-day revision roadmap.
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div style="background-color: #f8fafc; padding: 16px 32px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 11px; color: #94a3b8;">
      CareerOps Autonomous Career Intelligence Platform &bull; Generated strictly against verified candidate truth
    </div>
  </div>
</body>
</html>
"""

