"""Executive Cover Letter Generator tailored for European, Nordic, US, and Global Enterprise roles.

Generates highly compelling, personalized executive cover letters in both DOCX and PDF formats
aligned strictly with verified candidate facts and target job requirements.
"""

import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from src.models.candidate import CandidateTruth
from src.models.job import JobListing
from src.models.score import JobScore
from src.utils.logger import get_logger

logger = get_logger("cover_letter_agent")


class CoverLetterAgent:
    """Generates executive, ATS-tailored cover letters in DOCX and PDF."""

    def __init__(self, candidate_truth: CandidateTruth, config: Dict[str, Any]):
        self.candidate_truth = candidate_truth
        self.config = config
        self.output_dir = Path("cover_letters/generated")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_cover_letter(
        self,
        job: JobListing,
        score: JobScore,
    ) -> Tuple[Path, Path]:
        """Generates tailored executive cover letter in DOCX and PDF format."""
        cand = self.candidate_truth.candidate
        now = datetime.now(timezone.utc)
        safe_company = "".join(c if c.isalnum() else "_" for c in job.company).strip("_")
        safe_title = "".join(c if c.isalnum() else "_" for c in job.title[:25]).strip("_")
        base_name = f"{safe_company}_{safe_title}_{job.job_id}_{now.strftime('%Y%m%d')}_CoverLetter"

        docx_path = self.output_dir / f"{base_name}.docx"
        pdf_path = self.output_dir / f"{base_name}.pdf"

        # Determine target track context (OCI / Cloud vs AI / GenAI vs Hybrid)
        is_ai_role = score.ai_score >= 70.0 or any(
            kw in job.title.lower() for kw in ("ai", "genai", "llm", "agentic", "ml")
        )

        doc = docx.Document()

        # Set standard margins (1 inch / 72pt)
        for section in doc.sections:
            section.top_margin = Inches(0.9)
            section.bottom_margin = Inches(0.9)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        # 1. Header (Candidate Contact Info)
        h_para = doc.add_paragraph()
        h_run = h_para.add_run(cand.name)
        h_run.font.size = Pt(16)
        h_run.font.bold = True
        h_run.font.color.rgb = RGBColor(15, 23, 42)  # Slate 900

        sub_para = doc.add_paragraph()
        sub_run = sub_para.add_run(
            f"{cand.title} | {cand.location} | {cand.email} | {cand.phone}\n"
            f"LinkedIn: linkedin.com/in/saket-saurav-cloud"
        )
        sub_run.font.size = Pt(9.5)
        sub_run.font.color.rgb = RGBColor(71, 85, 105)  # Slate 600

        doc.add_paragraph()  # Blank spacing

        # Date & Addressee
        date_para = doc.add_paragraph()
        date_run = date_para.add_run(f"{now.strftime('%B %d, %Y')}\n\n")
        date_run.font.size = Pt(10)
        date_run.font.color.rgb = RGBColor(51, 65, 85)

        recipient_para = doc.add_paragraph()
        rec_text = (
            f"Hiring Team & Leadership\n"
            f"{job.company}\n"
            f"{job.location}\n"
        )
        rec_run = recipient_para.add_run(rec_text)
        rec_run.font.size = Pt(10)
        rec_run.font.color.rgb = RGBColor(30, 41, 59)

        # Subject Line
        subj_para = doc.add_paragraph()
        subj_run = subj_para.add_run(f"RE: Application for {job.title} — {job.company}")
        subj_run.font.size = Pt(10.5)
        subj_run.font.bold = True
        subj_run.font.color.rgb = RGBColor(15, 23, 42)

        doc.add_paragraph()

        # Salutation
        salut_para = doc.add_paragraph()
        salut_run = salut_para.add_run(f"Dear Hiring Team at {job.company},")
        salut_run.font.size = Pt(10)

        # Body Paragraph 1: Opening & Immediate Value Hook
        p1 = doc.add_paragraph()
        if is_ai_role:
            hook_text = (
                f"I am writing to express my strong interest in the {job.title} role at {job.company}. "
                f"With over 12 years of enterprise engineering leadership—including 5.0 years architecting Generative AI, "
                f"LLMOps, and agentic systems alongside 6.5 years of Oracle Cloud Infrastructure (OCI) and multi-cloud solutions—"
                f"I specialize in bridging advanced AI innovation with carrier-grade, highly secure enterprise infrastructure."
            )
        else:
            hook_text = (
                f"I am writing to express my strong interest in the {job.title} position at {job.company}. "
                f"As a Principal Cloud Engineer with 12 years of enterprise IT tenure and 6.5 years dedicated to designing, "
                f"migrating, and governing mission-critical Oracle Cloud Infrastructure (OCI) and multi-cloud environments, "
                f"I bring deep hands-on expertise in zero-downtime database migrations, microservices architectures, and automated infrastructure as code."
            )
        p1_run = p1.add_run(hook_text)
        p1_run.font.size = Pt(10)
        p1.paragraph_format.line_spacing = 1.15
        p1.paragraph_format.space_after = Pt(8)

        # Body Paragraph 2: Core Impact & Proven Results
        p2 = doc.add_paragraph()
        p2_text = (
            f"Throughout my tenure leading enterprise programs at Cognizant and strategic client accounts, "
            f"I have architected end-to-end cloud infrastructure migrations reducing client infrastructure costs by over 30%, "
            f"engineered multi-region high availability architectures achieving 99.99% service availability, and implemented "
            f"automated CI/CD pipelines deploying infrastructure across Terraform, Kubernetes (OKE), and microservices with zero operational regression."
        )
        p2_run = p2.add_run(p2_text)
        p2_run.font.size = Pt(10)
        p2.paragraph_format.line_spacing = 1.15
        p2.paragraph_format.space_after = Pt(8)

        # Body Paragraph 3: Alignment with Target Role & Company
        p3 = doc.add_paragraph()
        strengths_str = ", ".join(score.strengths[:3]) if score.strengths else "cloud architecture and resilient infrastructure"
        p3_text = (
            f"What particularly excites me about joining {job.company} is the opportunity to deliver measurable value in {job.location}. "
            f"My competencies directly mirror your technical requirements—specifically in {strengths_str}. "
            f"I operate with a strong owner mindset, translating complex architectural requirements into scalable, fault-tolerant platforms while empowering engineering teams."
        )
        p3_run = p3.add_run(p3_text)
        p3_run.font.size = Pt(10)
        p3.paragraph_format.line_spacing = 1.15
        p3.paragraph_format.space_after = Pt(8)

        # Body Paragraph 4: Mobility, Relocation & Sponsorship Readiness
        p4 = doc.add_paragraph()
        is_international = any(
            reg in job.location.lower()
            for reg in ("europe", "nordic", "denmark", "sweden", "norway", "finland", "australia", "united states", "uk", "germany", "netherlands")
        )
        if is_international:
            p4_text = (
                f"I am fully prepared and enthusiastic regarding international relocation to {job.location} or operating across flexible on-site/hybrid models. "
                f"I am an Indian citizen available for global sponsorship and relocation, ready to transition rapidly to support your team's operational milestones."
            )
        else:
            p4_text = (
                f"I am readily available for on-site, hybrid, or remote engagements, offering immediate architectural stewardship and leadership."
            )
        p4_run = p4.add_run(p4_text)
        p4_run.font.size = Pt(10)
        p4.paragraph_format.line_spacing = 1.15
        p4.paragraph_format.space_after = Pt(12)

        # Closing
        close_p = doc.add_paragraph()
        close_text = (
            f"Thank you for your time, consideration, and review. I look forward to the opportunity to discuss how my "
            f"background and technical leadership can accelerate {job.company}'s strategic goals.\n\n"
            f"Sincerely,\n\n"
            f"{cand.name}\n"
            f"{cand.title}\n"
            f"{cand.email} | {cand.phone}"
        )
        close_run = close_p.add_run(close_text)
        close_run.font.size = Pt(10)

        # Save DOCX
        doc.save(str(docx_path))
        logger.info(f"Generated Executive Cover Letter DOCX: {docx_path}")

        # Generate Companion PDF
        self._generate_pdf(docx_path, pdf_path, cand, job, hook_text, p2_text, p3_text, p4_text, is_ai_role)
        logger.info(f"Generated Executive Cover Letter PDF: {pdf_path}")

        return docx_path, pdf_path

    def _generate_pdf(
        self,
        docx_path: Path,
        pdf_path: Path,
        cand: Any,
        job: JobListing,
        p1_text: str,
        p2_text: str,
        p3_text: str,
        p4_text: str,
        is_ai_role: bool,
    ) -> None:
        """Renders an executive, print-ready PDF cover letter."""
        html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    color: #1e293b;
    margin: 40px 50px;
    font-size: 13.5px;
    line-height: 1.6;
  }}
  .header {{
    border-bottom: 2px solid #0284c7;
    padding-bottom: 12px;
    margin-bottom: 24px;
  }}
  .name {{
    font-size: 24px;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.5px;
  }}
  .contact {{
    font-size: 11.5px;
    color: #64748b;
    margin-top: 4px;
  }}
  .date-addressee {{
    margin-bottom: 20px;
    font-size: 13px;
    color: #334155;
  }}
  .subject {{
    font-weight: 700;
    color: #0284c7;
    font-size: 14px;
    margin-bottom: 16px;
    padding: 6px 12px;
    background: #f0f9ff;
    border-left: 3px solid #0284c7;
  }}
  p {{
    margin-bottom: 14px;
    text-align: justify;
  }}
  .signature {{
    margin-top: 28px;
    font-size: 13px;
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="name">{cand.name}</div>
    <div class="contact">{cand.title} &bull; {cand.location} &bull; {cand.email} &bull; {cand.phone}</div>
  </div>

  <div class="date-addressee">
    <strong>{datetime.now(timezone.utc).strftime('%B %d, %Y')}</strong><br><br>
    Hiring Team & Engineering Leadership<br>
    {job.company}<br>
    {job.location}
  </div>

  <div class="subject">RE: Application for {job.title} — {job.company}</div>

  <p>Dear Hiring Team at {job.company},</p>
  <p>{p1_text}</p>
  <p>{p2_text}</p>
  <p>{p3_text}</p>
  <p>{p4_text}</p>

  <div class="signature">
    Sincerely,<br><br>
    <strong>{cand.name}</strong><br>
    {cand.title}<br>
    {cand.email} | {cand.phone}
  </div>
</body>
</html>"""

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_doc, wait_until="networkidle")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "15mm", "bottom": "15mm", "left": "18mm", "right": "18mm"},
                )
                browser.close()
            return
        except Exception as e:
            logger.warning(f"Playwright cover letter PDF generation fallback: {e}")

        # Text-based fallback if Playwright unavailable
        pdf_path.write_text(html_doc, encoding="utf-8")
