"""Mailbox Retention Manager for CareerOps Automated Reports.

Enforces strict retention policy on candidate Gmail mailbox:
- Maintains at most the latest 3 CareerOps system report emails in 'INBOX'
- Maintains at most the latest 3 CareerOps system report emails in '[Gmail]/Sent Mail'
- Purges older CareerOps emails to '[Gmail]/Bin' while strictly protecting
  all recruiter interactions, personal emails, and external communications.
"""

import os
import sys
import re
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv

from src.utils.logger import get_logger

logger = get_logger("mailbox_retention")

TARGET_FOLDERS = ["INBOX", "[Gmail]/Sent Mail"]
TRASH_FOLDER = '"[Gmail]/Bin"'


class MailboxRetentionManager:
    """Manages cleanup and retention of automated CareerOps emails in Gmail."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        load_dotenv("/u01/CareerOps/.env")
        cfg = config or {}
        email_cfg = cfg.get("email", {})
        ret_cfg = cfg.get("retention", {})

        self.host = os.environ.get("IMAP_HOST", email_cfg.get("imap_host", "imap.gmail.com"))
        self.port = int(os.environ.get("IMAP_PORT", email_cfg.get("imap_port", 993)))
        self.username = os.environ.get("SMTP_USERNAME", email_cfg.get("username", "sauravskt8@gmail.com"))
        self.password = os.environ.get("SMTP_PASSWORD", email_cfg.get("password", ""))

        self.max_keep = int(ret_cfg.get("max_careerops_emails_per_folder", 3))
        self.enabled = bool(ret_cfg.get("mailbox_retention_enabled", True)) and bool(ret_cfg.get("enabled", True))
        self.purge_trash_enabled = bool(ret_cfg.get("purge_trash", True))

    def _is_careerops_report(self, subject: str, sender: str, to: str) -> bool:
        """Strictly matches automated system reports while protecting recruiter communications."""
        subj_clean = subject.replace("—", "-").replace("–", "-").lower()
        sender_lower = sender.lower()
        to_lower = to.lower()

        # Recruiter / External Communication Protection Barrier
        # Never match or touch recruiter communications, even if they reference CareerOps
        if any(term in sender_lower or term in subj_clean for term in [
            "apexit", "shubendu", "ltm", "ltmindtree", "juili", "recruiter",
            "hr", "hiring", "talent acquisition", "interview invitation"
        ]):
            return False

        # Must match CareerOps automated report signature
        is_careerops_subj = (
            "careerops" in subj_clean
            or "career agent" in subj_clean
        )

        is_system_sender = (
            "autonomous career agent" in sender_lower
            or (self.username.lower() in sender_lower and self.username.lower() in to_lower)
        )

        return is_careerops_subj and is_system_sender

    def clean_folder(self, mail: imaplib.IMAP4_SSL, folder: str, dry_run: bool = False) -> Dict[str, Any]:
        """Enforces retention on a specific folder, keeping at most self.max_keep latest CareerOps emails."""
        stats = {
            "folder": folder,
            "total_found": 0,
            "deleted": 0,
            "retained": 0,
            "deleted_subjects": [],
            "retained_subjects": [],
        }

        try:
            status, _ = mail.select(f'"{folder}"')
            if status != "OK":
                logger.warning(f"Could not select folder '{folder}'. Status: {status}")
                return stats

            # Server-side search for potential CareerOps emails by Subject
            res, data = mail.uid("SEARCH", None, 'SUBJECT', '"CareerOps"')
            uids = data[0].split() if (data and data[0]) else []

            # Also search for "Career Agent" to catch legacy weekly reports
            res2, data2 = mail.uid("SEARCH", None, 'SUBJECT', '"Career Agent"')
            uids_agent = data2[0].split() if (data2 and data2[0]) else []
            all_uids = list(dict.fromkeys(uids + uids_agent))  # Preserve order, unique

            if not all_uids:
                logger.info(f"No CareerOps emails found in folder '{folder}'.")
                return stats

            # Fetch headers in bulk
            id_set = b",".join(all_uids)
            res, fetch_data = mail.uid("FETCH", id_set, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM TO)])")

            matched_items: List[Tuple[bytes, datetime, str]] = []
            for item in fetch_data:
                if not isinstance(item, tuple):
                    continue
                raw_hdr = item[1].decode("utf-8", errors="ignore")
                hdr_msg = email.message_from_string(raw_hdr)

                # Decode subject
                subj_raw = hdr_msg.get("Subject", "")
                subject = ""
                for part, enc in decode_header(subj_raw):
                    if isinstance(part, bytes):
                        subject += part.decode(enc or "utf-8", errors="ignore")
                    else:
                        subject += str(part)

                sender = hdr_msg.get("From", "")
                to = hdr_msg.get("To", "")
                date_str = hdr_msg.get("Date", "")

                # Extract UID from fetch response header
                # e.g., b'123 (UID 456 BODY[HEADER...]'
                uid = None
                try:
                    resp_line = item[0].decode("utf-8", errors="ignore")
                    m_uid = re.search(r"UID\s+(\d+)", resp_line, re.IGNORECASE)
                    if m_uid:
                        uid = m_uid.group(1).encode("utf-8")
                except Exception:
                    pass

                if not uid:
                    continue

                if self._is_careerops_report(subject, sender, to):
                    try:
                        msg_date = parsedate_to_datetime(date_str)
                        if msg_date.tzinfo is None:
                            msg_date = msg_date.replace(tzinfo=timezone.utc)
                    except Exception:
                        msg_date = datetime.min.replace(tzinfo=timezone.utc)
                    matched_items.append((uid, msg_date, subject))

            # Sort chronologically by date ASC (oldest first, newest last)
            matched_items.sort(key=lambda x: x[1])
            stats["total_found"] = len(matched_items)

            if len(matched_items) <= self.max_keep:
                logger.info(f"Folder '{folder}' has {len(matched_items)} CareerOps emails (within <= {self.max_keep} retention limit). No deletion needed.")
                stats["retained"] = len(matched_items)
                stats["retained_subjects"] = [f"{x[1].strftime('%Y-%m-%d')} | {x[2]}" for x in matched_items]
                return stats

            # Split into items to delete (oldest) and items to keep (newest max_keep)
            num_to_delete = len(matched_items) - self.max_keep
            to_delete = matched_items[:num_to_delete]
            to_keep = matched_items[num_to_delete:]

            stats["retained"] = len(to_keep)
            stats["retained_subjects"] = [f"{x[1].strftime('%Y-%m-%d')} | {x[2]}" for x in to_keep]

            logger.info(f"Folder '{folder}': Found {len(matched_items)} CareerOps emails. Retaining latest {len(to_keep)}, deleting {len(to_delete)} older emails.")

            uids_to_delete = [x[0] for x in to_delete]
            stats["deleted_subjects"] = [f"{x[1].strftime('%Y-%m-%d')} | {x[2]}" for x in to_delete]

            if not dry_run and uids_to_delete:
                # Batch delete in chunks of 50 to prevent IMAP command line buffer limits
                chunk_size = 50
                for i in range(0, len(uids_to_delete), chunk_size):
                    chunk = uids_to_delete[i:i + chunk_size]
                    chunk_bytes = b",".join(chunk)

                    # Move to Trash/Bin in Gmail IMAP
                    mail.uid("COPY", chunk_bytes, TRASH_FOLDER)
                    mail.uid("STORE", chunk_bytes, "+FLAGS", "(\\Deleted)")

                mail.expunge()
                stats["deleted"] = len(uids_to_delete)
                logger.info(f"Successfully purged {len(uids_to_delete)} CareerOps emails from '{folder}' to {TRASH_FOLDER}.")
            else:
                stats["deleted"] = len(uids_to_delete)
                logger.info(f"[DRY RUN] Would purge {len(uids_to_delete)} CareerOps emails from '{folder}'.")

        except Exception as exc:
            logger.error(f"Error enforcing mailbox retention on '{folder}': {exc}", exc_info=True)

        return stats

    def purge_trash(self, mail: imaplib.IMAP4_SSL, dry_run: bool = False) -> Dict[str, Any]:
        """Permanently deletes CareerOps report emails from [Gmail]/Bin (Trash)."""
        stats = {
            "folder": "[Gmail]/Bin",
            "total_found": 0,
            "permanently_deleted": 0,
            "deleted_subjects": [],
        }

        try:
            status, _ = mail.select('"[Gmail]/Bin"')
            if status != "OK":
                logger.warning(f"Could not select '[Gmail]/Bin'. Status: {status}")
                return stats

            # Server-side search for CareerOps emails in Bin
            res, data = mail.uid("SEARCH", None, 'SUBJECT', '"CareerOps"')
            uids = data[0].split() if (data and data[0]) else []

            res2, data2 = mail.uid("SEARCH", None, 'SUBJECT', '"Career Agent"')
            uids_agent = data2[0].split() if (data2 and data2[0]) else []
            all_uids = list(dict.fromkeys(uids + uids_agent))

            if not all_uids:
                logger.info("No CareerOps emails found in [Gmail]/Bin to purge.")
                return stats

            # Fetch headers in bulk to verify against protection rules
            id_set = b",".join(all_uids)
            res, fetch_data = mail.uid("FETCH", id_set, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE FROM TO)])")

            uids_to_purge = []
            for item in fetch_data:
                if not isinstance(item, tuple):
                    continue
                raw_hdr = item[1].decode("utf-8", errors="ignore")
                hdr_msg = email.message_from_string(raw_hdr)

                subj_raw = hdr_msg.get("Subject", "")
                subject = ""
                for part, enc in decode_header(subj_raw):
                    if isinstance(part, bytes):
                        subject += part.decode(enc or "utf-8", errors="ignore")
                    else:
                        subject += str(part)

                sender = hdr_msg.get("From", "")
                to = hdr_msg.get("To", "")
                date_str = hdr_msg.get("Date", "")

                uid = None
                try:
                    resp_line = item[0].decode("utf-8", errors="ignore")
                    m_uid = re.search(r"UID\s+(\d+)", resp_line, re.IGNORECASE)
                    if m_uid:
                        uid = m_uid.group(1).encode("utf-8")
                except Exception:
                    pass

                if uid and self._is_careerops_report(subject, sender, to):
                    uids_to_purge.append(uid)
                    stats["deleted_subjects"].append(f"{date_str[:25]} | {subject}")

            stats["total_found"] = len(uids_to_purge)
            if not uids_to_purge:
                logger.info("No matching CareerOps report emails to permanently purge from [Gmail]/Bin.")
                return stats

            logger.info(f"[Gmail]/Bin: Found {len(uids_to_purge)} CareerOps emails to permanently purge (DRY_RUN={dry_run}).")

            if not dry_run and uids_to_purge:
                chunk_size = 50
                for i in range(0, len(uids_to_purge), chunk_size):
                    chunk = uids_to_purge[i:i + chunk_size]
                    chunk_bytes = b",".join(chunk)
                    mail.uid("STORE", chunk_bytes, "+FLAGS", "(\\Deleted)")

                mail.expunge()
                stats["permanently_deleted"] = len(uids_to_purge)
                logger.info(f"Permanently expunged {len(uids_to_purge)} CareerOps emails from [Gmail]/Bin.")
            else:
                stats["permanently_deleted"] = len(uids_to_purge)
                logger.info(f"[DRY RUN] Would permanently expunge {len(uids_to_purge)} CareerOps emails from [Gmail]/Bin.")

        except Exception as exc:
            logger.error(f"Error purging [Gmail]/Bin: {exc}", exc_info=True)

        return stats

    def apply_retention(self, dry_run: bool = False) -> Dict[str, Any]:
        """Runs retention enforcement across INBOX, [Gmail]/Sent Mail, and permanently purges [Gmail]/Bin."""
        if not self.enabled:
            logger.info("Mailbox retention policy is disabled by configuration.")
            return {"status": "DISABLED", "folders": {}}

        if not self.username or not self.password:
            logger.warning("IMAP credentials not configured. Skipping mailbox retention.")
            return {"status": "CREDENTIALS_MISSING", "folders": {}}

        logger.info(f"Starting Gmail Mailbox Retention Enforcement (Keep at most {self.max_keep} latest CareerOps emails per folder, DRY_RUN={dry_run})...")

        results = {}
        mail = None
        try:
            mail = imaplib.IMAP4_SSL(self.host, self.port)
            mail.login(self.username, self.password)

            for folder in TARGET_FOLDERS:
                folder_stats = self.clean_folder(mail, folder, dry_run=dry_run)
                results[folder] = folder_stats

            if self.purge_trash_enabled:
                trash_stats = self.purge_trash(mail, dry_run=dry_run)
                results["[Gmail]/Bin"] = trash_stats

            total_deleted = sum(f.get("deleted", 0) for f in results.values() if "deleted" in f)
            total_permanently_purged = results.get("[Gmail]/Bin", {}).get("permanently_deleted", 0)
            total_retained = sum(f.get("retained", 0) for f in results.values() if "retained" in f)
            logger.info(f"Mailbox retention completed. Folder purges: {total_deleted}, Trash expunged: {total_permanently_purged}, Retained: {total_retained}")

            return {
                "status": "SUCCESS",
                "dry_run": dry_run,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_deleted": total_deleted,
                "total_permanently_purged": total_permanently_purged,
                "total_retained": total_retained,
                "folders": results,
            }
        except Exception as exc:
            logger.error(f"Failed to execute mailbox retention: {exc}", exc_info=True)
            return {"status": "ERROR", "error": str(exc), "folders": results}
        finally:
            if mail:
                try:
                    mail.close()
                except Exception:
                    pass
                try:
                    mail.logout()
                except Exception:
                    pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mailbox Retention Engine for CareerOps Reports")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and simulate cleanup without deleting")
    parser.add_argument("--max-keep", type=int, default=3, help="Maximum number of latest emails to retain per folder")
    args = parser.parse_args()

    cfg = {"retention": {"max_careerops_emails_per_folder": args.max_keep, "mailbox_retention_enabled": True}}
    manager = MailboxRetentionManager(cfg)
    res = manager.apply_retention(dry_run=args.dry_run)
    print("\n" + "=" * 60)
    print("  CAREEROPS MAILBOX RETENTION SUMMARY")
    print("=" * 60)
    print(f"  Status:         {res.get('status')}")
    print(f"  Total Deleted:  {res.get('total_deleted', 0)}")
    print(f"  Total Retained: {res.get('total_retained', 0)}")
    for f, fstats in res.get("folders", {}).items():
        print(f"\n  Folder: {f}")
        print(f"    Total Found:          {fstats.get('total_found')}")
        if "deleted" in fstats:
            print(f"    Moved to Bin:         {fstats.get('deleted')}")
        if "permanently_deleted" in fstats:
            print(f"    Permanently Expunged: {fstats.get('permanently_deleted')}")
        if "retained" in fstats:
            print(f"    Retained:             {fstats.get('retained')}")
        if fstats.get("retained_subjects"):
            print("    Retained Emails:")
            for s in fstats["retained_subjects"]:
                print(f"      - {s}")
    print("=" * 60 + "\n")
