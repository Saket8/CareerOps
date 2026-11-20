"""Hyperscaler & Tier-1 GCC Employee Referral and Direct Application Pack Generator.

Generates pre-crafted 30-second LinkedIn employee referral messages, hiring manager pitches,
pre-resolved ATS screening answers, and links to tailored resumes for direct enterprise requisitions
(AWS, Microsoft, Google Cloud, Oracle OCI, Barclays, Adobe, Walmart Global Tech, etc.).
"""

import os
import re
import html
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from src.models.candidate import CandidateTruth
from src.models.job import JobListing
from src.models.score import JobScore
from src.utils.logger import get_logger

logger = get_logger("referral_pack_agent")


class ReferralPackAgent:
    """Generates 1-click referral pitches, direct application kits, and hiring manager outreach."""

    def __init__(self, candidate_truth: CandidateTruth, config: Dict[str, Any], base_dir: Path = Path("interviews")):
        self.candidate_truth = candidate_truth
        self.config = config
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def generate_referral_pack(
        self,
        job: JobListing,
        score: JobScore,
        docx_path: Path,
        pdf_path: Path,
    ) -> Path:
        """Generates a comprehensive referral and direct application package on disk."""
        safe_company = re.sub(r"[^\w\-]", "_", job.company).strip("_")
        safe_role = re.sub(r"[^\w\-]", "_", job.title).strip("_")
        pack_dir = self.base_dir / safe_company / safe_role
        pack_dir.mkdir(parents=True, exist_ok=True)

        cand = self.candidate_truth.candidate
        req_id_match = re.search(r"(?:Job ID|Req ID|JR-|_R|_)([A-Za-z0-9\-]+)", job.jd_text or "") or re.search(r"/jobs/(\d+)/", job.url)
        req_id = req_id_match.group(1) if req_id_match else "Direct-Req"

        # Determine recruiter search URL
        comp_clean = re.sub(r"\(.*?\)", "", job.company).strip()
        search_kw = f"{comp_clean} Recruiter Cloud OR Talent Acquisition"
        recruiter_search_url = f"https://www.linkedin.com/search/results/people/?keywords={html.escape(search_kw)}"

        # Pre-drafted 30-Second LinkedIn Employee Referral Message
        referral_message = (
            f"Hi [Name],\n\n"
            f"Hope you are doing well! I noticed an open {job.title} role at {job.company} "
            f"(Requisition/Job ID: {req_id}) in {job.location}.\n\n"
            f"With 12 years of enterprise IT experience and 6.5 years dedicated to Cloud & Security Architecture "
            f"(OCI / Multi-Cloud / Kubernetes / IaC / AI Platform integration), my background strongly aligns with this opening.\n\n"
            f"Would you be open to putting in a quick internal employee referral for me? "
            f"I have a tailored resume ready for this specific requisition.\n\n"
            f"Direct Requisition URL: {job.url}\n"
            f"My LinkedIn Profile: https://www.linkedin.com/in/saket-saurav-31326b57/\n\n"
            f"Thank you for your time and help!\n\n"
            f"Best regards,\n"
            f"{cand.name}\n"
            f"+91-7028481800 | {cand.email}"
        )

        # Pre-drafted Cold Outreach to Hiring Manager / Engineering Director
        hiring_manager_message = (
            f"Hi [Hiring Manager Name],\n\n"
            f"I recently reviewed {job.company}'s open requisition for {job.title} (Job ID: {req_id}) "
            f"in {job.location} and wanted to reach out directly.\n\n"
            f"Key highlights of what I deliver:\n"
            f"• 12 Years Total Enterprise Tenure: Designing enterprise-scale infrastructure, high-availability clusters, and automated landing zones.\n"
            f"• 6.5 Years Cloud & OCI Architecture: Proven leadership in zero-downtime database migrations, microservices orchestration, and security hardening.\n"
            f"• 5.0 Years AI & Agentic Platforms: Production-grade LLMOps, agentic workflows, and secure AI infra deployment.\n\n"
            f"I have submitted my application via {job.company}'s career portal and would welcome a brief conversation to explore how my architectural experience can accelerate your roadmap.\n\n"
            f"Tailored Resume: Available on request\n"
            f"LinkedIn: https://www.linkedin.com/in/saket-saurav-31326b57/\n\n"
            f"Best regards,\n"
            f"{cand.name}\n"
            f"{cand.email} | +91-7028481800"
        )

        pack_file = pack_dir / "REFERRAL_AND_DIRECT_APPLY_PACK.md"
        content = f"""# Tier-1 GCC / Hyperscaler Direct Requisition Pack

**Company:** {job.company}  
**Requisition Title:** {job.title}  
**Requisition / Job ID:** `{req_id}`  
**Location:** {job.location} ({job.work_mode or 'On-site / Hybrid'})  
**Direct Career Portal Link:** [{job.url}]({job.url})  
**Match Score:** {score.overall_score:.1f}% ({'Tier-1 GCC / Hyperscaler Priority' if score.overall_score >= 80 else 'Qualified'})  
**Generated At:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  

---

## 1. Tailored Resume Files
- **Tailored Resume (PDF):** [{pdf_path.name}](file://{pdf_path.resolve()})
- **Tailored Resume (DOCX):** [{docx_path.name}](file://{docx_path.resolve()})

---

## 2. 30-Second Internal Employee Referral Pitch
> **Usage:** Send this via LinkedIn Message / InMail to any 1st or 2nd degree connection working at **{job.company}**.

```text
{referral_message}
```

---

## 3. Direct Hiring Manager / Director Outreach Pitch
> **Usage:** Send this to the Engineering Director, Head of Cloud, or Practice Lead at **{job.company}**.

```text
{hiring_manager_message}
```

---

## 4. Recruiter Discovery Link
Find Talent Acquisition leads & technical recruiters for this role:
- [LinkedIn Search: {comp_clean} Talent Acquisition]({recruiter_search_url})

---

## 5. Pre-Resolved ATS Screening Answers (Direct Portal Fast-Fill)
When applying directly on **{job.company}'s Career Portal**, use these verified candidate facts:

| Screening Field | Verified Profile Answer |
|---|---|
| **Full Name** | `Saket Saurav` |
| **Email** | `sauravskt8@gmail.com` *(Strict personal email)* |
| **Phone** | `+91-7028481800` |
| **Current Location** | `Noida, India` (Delhi NCR) |
| **LinkedIn URL** | `https://www.linkedin.com/in/saket-saurav-31326b57/` |
| **GitHub URL** | `https://github.com/Saket8` |
| **Current Employer** | `Cognizant` (Principal Cloud Architect) |
| **Current Employment Dates** | `Nov 2024 – Present` (2.0 yrs) |
| **Total Experience** | `12 Years` |
| **Relevant Cloud / OCI Experience** | `6.5 Years` |
| **Generative AI / Agentic AI Experience**| `5.0 Years` |
| **Official Notice Period** | `90 Days` (Official / Negotiable) |
| **Work Authorization** | `Authorized to work in India (Citizen)` |
| **Willingness to Relocate** | `Yes (Pan India & International Relocation Target)` |

---
*Generated autonomously by CareerOps Direct Portal & Referral Intelligence Engine.*
"""

        pack_file.write_text(content, encoding="utf-8")
        logger.info(f"Generated Direct Referral & Application Pack for {job.company} ({job.title}) at {pack_file}")
        return pack_file
