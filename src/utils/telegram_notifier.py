"""Telegram Real-Time Push Notification Engine for CareerOps.

Delivers instant mobile push notifications for:
- Confirmed job applications (Naukri Direct, LinkedIn Easy Apply, Greenhouse/Lever ATS)
- Real-time inbound recruiter interview invitations
- Daily executive pipeline execution summaries
"""

import json
import html
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger("telegram_notifier")


class TelegramNotifier:
    """Manages instant real-time Telegram push alerts."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        tg_cfg = config.get("telegram", {})
        self.enabled = bool(tg_cfg.get("enabled", False))
        self.bot_token = tg_cfg.get("bot_token", "")
        self.chat_id = tg_cfg.get("chat_id", "")
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Sends an instant text push notification via Telegram Bot API."""
        if not self.enabled or not self.bot_token or not self.chat_id:
            logger.debug("Telegram notifications not configured or disabled.")
            return False

        try:
            url = f"{self.api_base}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                success = bool(res_data.get("ok", False))
                if success:
                    logger.info("Telegram notification delivered successfully.")
                return success
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}")
            return False

    def notify_application_submitted(
        self,
        company: str,
        role: str,
        location: str,
        platform: str,
        match_score: float,
        confirmation_ref: Optional[str] = None,
        job_url: Optional[str] = None,
        cover_letter: bool = False,
    ) -> bool:
        """Sends an instant alert when a job application is successfully submitted."""
        cl_tag = " | 📄 <i>Cover Letter Attached</i>" if cover_letter else ""
        msg = (
            f"🚀 <b>CareerOps — Application Submitted!</b>\n\n"
            f"🏢 <b>Company:</b> {company}\n"
            f"🎯 <b>Role:</b> {role}\n"
            f"📍 <b>Location:</b> {location}\n"
            f"🌐 <b>Platform:</b> {platform}\n"
            f"📊 <b>Profile Match:</b> <code>{match_score:.1f}%</code>{cl_tag}\n"
        )
        if confirmation_ref:
            msg += f"🔖 <b>Ref:</b> <code>{confirmation_ref}</code>\n"
        if job_url:
            msg += f"\n🔗 <a href='{job_url}'>View Listing / Verify Status</a>"

        return self.send_message(msg)

    def notify_interview_invite(
        self,
        sender: str,
        subject: str,
        company: Optional[str] = None,
        snippet: Optional[str] = None,
    ) -> bool:
        """Sends high-priority push alert when an inbound interview invite is detected."""
        msg = (
            f"🎉 <b>URGENT: Recruiter Interview Invitation!</b>\n\n"
            f"🏢 <b>Company:</b> {company or 'Enterprise Partner'}\n"
            f"👤 <b>From:</b> {sender}\n"
            f"📝 <b>Subject:</b> {subject}\n"
        )
        if snippet:
            msg += f"\n💬 <i>\"{snippet[:250]}...\"</i>\n"
        msg += "\n⚡ <i>Status updated to INTERVIEW in your CareerOps CRM.</i>"

        return self.send_message(msg)

    def notify_daily_summary(
        self,
        date_str: str,
        confirmed_count: int,
        qualified_count: int,
        scanned_count: int,
        dry_run: bool = False,
        source_summary: Optional[Dict[str, int]] = None,
    ) -> bool:
        """Sends the daily executive completion summary via Telegram."""
        mode_tag = " [DRY RUN]" if dry_run else " [LIVE]"
        msg = (
            f"📊 <b>CareerOps — Daily Pipeline Complete{mode_tag}</b>\n"
            f"📅 <b>Date:</b> {date_str}\n\n"
            f"• <b>Jobs Scanned:</b> {scanned_count}\n"
            f"• <b>Qualified Roles:</b> {qualified_count}\n"
            f"• <b>Applications Confirmed:</b> <b>{confirmed_count}</b>\n"
        )
        if source_summary:
            msg += "\n📈 <b>Source Breakdown (Confirmed):</b>\n"
            for src_name, c_cnt in source_summary.items():
                msg += f"  - {src_name}: <b>{c_cnt}</b>\n"

        msg += "\n📬 <i>Full report and tailored dossiers delivered to your email.</i>"
        return self.send_message(msg)

    def notify_recruiter_draft(
        self,
        company: str,
        role: str,
        contact_source: str,
        job_url: str,
        match_rationale: str,
        pitch: str,
        inmail_url: Optional[str] = None,
    ) -> bool:
        """Sends a recruiter outreach draft to Telegram for human review and 1-click dispatch.
        NOTE: This is strictly for human review. CareerOps NEVER sends messages to recruiters automatically.
        """
        clean_company = html.escape(company)
        clean_role = html.escape(role)
        clean_contact = html.escape(contact_source)
        clean_rationale = html.escape(match_rationale)
        clean_pitch = html.escape(pitch)

        msg = (
            f"📨 <b>CareerOps — Recruiter Outreach Draft for Review</b>\n\n"
            f"🏢 <b>Company:</b> {clean_company}\n"
            f"🎯 <b>Role:</b> {clean_role}\n"
            f"👤 <b>Contact / Target:</b> {clean_contact}\n"
            f"📊 <b>Match Rationale:</b> {clean_rationale}\n"
            f"🔗 <a href='{job_url}'>View Job Posting</a>\n\n"
            f"📝 <b>Proposed 3-Bullet Pitch:</b>\n"
            f"<blockquote>{clean_pitch[:600]}...</blockquote>\n\n"
        )
        if inmail_url:
            msg += f"👉 <a href='{inmail_url}'>Review Profile & Send on LinkedIn ↗</a>\n\n"
        msg += "⚠️ <i>Draft saved in database for review. Not sent to recruiter automatically.</i>"

        return self.send_message(msg)

    def notify_run_delay_or_failure(
        self,
        run_id: str,
        status: str,
        error_msg: Optional[str] = None,
        elapsed_seconds: Optional[float] = None,
        target_seconds: Optional[float] = None,
    ) -> bool:
        """Sends an instant push alert when a pipeline run misses its target window or encounters a failure."""
        if status == "DELAYED":
            mins = int(elapsed_seconds / 60) if elapsed_seconds else 0
            target_mins = int(target_seconds / 60) if target_seconds else 15
            msg = (
                f"⚠️ <b>CareerOps — Run Execution Delayed</b>\n\n"
                f"🆔 <b>Run ID:</b> <code>{run_id}</code>\n"
                f"⏱️ <b>Elapsed Time:</b> {mins} min (Target: {target_mins} min)\n"
                f"ℹ️ <i>The daily pipeline is running longer than historical baseline. Continuing execution...</i>\n"
            )
        else:
            msg = (
                f"🚨 <b>CareerOps — Pipeline Run Failure Alert</b>\n\n"
                f"🆔 <b>Run ID:</b> <code>{run_id}</code>\n"
                f"❌ <b>Status:</b> {status}\n"
            )
            if error_msg:
                msg += f"⚠️ <b>Error Details:</b> <code>{html.escape(error_msg[:300])}</code>\n"
            if elapsed_seconds:
                msg += f"⏱️ <b>Duration before halt:</b> {int(elapsed_seconds)}s\n"

        return self.send_message(msg)
