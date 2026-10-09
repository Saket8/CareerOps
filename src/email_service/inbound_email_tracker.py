"""Inbound Recruiter Email Scanner and Application Lifecycle Tracker.

Monitors candidate inbox (via IMAP/SMTP host credentials) for inbound recruiter communications:
- Interview invitations
- Screening calls
- Test/assessment requests
- Rejection notices
Matches them back to the CareerOps applications database and updates application status in real-time.
"""

import re
import imaplib
import email
from email.header import decode_header
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass

from src.models.job import JobStatus
from src.database.connection import get_db_session
from src.database.models import ApplicationModel, JobModel
from src.utils.logger import get_logger

logger = get_logger("inbound_email_tracker")

KEYWORDS_INTERVIEW = [
    "interview", "screening", "invitation to connect", "availability", "phone screen",
    "technical discussion", "round 1", "virtual interview", "hiring manager", "shortlisted"
]
KEYWORDS_REJECTION = [
    "unfortunately", "other candidates", "not moving forward", "not selected",
    "regret to inform", "pursuing other applicants"
]


@dataclass
class RecruiterMessage:
    sender: str
    subject: str
    date: str
    category: str  # INTERVIEW, REJECTION, UPDATE
    snippet: str
    matched_job_id: Optional[str] = None
    matched_company: Optional[str] = None


class InboundEmailTracker:
    """Scans incoming recruiter messages and correlates with active applications."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.email_cfg = config.get("email", {})
        self.host = self.email_cfg.get("imap_host", "imap.gmail.com")
        self.port = self.email_cfg.get("imap_port", 993)
        self.username = self.email_cfg.get("username", "")
        self.password = self.email_cfg.get("password", "")

    def scan_inbox(self, max_messages: int = 25) -> List[RecruiterMessage]:
        """Scans recent inbox messages for recruiter responses."""
        if not self.username or not self.password:
            logger.info("IMAP credentials not configured. Skipping live inbox scan.")
            return []

        recruiter_messages: List[RecruiterMessage] = []

        try:
            mail = imaplib.IMAP4_SSL(self.host, self.port)
            mail.login(self.username, self.password)
            mail.select("INBOX")

            # Search recent unread or recent messages
            status, response = mail.search(None, "ALL")
            if status != "OK" or not response or not response[0]:
                mail.logout()
                return []

            msg_ids = response[0].split()
            recent_ids = msg_ids[-max_messages:]

            for mid in reversed(recent_ids):
                try:
                    res, data = mail.fetch(mid, "(RFC822)")
                    if res != "OK":
                        continue

                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Extract subject
                    subject_header = msg.get("Subject", "")
                    decoded_parts = decode_header(subject_header)
                    subject = ""
                    for part, enc in decoded_parts:
                        if isinstance(part, bytes):
                            subject += part.decode(enc or "utf-8", errors="ignore")
                        else:
                            subject += str(part)

                    sender = msg.get("From", "")
                    date_str = msg.get("Date", "")

                    # Extract body text
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                    combined_text = f"{subject}\n{body}".lower()

                    # Classify
                    category = None
                    if any(kw in combined_text for kw in KEYWORDS_INTERVIEW):
                        category = "INTERVIEW"
                    elif any(kw in combined_text for kw in KEYWORDS_REJECTION):
                        category = "REJECTION"

                    if category:
                        snippet = body.strip().replace("\n", " ")[:200]
                        matched_id, matched_company = self._correlate_with_db(combined_text)

                        rm = RecruiterMessage(
                            sender=sender,
                            subject=subject,
                            date=date_str,
                            category=category,
                            snippet=snippet,
                            matched_job_id=matched_id,
                            matched_company=matched_company,
                        )
                        recruiter_messages.append(rm)

                        # Update DB lifecycle status
                        if matched_id:
                            self._update_lifecycle(matched_id, category)
                except Exception as m_err:
                    logger.debug(f"Error processing email message {mid}: {m_err}")

            mail.logout()
        except Exception as e:
            logger.warning(f"Inbound email tracker connection note: {e}")

        return recruiter_messages

    def _correlate_with_db(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Matches email content against company names in applications DB."""
        try:
            with get_db_session() as session:
                apps = (
                    session.query(ApplicationModel.job_id, JobModel.company)
                    .join(JobModel, ApplicationModel.job_id == JobModel.job_id)
                    .all()
                )
                for jid, comp in apps:
                    if comp and comp.lower() in text:
                        return jid, comp
        except Exception:
            pass
        return None, None

    def _update_lifecycle(self, job_id: str, category: str) -> None:
        """Updates the application record with recruiter outcome."""
        try:
            with get_db_session() as session:
                app = session.query(ApplicationModel).filter(ApplicationModel.job_id == job_id).first()
                if app:
                    if category == "INTERVIEW":
                        app.status = JobStatus.INTERVIEW.value
                        logger.info(f"Updated job {job_id} to INTERVIEW based on inbound recruiter email.")
                    elif category == "REJECTION":
                        app.status = JobStatus.REJECTED.value
                        logger.info(f"Updated job {job_id} to REJECTED based on inbound recruiter email.")
                    session.commit()
        except Exception as err:
            logger.warning(f"Could not update application lifecycle in DB: {err}")
