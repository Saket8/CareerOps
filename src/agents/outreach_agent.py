"""Recruiter & Hiring Manager Discovery and 1-Click Outreach Drafter.

Identifies the relevant hiring managers or talent acquisition partners for high-match opportunities,
and crafts hyper-tailored 3-bullet executive InMail/email outreach drafts ready for 1-click dispatch.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import html
from src.models.candidate import CandidateTruth
from src.models.job import JobListing
from src.models.score import JobScore
from src.utils.logger import get_logger

logger = get_logger("outreach_agent")


@dataclass
class OutreachDraft:
    job_id: str
    company: str
    role: str
    hiring_lead_target: str
    search_query: str
    subject: str
    inmail_message: str
    cold_email_message: str
    linkedin_search_url: str


class OutreachAgent:
    """Discovers target hiring contacts and generates high-conversion executive outreach drafts."""

    def __init__(self, candidate_truth: CandidateTruth, config: Dict[str, Any]):
        self.candidate_truth = candidate_truth
        self.config = config

    def draft_outreach(
        self,
        job: JobListing,
        score: JobScore,
        recruiter_lead: Optional[Dict[str, Any]] = None,
    ) -> OutreachDraft:
        """Generates hyper-targeted 3-bullet executive outreach for high-match opportunities."""
        cand = self.candidate_truth.candidate
        comp = job.company
        title = job.title

        # Determine target persona or use discovered lead
        is_director_level = any(k in title.lower() for k in ("lead", "principal", "director", "staff", "architect"))
        if recruiter_lead and recruiter_lead.get("name"):
            lead_name = recruiter_lead.get("first_name") or recruiter_lead.get("name").split()[0]
            target_title = f"{recruiter_lead.get('name')} ({recruiter_lead.get('title', 'Talent Acquisition')})"
            search_kw = f"{comp} {recruiter_lead.get('title', 'Talent Acquisition')}"
            linkedin_search_url = recruiter_lead.get("profile_url") or f"https://www.linkedin.com/search/results/people/?keywords={html.escape(comp + ' Talent Acquisition')}"
            greeting = f"Hi {lead_name},"
        else:
            if is_director_level:
                target_title = f"{comp} Director of Engineering OR Head of Cloud Architecture"
            else:
                target_title = f"{comp} Technical Recruiter OR Talent Acquisition Lead"
            search_kw = f"{comp} Talent Acquisition Cloud OR Engineering Manager"
            linkedin_search_url = f"https://www.linkedin.com/search/results/people/?keywords={html.escape(search_kw)}"
            greeting = "Hi [Name],"

        subject = f"{cand.name} — Principal Cloud & AI Architect for {title} @ {comp}"

        # 3-Bullet Executive Pitch
        inmail_body = (
            f"{greeting}\n\n"
            f"I recently applied for the {title} role at {comp} and wanted to reach out directly given how closely my enterprise background aligns with your architectural goals.\n\n"
            f"A brief snapshot of what I bring:\n"
            f"• 12 Years Total Enterprise IT Tenure: Proven track record driving large-scale enterprise cloud transformations, multi-region high availability, and 99.99% operational reliability.\n"
            f"• 6.5 Years Oracle Cloud Infrastructure (OCI) & Multi-Cloud Leadership: Hands-on architect for zero-downtime database migrations, microservices, containerization (Kubernetes/OKE), and Infrastructure as Code (Terraform).\n"
            f"• 5.0 Years Generative AI & Agentic Platforms: Architecting production LLMOps pipelines, agentic AI frameworks, and resilient enterprise AI security.\n\n"
            f"I am fully available for international relocation / on-site commitments in {job.location} and would value a brief conversation if this aligns with your current priorities.\n\n"
            f"Best regards,\n"
            f"{cand.name}\n"
            f"{cand.title}\n"
            f"{cand.email} | {cand.phone}\n"
            f"LinkedIn: linkedin.com/in/saket-saurav-cloud"
        )

        cold_email_body = (
            f"{greeting}\n\n"
            f"Hope this note finds you well. I noticed {comp} is actively expanding its engineering leadership with the {title} opening in {job.location}.\n\n"
            f"As a Principal Cloud & AI Engineer with 12 years of enterprise tenure (6.5 years OCI/Cloud, 5.0 years AI/GenAI), I have led cost-optimization migrations delivering >30% efficiency while preserving carrier-grade uptime.\n\n"
            f"Would you be open to a 10-minute introductory sync this week?\n\n"
            f"Warm regards,\n"
            f"{cand.name}\n"
            f"{cand.email} | {cand.phone}"
        )

        return OutreachDraft(
            job_id=job.job_id,
            company=comp,
            role=title,
            hiring_lead_target=target_title,
            search_query=search_kw,
            subject=subject,
            inmail_message=inmail_body,
            cold_email_message=cold_email_body,
            linkedin_search_url=linkedin_search_url,
        )
