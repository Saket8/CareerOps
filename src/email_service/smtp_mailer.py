import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

from src.utils.logger import get_logger

logger = get_logger("smtp_mailer")


class SmtpMailer:
    """Dispatches HTML reports securely with retry logic and graceful dry-run fallback."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config.get("email", {}) if config else {}
        self.server_host = os.environ.get("SMTP_SERVER", cfg.get("smtp_server", "smtp.gmail.com"))
        self.server_port = int(os.environ.get("SMTP_PORT", cfg.get("smtp_port", 587)))
        self.use_tls = cfg.get("smtp_use_tls", True)
        self.username = os.environ.get("SMTP_USERNAME", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        self.sender_name = cfg.get("sender_name", "Autonomous Career Agent")
        self.default_recipient = os.environ.get("EMAIL_RECIPIENT", cfg.get("default_recipient", "sauravskt8@gmail.com"))
        self.enabled = cfg.get("enabled", True) and os.environ.get("EMAIL_ENABLED", "true").lower() in ("true", "1", "yes")

    def send_report(
        self,
        subject: str,
        html_body: str,
        text_body: str = "",
        recipient: Optional[str] = None,
        attachments: Optional[List[Union[str, Path]]] = None,
        max_retries: int = 3,
    ) -> bool:
        """Sends an HTML email report with retry logic and optional file attachments."""
        target_recipient = recipient or self.default_recipient

        if not self.enabled:
            logger.info(f"Email delivery disabled by config. Skipping email to {target_recipient}.")
            return False

        if not self.username or not self.password:
            logger.warning(
                "SMTP credentials (SMTP_USERNAME/SMTP_PASSWORD) not configured in environment. "
                f"Skipping live email dispatch for '{subject}'. Report preserved locally."
            )
            return False

        if attachments:
            msg = MIMEMultipart("mixed")
            body_part = MIMEMultipart("alternative")
            body_part.attach(MIMEText(text_body or "Please view this email in an HTML-compatible client.", "plain", "utf-8"))
            body_part.attach(MIMEText(html_body, "html", "utf-8"))
            msg.attach(body_part)

            for attach_item in attachments:
                attach_path = Path(attach_item)
                if attach_path.exists() and attach_path.is_file():
                    try:
                        with open(attach_path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=attach_path.name)
                        part["Content-Disposition"] = f'attachment; filename="{attach_path.name}"'
                        msg.attach(part)
                        logger.info(f"Attached file {attach_path.name} to email '{subject}'")
                    except Exception as e:
                        logger.warning(f"Failed to attach file {attach_path}: {e}")
        else:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(text_body or "Please view this email in an HTML-compatible client.", "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        msg["Subject"] = subject
        msg["From"] = f"{self.sender_name} <{self.username}>"
        msg["To"] = target_recipient

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Attempting to send email '{subject}' to {target_recipient} (attempt {attempt}/{max_retries})...")
                with smtplib.SMTP(self.server_host, self.server_port, timeout=15) as server:
                    if self.use_tls:
                        server.starttls()
                    server.login(self.username, self.password)
                    server.send_message(msg)

                logger.info(f"Email '{subject}' successfully delivered to {target_recipient}")
                return True
            except Exception as exc:
                logger.error(f"Failed to send email on attempt {attempt}: {exc}")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)

        logger.error(f"Email delivery failed after {max_retries} attempts.")
        return False
