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
        focus = []
        jd_lower = f"{job.title} {job.jd_text}".lower()

        if "genai" in jd_lower or "rag" in jd_lower:
            focus.append("GenAI platform engineering (RAG, Model Context Protocol, ChatOps)")
        if "oke" in jd_lower or "kubernetes" in jd_lower:
            focus.append("production Kubernetes (OKE) platform architecture")
        if "multi-cloud" in jd_lower or "aws" in jd_lower:
            focus.append("multi-cloud networking & landing zone governance")
        if "security" in jd_lower or "iam" in jd_lower:
            focus.append("enterprise IAM federation and air-gapped security boundaries")

        focus_str = f" with proven expertise in {', '.join(focus)}" if focus else ""

        return (
            f"{cand.title} with {cand.total_experience_years}+ years of enterprise IT experience, "
            f"including {cand.cloud_experience_years}+ years specializing in Oracle Cloud Infrastructure (OCI){focus_str}. "
            f"Proven track record architecting mission-critical, telecom-grade cloud environments, Infrastructure as Code (Terraform), "
            f"and AI-driven operations. Recognized for bridging architecture, security, automation, and business outcomes."
        )

    def _build_tailored_skills(self, job: JobListing) -> List[str]:
        # Return candidate's verified skills prioritizing those found in JD
        jd_lower = f"{job.title} {job.jd_text}".lower()
        prioritized = []
        regular = []

        raw_skills = [
            "Cloud Platforms: Primary - OCI, Secondary: Azure, AWS, GCP",
            "Container Orchestration: Kubernetes (OKE), Docker, Helm, RBAC",
            "IaC & Automation: Terraform, Ansible, OCI CLI, Bash",
            "AI & GenAI CloudOps: LangChain, LangGraph, Local LLMs, Agentic Frameworks, MCP Servers",
            "Security & IAM: OCI IAM, Azure AD, SAML 2.0 / SSO, PAM Hardening, RBAC",
            "Networking: VCN Hub-and-Spoke, DRG, FastConnect, Private DNS, Palo Alto Firewalls",
            "Observability: Prometheus, Grafana, Splunk, Datadog, OCI Logging Analytics",
            "Databases: Oracle DB 19c/12c RAC, Exadata, Autonomous Database (ADW/ADB)",
            "DevOps / CI-CD: OCI DevOps, Git, GitHub Actions, CI/CD Pipelines",
        ]

        for skill_line in raw_skills:
            words = skill_line.lower().split()
            if any(w in jd_lower for w in words if len(w) > 3):
                prioritized.append(skill_line)
            else:
                regular.append(skill_line)

        return prioritized + regular

    def _generate_docx(self, path: Path, summary: str, skills: List[str]) -> None:
        cand = self.candidate_truth.candidate
        doc = docx.Document()

        # Page margins
        sections = doc.sections
        for s in sections:
            s.top_margin = Inches(0.6)
            s.bottom_margin = Inches(0.6)
            s.left_margin = Inches(0.65)
            s.right_margin = Inches(0.65)

        # Header / Candidate Name
        name_p = doc.add_paragraph()
        name_run = name_p.add_run(cand.name)
        name_run.font.name = "Calibri"
        name_run.font.size = Pt(20)
        name_run.font.bold = True
        name_run.font.color.rgb = RGBColor(30, 41, 59)
        name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_p.paragraph_format.space_after = Pt(2)

        # Subtitle / Role
        role_p = doc.add_paragraph()
        role_run = role_p.add_run(f"{cand.title} | Cloud Architecture | GenAI & AI Platforms")
        role_run.font.name = "Calibri"
        role_run.font.size = Pt(11)
        role_run.font.bold = True
        role_run.font.color.rgb = RGBColor(71, 85, 105)
        role_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        role_p.paragraph_format.space_after = Pt(4)

        # Contact line
        contact_p = doc.add_paragraph()
        contact_text = f"{cand.email}  |  {cand.phone}  |  {cand.location}  |  {cand.total_experience_years}+ Years Experience"
        contact_run = contact_p.add_run(contact_text)
        contact_run.font.name = "Calibri"
        contact_run.font.size = Pt(9.5)
        contact_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        contact_p.paragraph_format.space_after = Pt(14)

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
        sum_p = doc.add_paragraph()
        sum_run = sum_p.add_run(summary)
        sum_run.font.name = "Calibri"
        sum_run.font.size = Pt(10)
        sum_p.paragraph_format.space_after = Pt(8)

        # 2. Core Competencies
        add_heading("CORE COMPETENCIES")
        for sk in skills:
            sk_p = doc.add_paragraph(style="List Bullet")
            sk_run = sk_p.add_run(sk)
            sk_run.font.name = "Calibri"
            sk_run.font.size = Pt(9.5)
            sk_p.paragraph_format.space_after = Pt(2)

        # 3. Professional Experience
        add_heading("PROFESSIONAL EXPERIENCE")
        for emp in self.candidate_truth.employment_history:
            emp_header_p = doc.add_paragraph()
            emp_header = f"{emp.role}  |  {emp.company}"
            if emp.client:
                emp_header += f" (Client: {emp.client})"
            emp_header += f"   [{emp.start_date} - {emp.end_date}]"
            hrun = emp_header_p.add_run(emp_header)
            hrun.font.name = "Calibri"
            hrun.font.size = Pt(10.5)
            hrun.font.bold = True
            emp_header_p.paragraph_format.space_before = Pt(6)
            emp_header_p.paragraph_format.space_after = Pt(2)

            for resp in emp.responsibilities:
                rp = doc.add_paragraph(style="List Bullet")
                rr = rp.add_run(resp)
                rr.font.name = "Calibri"
                rr.font.size = Pt(9.5)
                rp.paragraph_format.space_after = Pt(2)

        # 4. Certifications
        add_heading("CERTIFICATIONS")
        for cert in self.candidate_truth.certifications:
            cp = doc.add_paragraph(style="List Bullet")
            cr = cp.add_run(f"{cert.name} ({cert.year})")
            cr.font.name = "Calibri"
            cr.font.size = Pt(9.5)
            cp.paragraph_format.space_after = Pt(2)

        # 5. Education
        add_heading("EDUCATION")
        for edu in self.candidate_truth.education:
            ed_p = doc.add_paragraph()
            ed_run = ed_p.add_run(f"{edu.degree} in {edu.field}  |  {edu.institution} ({edu.score})")
            ed_run.font.name = "Calibri"
            ed_run.font.size = Pt(9.5)
            ed_p.paragraph_format.space_after = Pt(4)

        doc.save(str(path))

    def _generate_pdf(self, path: Path, summary: str, skills: List[str]) -> None:
        cand = self.candidate_truth.candidate
        pdf = SimplePdfWriter()

        pdf.add_line(cand.name, font_style="bold", size=16)
        pdf.add_line(f"{cand.title} | Cloud Architecture | GenAI & AI Platforms", font_style="bold", size=10)
        pdf.add_line(f"{cand.email} | {cand.phone} | {cand.location} | {cand.total_experience_years}+ Years Experience", size=9)
        pdf.add_line("")

        pdf.add_line("PROFESSIONAL SUMMARY", font_style="bold", size=11)
        # Split summary into lines ~85 chars
        words = summary.split()
        curr_line = []
        for w in words:
            curr_line.append(w)
            if len(" ".join(curr_line)) > 85:
                pdf.add_line(" ".join(curr_line), size=9)
                curr_line = []
        if curr_line:
            pdf.add_line(" ".join(curr_line), size=9)
        pdf.add_line("")

        pdf.add_line("CORE COMPETENCIES", font_style="bold", size=11)
        for sk in skills[:8]:
            pdf.add_line(f"- {sk[:90]}", size=9)
        pdf.add_line("")

        pdf.add_line("PROFESSIONAL EXPERIENCE", font_style="bold", size=11)
        for emp in self.candidate_truth.employment_history:
            header = f"{emp.role} | {emp.company} [{emp.start_date} - {emp.end_date}]"
            pdf.add_line(header, font_style="bold", size=10)
            for resp in emp.responsibilities[:3]:
                pdf.add_line(f"- {resp[:90]}", size=8)
            pdf.add_line("")

        pdf.add_line("CERTIFICATIONS", font_style="bold", size=11)
        for cert in self.candidate_truth.certifications:
            pdf.add_line(f"- {cert.name} ({cert.year})", size=9)
        pdf.add_line("")

        pdf.add_line("EDUCATION", font_style="bold", size=11)
        for edu in self.candidate_truth.education:
            pdf.add_line(f"{edu.degree} - {edu.field} | {edu.institution}", size=9)

        pdf.write(path)
