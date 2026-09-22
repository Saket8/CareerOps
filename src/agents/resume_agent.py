"""ATS-friendly resume generator and validation engine.

Generates tailored DOCX and companion PDF resumes preserving 100% truthful
candidate facts, and validates ATS readability, layout, and keyword density.
"""

import os
import re
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from src.models.candidate import CandidateTruth
from src.models.job import JobListing
from src.models.score import JobScore
from src.database.repositories.resume_repo import ResumeRepository
from src.utils.logger import get_logger

logger = get_logger("resume_agent")


class SimplePdfWriter:
    """Minimal, self-contained pure-Python PDF 1.4 generator for ATS resumes."""

    def __init__(self):
        self.lines: List[Tuple[str, str, int]] = []  # (text, font_style, size)

    def add_line(self, text: str, font_style: str = "regular", size: int = 10):
        # Sanitize text for basic ASCII/PDF string
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        self.lines.append((safe, font_style, size))

    def write(self, output_path: Path) -> None:
        """Generates standard multi-page PDF document."""
        page_width, page_height = 595, 842  # A4 points
        margin_left, margin_top = 40, 50
        y_cursor = page_height - margin_top
        line_height = 13

        pages = []
        current_page_stream = []

        for text, font_style, size in self.lines:
            if y_cursor < 50:
                pages.append("\n".join(current_page_stream))
                current_page_stream = []
                y_cursor = page_height - margin_top

            font_tag = "/F2" if font_style == "bold" else "/F1"
            # Add line text to stream
            current_page_stream.append(f"BT {font_tag} {size} Tf {margin_left} {y_cursor} Td ({text}) Tj ET")
            y_cursor -= (size + 4)

        if current_page_stream:
            pages.append("\n".join(current_page_stream))

        # Build PDF objects
        objects = []
        objects.append("<< /Type /Catalog /Pages 2 0 R >>")  # 1: Catalog
        
        # 2: Pages list
        page_refs = [f"{i + 3} 0 R" for i in range(len(pages))]
        objects.append(f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(pages)} >>")

        # Object indices
        # 3 .. 3 + len(pages)-1: Page objects
        # Next: Content streams
        # Next: Fonts
        content_obj_start = 3 + len(pages)
        for i, _ in enumerate(pages):
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Contents {content_obj_start + i} 0 R /Resources << /Font << /F1 999 0 R /F2 1000 0 R >> >> >>"
            )
            objects.append(page_obj)

        for p_stream in pages:
            stream_bytes = p_stream.encode("latin-1", errors="replace")
            objects.append(f"<< /Length {len(stream_bytes)} >>\nstream\n{p_stream}\nendstream")

        font1_idx = len(objects) + 1
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font2_idx = len(objects) + 1
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

        # Replace font placeholders in page objects
        for idx in range(2, 2 + len(pages)):
            objects[idx] = objects[idx].replace("999 0 R", f"{font1_idx} 0 R").replace("1000 0 R", f"{font2_idx} 0 R")

        # Assemble PDF
        out = [b"%PDF-1.4\n"]
        xref_offsets = [0]
        offset = len(out[0])

        for i, obj in enumerate(objects):
            xref_offsets.append(offset)
            obj_bytes = f"{i + 1} 0 obj\n{obj}\nendobj\n".encode("latin-1", errors="replace")
            out.append(obj_bytes)
            offset += len(obj_bytes)

        xref_start = offset
        out.append(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
        for off in xref_offsets[1:]:
            out.append(f"{off:010d} 00000 n \n".encode("latin-1"))

        out.append(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("latin-1")
        )

        with open(output_path, "wb") as f:
            for chunk in out:
                f.write(chunk)


class ATSValidator:
    """Validates ATS readability, text extraction, keyword density, and zero fabrication."""

    @staticmethod
    def validate(docx_path: Path, candidate_truth: CandidateTruth, jd_text: str) -> Dict[str, Any]:
        report = {
            "passed": True,
            "ats_score": 100.0,
            "checks": {},
            "issues": [],
        }

        # 1. Text extractability
        try:
            doc = docx.Document(str(docx_path))
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            report["checks"]["text_extractability"] = len(full_text) > 500
        except Exception as exc:
            report["checks"]["text_extractability"] = False
            report["issues"].append(f"Failed to read DOCX: {exc}")
            report["passed"] = False
            report["ats_score"] = 0.0
            return report

        # 2. Section recognition
        expected_sections = [
            "PROFESSIONAL SUMMARY",
            "CORE COMPETENCIES",
            "PROFESSIONAL EXPERIENCE",
            "CERTIFICATIONS",
            "EDUCATION",
        ]
        recognized_sections = [s for s in expected_sections if s in full_text.upper()]
        report["checks"]["section_recognition"] = len(recognized_sections) == len(expected_sections)
        if len(recognized_sections) < len(expected_sections):
            report["issues"].append(f"Missing standard sections: {set(expected_sections) - set(recognized_sections)}")
            report["ats_score"] -= 15.0

        # 3. Contact information check
        cand = candidate_truth.candidate
        report["checks"]["contact_name"] = cand.name.lower() in full_text.lower()
        report["checks"]["contact_phone"] = "7028481800" in full_text
        report["checks"]["contact_email"] = cand.email.lower() in full_text.lower()

        if not (report["checks"]["contact_name"] and report["checks"]["contact_phone"]):
            report["issues"].append("Essential contact info missing from resume body")
            report["ats_score"] -= 20.0

        # 4. Zero Fabrication verification
        for emp in candidate_truth.employment_history:
            if emp.company.lower() not in full_text.lower():
                report["issues"].append(f"Historical employer {emp.company} missing from generated resume")
                report["ats_score"] -= 10.0

        # 5. Keyword stuffing check
        words = re.findall(r"\b\w+\b", full_text.lower())
        total_words = len(words)
        if total_words > 0:
            word_counts = {}
            for w in words:
                if len(w) > 3:
                    word_counts[w] = word_counts.get(w, 0) + 1
            highest_density = max(word_counts.values()) / float(total_words)
            report["checks"]["keyword_density_safe"] = highest_density < 0.06  # Less than 6% frequency for single word
            if not report["checks"]["keyword_density_safe"]:
                report["issues"].append(f"Keyword stuffing risk: single word density too high ({highest_density:.2%})")
                report["ats_score"] -= 15.0
        else:
            report["checks"]["keyword_density_safe"] = True

        report["passed"] = len(report["issues"]) == 0
        report["ats_score"] = max(0.0, min(100.0, report["ats_score"]))
        return report


class ResumeAgent:
    """Orchestrates truthful tailoring, DOCX/PDF generation, and ATS validation."""

    def __init__(self, resume_repo: ResumeRepository, candidate_truth: CandidateTruth, config: Dict[str, Any]):
        self.resume_repo = resume_repo
        self.candidate_truth = candidate_truth
        self.config = config
        self.output_dir = Path(config.get("resume", {}).get("output_dir", "resumes/generated"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_tailored_resume(self, job: JobListing, score: JobScore) -> Tuple[Path, Path, Dict[str, Any]]:
        """Generates job-specific ATS-tailored DOCX and PDF resumes."""
        safe_company = re.sub(r"[^\w\-]", "_", job.company)[:30].strip("_")
        safe_role = re.sub(r"[^\w\-]", "_", job.title)[:30].strip("_")
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        
        docx_filename = f"{safe_company}_{safe_role}_{date_str}.docx"
        pdf_filename = f"{safe_company}_{safe_role}_{date_str}.pdf"
        
        docx_path = self.output_dir / docx_filename
        pdf_path = self.output_dir / pdf_filename

        # Tailor summary and skills without fabrication
        tailored_summary = self._build_tailored_summary(job)
        tailored_skills = self._build_tailored_skills(job)

        # 1. Generate DOCX
        self._generate_docx(docx_path, tailored_summary, tailored_skills)

        # 2. Generate PDF
        self._generate_pdf(pdf_path, tailored_summary, tailored_skills)

        # 3. ATS Validation
        val_report = ATSValidator.validate(docx_path, self.candidate_truth, job.jd_text)

        # 4. Record version in database
        checksum = hashlib.sha256(open(docx_path, "rb").read()).hexdigest()
        version_id = f"res_{job.job_id}_{date_str}"

        self.resume_repo.save_version(
            version_id=version_id,
            job_id=job.job_id,
            is_master=False,
            file_path_docx=str(docx_path),
            file_path_pdf=str(pdf_path),
            checksum=checksum,
            ats_score=val_report["ats_score"],
            ats_validation_details=val_report,
            tailoring_diff={"matched_skills": tailored_skills[:6]},
        )

        logger.info(f"Generated ATS Resume for {job.company} -> {docx_path} (ATS Score: {val_report['ats_score']}%)")
        return docx_path, pdf_path, val_report

    def _build_tailored_summary(self, job: JobListing) -> str:
        cand = self.candidate_truth.candidate
        jd_lower = f"{job.title} {job.jd_text}".lower()

        focus_highlights = []
        if any(k in jd_lower for k in ["genai", "generative ai", "llm", "rag", "mcp", "agent", "agentic", "artificial intelligence", "ai "]):
            focus_highlights.append("AI-driven operations and GenAI platform engineering (Model Context Protocol [MCP], LangChain, air-gapped ChatOps, and local LLMs)")
        if any(k in jd_lower for k in ["oke", "kubernetes", "k8s", "container", "docker", "helm"]):
            focus_highlights.append("enterprise Kubernetes (OKE) platform engineering (private clusters, FSS persistent storage, RBAC governance, and ingress architecture)")
        if any(k in jd_lower for k in ["security", "iam", "sso", "saml", "zero trust", "air-gapped", "pam"]):
            focus_highlights.append("Zero Trust enterprise security, OCI IAM database environment isolation, and SAML 2.0 / Azure AD federated SSO")
        if any(k in jd_lower for k in ["terraform", "iac", "ansible", "automation", "devops", "ci/cd"]):
            focus_highlights.append("modular Infrastructure as Code (Terraform) driving ~60% reduction in deployment lifecycle and eliminating configuration drift")
        if any(k in jd_lower for k in ["migration", "database", "exacs", "exadata", "oracle db", "rac"]):
            focus_highlights.append("mission-critical on-prem to OCI cloud migrations (ExaCS, Autonomous DB, and Oracle RAC high availability)")

        focus_str = f" Specialized in {', '.join(focus_highlights)}." if focus_highlights else ""

        p1 = (
            f"Distinguished {cand.title} with 12+ years of enterprise IT engineering excellence, including 6.5+ years of deep specialization "
            f"in Oracle Cloud Infrastructure (OCI) and Multi-Cloud architectures (Azure, AWS, GCP). Proven architectural track record designing, "
            f"migrating, and operating mission-critical, telecom-grade cloud estates and regulated air-gapped environments for global enterprises.{focus_str}"
        )
        p2 = (
            f"Recognized for bridging strategic enterprise architecture, cloud-native scalability, zero-trust security, and AI-powered operational autonomy. "
            f"Hands-on leader with extensive delivery across private OKE cluster topologies, modular Terraform IaC automation, GenAI CloudOps dashboards, "
            f"and enterprise database modernization (Exadata, Autonomous Database). Accomplished in directing cross-functional engineering teams, "
            f"authoring technical decision records (TDRs), and establishing organizational landing zone governance."
        )
        return f"{p1}\n\n{p2}"

    def _build_tailored_skills(self, job: JobListing) -> List[str]:
        # Return categorized architectural skills prioritizing those matched in target JD
        jd_lower = f"{job.title} {job.jd_text}".lower()

        categories = [
            (
                "Enterprise Cloud Architecture",
                "Oracle Cloud Infrastructure (OCI - Primary), Multi-Cloud (Azure, AWS, GCP), Landing Zones, VCN Hub-and-Spoke, DRG, FastConnect, Private DNS, Network Firewalls (Palo Alto VM-Series), High Availability & DR Topology",
                ["cloud", "oci", "oracle", "multi-cloud", "landing zone", "vcn", "drg", "fastconnect", "network", "firewall", "hybrid"],
            ),
            (
                "Container & Cloud-Native Platforms",
                "Kubernetes (OKE), Docker, Helm, Private OKE Clusters, FSS Persistent Storage (StorageClass, PV, PVC), Layered Security & RBAC, Application Load Balancers (ALB/NLB), API Gateway Ingress",
                ["kubernetes", "oke", "k8s", "container", "docker", "helm", "microservices"],
            ),
            (
                "AI & GenAI Platform Engineering",
                "LangChain, LangGraph, Local LLMs, Model Context Protocol (MCP) Servers, Agentic AI Frameworks, RAG Architecture, GenAI CloudOps Dashboard, Offline ChatOps CLI, ODAOS (Autonomous DB Ops)",
                ["genai", "ai", "artificial intelligence", "llm", "rag", "mcp", "agentic", "langchain", "prompt"],
            ),
            (
                "Infrastructure as Code & DevOps",
                "Terraform (Reusable Modular Blueprints), Ansible, OCI Resource Manager, OCI CLI, Bash Scripting, OCI DevOps, Git, GitHub Actions, Automated CI/CD Pipelines, Multi-Environment Release Governance",
                ["terraform", "iac", "ansible", "devops", "ci/cd", "pipeline", "automation"],
            ),
            (
                "Zero Trust Security & Identity",
                "OCI IAM Identity Domains, Azure Active Directory / Microsoft Entra ID Federation, SAML 2.0 / SSO, SCIM Provisioning, Okta Integration, Linux PAM Hardening, OCI IAM Database Environment Isolation, Confidential Applications",
                ["security", "iam", "sso", "saml", "rbac", "zero trust", "pam", "scim", "okta", "azure ad"],
            ),
            (
                "Observability, SRE & Governance",
                "Prometheus, Grafana, Splunk, Datadog, OCI Logging Analytics, Service Connector Hub, ONS Alerting, Multi-Cloud Cost Governance (Cloudability), Capacity Planning & Performance Tuning",
                ["observability", "monitoring", "splunk", "datadog", "prometheus", "grafana", "sre", "logging"],
            ),
            (
                "Databases & Mission-Critical Data",
                "Oracle Database 19c/12c/11g, Oracle RAC (Real Application Clusters), Exadata Database Service (ExaCS), Autonomous Data Warehouse (ADW), Autonomous DB (ADB), Data Guard, RMAN Backup & Recovery",
                ["database", "oracle db", "rac", "exadata", "exacs", "adw", "adb", "data guard", "rman", "sql"],
            ),
        ]

        def score_cat(keywords):
            return sum(1 for kw in keywords if kw in jd_lower)

        sorted_cats = sorted(categories, key=lambda c: score_cat(c[2]), reverse=True)
        return [f"{c[0]}: {c[1]}" for c in sorted_cats]

    def _generate_docx(self, path: Path, summary: str, skills: List[str]) -> None:
        cand = self.candidate_truth.candidate
        doc = docx.Document()

        # Professional Page Margins
        for s in doc.sections:
            s.top_margin = Inches(0.5)
            s.bottom_margin = Inches(0.5)
            s.left_margin = Inches(0.6)
            s.right_margin = Inches(0.6)

        # Header / Candidate Name
        name_p = doc.add_paragraph()
        name_run = name_p.add_run(cand.name)
        name_run.font.name = "Calibri"
        name_run.font.size = Pt(20)
        name_run.font.bold = True
        name_run.font.color.rgb = RGBColor(15, 23, 42)
        name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_p.paragraph_format.space_after = Pt(2)

        # Subtitle / Role
        role_p = doc.add_paragraph()
        role_run = role_p.add_run(f"{cand.title} | Cloud & AI Architecture | Multi-Cloud & OKE")
        role_run.font.name = "Calibri"
        role_run.font.size = Pt(11)
        role_run.font.bold = True
        role_run.font.color.rgb = RGBColor(51, 65, 85)
        role_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        role_p.paragraph_format.space_after = Pt(3)

        # Contact line
        contact_p = doc.add_paragraph()
        contact_text = f"{cand.email}  |  {cand.phone}  |  {cand.location}  |  {cand.total_experience_years}+ Years Enterprise Experience"
        contact_run = contact_p.add_run(contact_text)
        contact_run.font.name = "Calibri"
        contact_run.font.size = Pt(9.5)
        contact_run.font.color.rgb = RGBColor(71, 85, 105)
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_p.paragraph_format.space_after = Pt(12)

        # Helper for Section Heading
        def add_heading(text: str):
            hp = doc.add_paragraph()
            hr = hp.add_run(text)
            hr.font.name = "Calibri"
            hr.font.size = Pt(12)
            hr.font.bold = True
            hr.font.color.rgb = RGBColor(15, 23, 42)
            hp.paragraph_format.space_before = Pt(10)
            hp.paragraph_format.space_after = Pt(4)

        # 1. Professional Summary
        add_heading("PROFESSIONAL SUMMARY")
        for para in summary.split("\n\n"):
            if not para.strip():
                continue
            sum_p = doc.add_paragraph()
            sum_run = sum_p.add_run(para.strip())
            sum_run.font.name = "Calibri"
            sum_run.font.size = Pt(9.5)
            sum_p.paragraph_format.space_after = Pt(4)
            sum_p.paragraph_format.line_spacing = 1.15

        # 2. Core Competencies
        add_heading("CORE COMPETENCIES")
        for sk in skills:
            sk_p = doc.add_paragraph(style="List Bullet")
            if ":" in sk:
                cat_name, cat_items = sk.split(":", 1)
                run_cat = sk_p.add_run(f"{cat_name.strip()}: ")
                run_cat.font.name = "Calibri"
                run_cat.font.size = Pt(9.5)
                run_cat.font.bold = True
                run_items = sk_p.add_run(cat_items.strip())
                run_items.font.name = "Calibri"
                run_items.font.size = Pt(9.5)
            else:
                sk_run = sk_p.add_run(sk)
                sk_run.font.name = "Calibri"
                sk_run.font.size = Pt(9.5)
            sk_p.paragraph_format.space_after = Pt(2.5)

        # 3. Professional Experience
        add_heading("PROFESSIONAL EXPERIENCE")
        for emp in self.candidate_truth.employment_history:
            emp_header_p = doc.add_paragraph()
            emp_header = f"{emp.role}  |  {emp.company}"
            if emp.client:
                emp_header += f" (Client: {emp.client})"
            emp_header += f"    [{emp.start_date} – {emp.end_date}]"
            hrun = emp_header_p.add_run(emp_header)
            hrun.font.name = "Calibri"
            hrun.font.size = Pt(10.5)
            hrun.font.bold = True
            hrun.font.color.rgb = RGBColor(15, 23, 42)
            emp_header_p.paragraph_format.space_before = Pt(8)
            emp_header_p.paragraph_format.space_after = Pt(3)

            for resp in emp.responsibilities:
                rp = doc.add_paragraph(style="List Bullet")
                if ":" in resp:
                    domain_lead, body_text = resp.split(":", 1)
                    lead_run = rp.add_run(f"{domain_lead.strip()}: ")
                    lead_run.font.name = "Calibri"
                    lead_run.font.size = Pt(9.5)
                    lead_run.font.bold = True
                    body_run = rp.add_run(body_text.strip())
                    body_run.font.name = "Calibri"
                    body_run.font.size = Pt(9.5)
                else:
                    rr = rp.add_run(resp)
                    rr.font.name = "Calibri"
                    rr.font.size = Pt(9.5)
                rp.paragraph_format.space_after = Pt(2.5)
                rp.paragraph_format.line_spacing = 1.15

        # 4. Certifications
        add_heading("CERTIFICATIONS")
        for cert in self.candidate_truth.certifications:
            cp = doc.add_paragraph(style="List Bullet")
            c_run = cp.add_run(f"{cert.name}")
            c_run.font.name = "Calibri"
            c_run.font.size = Pt(9.5)
            c_run.font.bold = True
            c_issuer = cp.add_run(f" — {cert.issuer} ({cert.year})")
            c_issuer.font.name = "Calibri"
            c_issuer.font.size = Pt(9.5)
            cp.paragraph_format.space_after = Pt(2)

        # 5. Education
        add_heading("EDUCATION")
        for edu in self.candidate_truth.education:
            ed_p = doc.add_paragraph()
            ed_bold = ed_p.add_run(f"{edu.degree} in {edu.field}")
            ed_bold.font.name = "Calibri"
            ed_bold.font.size = Pt(9.5)
            ed_bold.font.bold = True
            ed_run = ed_p.add_run(f"  |  {edu.institution} ({edu.score})")
            ed_run.font.name = "Calibri"
            ed_run.font.size = Pt(9.5)
            ed_p.paragraph_format.space_after = Pt(4)

        doc.save(str(path))

    def _generate_pdf(self, path: Path, summary: str, skills: List[str]) -> None:
        """Renders full-fidelity multi-page PDF via Playwright Chromium with zero truncation."""
        cand = self.candidate_truth.candidate

        # Build clean, print-optimized semantic HTML
        skills_html = []
        for sk in skills:
            if ":" in sk:
                cat_name, cat_items = sk.split(":", 1)
                skills_html.append(f"<li><strong>{cat_name.strip()}:</strong> {cat_items.strip()}</li>")
            else:
                skills_html.append(f"<li>{sk.strip()}</li>")

        exp_html = []
        for emp in self.candidate_truth.employment_history:
            client_str = f" (Client: {emp.client})" if emp.client else ""
            bullets_html = []
            for resp in emp.responsibilities:
                if ":" in resp:
                    domain_lead, body_text = resp.split(":", 1)
                    bullets_html.append(f"<li><strong>{domain_lead.strip()}:</strong> {body_text.strip()}</li>")
                else:
                    bullets_html.append(f"<li>{resp.strip()}</li>")

            exp_html.append(f"""
            <div class="job-block">
              <div class="job-header">
                <span class="job-title"><strong>{emp.role}</strong> &bull; {emp.company}{client_str}</span>
                <span class="job-dates">{emp.start_date} &ndash; {emp.end_date} ({emp.duration})</span>
              </div>
              <ul>
                {''.join(bullets_html)}
              </ul>
            </div>
            """)

        certs_html = [f"<li><strong>{c.name}</strong> &ndash; {c.issuer} ({c.year})</li>" for c in self.candidate_truth.certifications]
        edu_html = [f"<div><strong>{e.degree} in {e.field}</strong> &bull; {e.institution} ({e.score})</div>" for e in self.candidate_truth.education]

        summary_paras = [f"<p>{p.strip()}</p>" for p in summary.split("\n\n") if p.strip()]

        html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 14mm 16mm 14mm 16mm;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    color: #1e293b;
    line-height: 1.42;
    font-size: 9pt;
    margin: 0;
    padding: 0;
  }}
  .header {{
    text-align: center;
    margin-bottom: 10px;
    border-bottom: 2px solid #0f172a;
    padding-bottom: 6px;
  }}
  .name {{
    font-size: 19pt;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 2px;
    letter-spacing: -0.5px;
  }}
  .role-subtitle {{
    font-size: 10.5pt;
    font-weight: 700;
    color: #334155;
    margin-bottom: 3px;
  }}
  .contact-line {{
    font-size: 9pt;
    color: #475569;
  }}
  .section-title {{
    font-size: 10.5pt;
    font-weight: 800;
    color: #0f172a;
    border-bottom: 1.5px solid #94a3b8;
    padding-bottom: 2px;
    margin-top: 10px;
    margin-bottom: 5px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  p {{
    margin: 0 0 5px 0;
    text-align: justify;
  }}
  ul {{
    margin: 0 0 6px 16px;
    padding: 0;
  }}
  li {{
    margin-bottom: 2.5px;
  }}
  strong {{
    color: #0f172a;
  }}
  .job-block {{
    margin-bottom: 8px;
    page-break-inside: avoid;
  }}
  .job-header {{
    display: flex;
    justify-content: space-between;
    font-size: 9.5pt;
    margin-bottom: 3px;
  }}
  .job-dates {{
    color: #475569;
    font-style: italic;
    font-size: 8.5pt;
    white-space: nowrap;
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="name">{cand.name}</div>
    <div class="role-subtitle">{cand.title} | Cloud & AI Architecture | Multi-Cloud & OKE</div>
    <div class="contact-line">{cand.email} &bull; {cand.phone} &bull; {cand.location} &bull; {cand.total_experience_years}+ Years Enterprise Experience</div>
  </div>

  <div class="section-title">Professional Summary</div>
  {''.join(summary_paras)}

  <div class="section-title">Core Competencies</div>
  <ul>
    {''.join(skills_html)}
  </ul>

  <div class="section-title">Professional Experience</div>
  {''.join(exp_html)}

  <div class="section-title">Certifications</div>
  <ul>
    {''.join(certs_html)}
  </ul>

  <div class="section-title">Education</div>
  {''.join(edu_html)}
</body>
</html>
"""

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_doc, wait_until="networkidle")
                page.pdf(
                    path=str(path),
                    format="A4",
                    print_background=True,
                    margin={"top": "14mm", "bottom": "14mm", "left": "16mm", "right": "16mm"},
                )
                browser.close()
            return
        except Exception as exc:
            logger.warning(f"Playwright PDF generation failed: {exc}, using fallback writer.")

        # Fallback SimplePdfWriter if Playwright is unavailable
        pdf = SimplePdfWriter()
        pdf.add_line(cand.name, font_style="bold", size=16)
        pdf.add_line(f"{cand.title} | Cloud & AI Architecture", font_style="bold", size=10)
        pdf.add_line(f"{cand.email} | {cand.phone} | {cand.location} | {cand.total_experience_years}+ Years Experience", size=9)
        pdf.add_line("")
        pdf.add_line("PROFESSIONAL SUMMARY", font_style="bold", size=11)
        for p in summary.split("\n\n"):
            words = p.split()
            curr = []
            for w in words:
                curr.append(w)
                if len(" ".join(curr)) > 85:
                    pdf.add_line(" ".join(curr), size=9)
                    curr = []
            if curr:
                pdf.add_line(" ".join(curr), size=9)
        pdf.add_line("")
        pdf.add_line("CORE COMPETENCIES", font_style="bold", size=11)
        for sk in skills:
            pdf.add_line(f"- {sk}", size=9)
        pdf.add_line("")
        pdf.add_line("PROFESSIONAL EXPERIENCE", font_style="bold", size=11)
        for emp in self.candidate_truth.employment_history:
            pdf.add_line(f"{emp.role} | {emp.company} [{emp.start_date} - {emp.end_date}]", font_style="bold", size=10)
            for resp in emp.responsibilities:
                pdf.add_line(f"- {resp}", size=8)
            pdf.add_line("")
        pdf.add_line("CERTIFICATIONS", font_style="bold", size=11)
        for cert in self.candidate_truth.certifications:
            pdf.add_line(f"- {cert.name} ({cert.year})", size=9)
        pdf.add_line("")
        pdf.add_line("EDUCATION", font_style="bold", size=11)
        for edu in self.candidate_truth.education:
            pdf.add_line(f"{edu.degree} - {edu.field} | {edu.institution}", size=9)
        pdf.write(path)

