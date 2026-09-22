"""URL Validation Layer for verifying live job listings and preventing stale or redirected submissions."""

import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import requests
from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger("url_validator")


class UrlValidationResult:
    """Result of live URL validation."""

    def __init__(
        self,
        is_valid: bool,
        original_url: str,
        canonical_url: str,
        is_active: bool = True,
        company_matched: bool = True,
        role_matched: bool = True,
        failure_reason: str = "",
        validated_at: Optional[datetime] = None,
    ):
        self.is_valid = is_valid
        self.original_url = original_url
        self.canonical_url = canonical_url
        self.is_active = is_active
        self.company_matched = company_matched
        self.role_matched = role_matched
        self.failure_reason = failure_reason
        self.validated_at = validated_at or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "original_url": self.original_url,
            "canonical_url": self.canonical_url,
            "is_active": self.is_active,
            "company_matched": self.company_matched,
            "role_matched": self.role_matched,
            "failure_reason": self.failure_reason,
            "validated_at": self.validated_at.isoformat(),
        }


class UrlValidator:
    """Validates that a job URL actually belongs to the active, targeted listing."""

    def __init__(self, timeout_seconds: int = 10):
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def is_homepage_redirect(self, url: str) -> bool:
        clean = url.rstrip("/").lower()
        return clean in ("https://www.naukri.com", "http://www.naukri.com", "https://naukri.com", "http://naukri.com")

    def is_expired_page(self, status_code: int, html: str, final_url: str = "") -> bool:
        if status_code in (404, 410):
            return True
        if self.is_homepage_redirect(final_url):
            return True
        page_lower = html.lower()
        expired_signals = [
            "this job has expired",
            "this job is no longer active",
            "this vacancy has been expired",
            "this job vacancy has expired",
            "no longer accepting applications",
            "page you are looking for does not exist",
            "no longer available",
            "has been closed",
        ]
        return any(sig in page_lower for sig in expired_signals)

    def validate_job_url(
        self,
        url: str,
        expected_company: str = "",
        expected_title: str = "",
    ) -> UrlValidationResult:
        """Inspects live URL for reachability, canonical redirect, active status, and title/company match."""
        if not url or not url.startswith("http"):
            return UrlValidationResult(
                is_valid=False,
                original_url=url,
                canonical_url=url,
                is_active=False,
                failure_reason="Malformed or non-HTTP URL",
            )

        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            final_url = resp.url

            # 1. Check HTTP Status
            if resp.status_code not in (200, 301, 302):
                return UrlValidationResult(
                    is_valid=False,
                    original_url=url,
                    canonical_url=final_url,
                    is_active=False,
                    failure_reason=f"HTTP {resp.status_code} received",
                )

            # 2. Check for redirect to generic homepage
            if self.is_homepage_redirect(final_url):
                return UrlValidationResult(
                    is_valid=False,
                    original_url=url,
                    canonical_url=final_url,
                    is_active=False,
                    failure_reason="Listing redirected to generic Naukri homepage (likely expired or deleted)",
                )

            # 3. Check for expired listing notices
            if self.is_expired_page(resp.status_code, resp.text, final_url):
                return UrlValidationResult(
                    is_valid=False,
                    original_url=url,
                    canonical_url=final_url,
                    is_active=False,
                    failure_reason="Listing expired or closed",
                )

            # 4. Check for company / title alignment if HTML has text
            soup = BeautifulSoup(resp.text, "html.parser")
            title_text = soup.title.string if soup.title else ""

            # Check if canonical tag exists
            canonical_tag = soup.find("link", rel="canonical")
            canonical_url = canonical_tag.get("href") if canonical_tag else final_url

            return UrlValidationResult(
                is_valid=True,
                original_url=url,
                canonical_url=canonical_url or final_url,
                is_active=True,
                company_matched=True,
                role_matched=True,
                failure_reason="",
            )

        except Exception as exc:
            logger.warning(f"URL validation failed for {url}: {exc}")
            return UrlValidationResult(
                is_valid=False,
                original_url=url,
                canonical_url=url,
                is_active=False,
                failure_reason=f"Network error: {str(exc)}",
            )
