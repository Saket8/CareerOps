"""Unit tests for UrlValidator covering reachability, redirects, and job status checks."""

from unittest.mock import MagicMock
import pytest
from src.naukri.url_validator import UrlValidator, UrlValidationResult


def test_url_validator_valid_naukri_url():
    validator = UrlValidator()
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://www.naukri.com/job-listings-oracle-cloud-infrastructure-architect-oracle-india-12345"
    mock_resp.text = "<html><head><title>Oracle Cloud Architect - Oracle India</title></head><body><h1>Job Description</h1></body></html>"
    validator.session.get = MagicMock(return_value=mock_resp)

    result = validator.validate_job_url(
        url="https://www.naukri.com/job-listings-oracle-cloud-infrastructure-architect-oracle-india-12345",
        expected_company="Oracle India",
        expected_title="Oracle Cloud Infrastructure Architect",
    )
    assert result.is_valid is True
    assert "naukri.com" in result.canonical_url
    assert result.is_active is True


def test_url_validator_invalid_scheme():
    validator = UrlValidator()
    result = validator.validate_job_url("ftp://naukri.com/job/123")
    assert result.is_valid is False
    assert "Malformed" in result.failure_reason


def test_url_validator_empty_url():
    validator = UrlValidator()
    result = validator.validate_job_url("")
    assert result.is_valid is False
    assert "Malformed" in result.failure_reason


def test_url_validator_expired_status_codes():
    validator = UrlValidator()
    assert validator.is_expired_page(status_code=404, html="", final_url="https://naukri.com/job/1") is True
    assert validator.is_expired_page(status_code=410, html="", final_url="https://naukri.com/job/1") is True


def test_url_validator_expired_html_content():
    validator = UrlValidator()
    expired_html = "<html><body><h1>This vacancy is no longer available</h1></body></html>"
    assert validator.is_expired_page(status_code=200, html=expired_html, final_url="https://naukri.com/job/1") is True

    closed_html = "<html><body><p>This job opening has been closed by the recruiter.</p></body></html>"
    assert validator.is_expired_page(status_code=200, html=closed_html, final_url="https://naukri.com/job/1") is True


def test_url_validator_homepage_redirect():
    validator = UrlValidator()
    assert validator.is_homepage_redirect("https://www.naukri.com") is True
    assert validator.is_homepage_redirect("https://www.naukri.com/") is True
    assert validator.is_homepage_redirect("https://www.naukri.com/job-listings-123") is False
