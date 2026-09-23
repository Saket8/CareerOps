"""Unit tests for ApplicationVerifier covering 5-level confirmation hierarchy and barrier detection."""

import pytest
from src.naukri.verifier import ApplicationVerifier, VerificationEvidence
from src.models.job import JobStatus


def test_verifier_level_1_confirmation_with_ref():
    verifier = ApplicationVerifier()
    html = """
    <html>
        <body>
            <h2>Application submitted successfully!</h2>
            <p>Your application for Cloud Architect was received.</p>
            <div>Application ID: CONF_778899</div>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/apply/success",
        page_title="Application Submitted",
    )
    assert evidence.confirmed is True
    assert evidence.status == JobStatus.APPLIED_CONFIRMED
    assert evidence.verification_level == "LEVEL_1_DIRECT_MODAL"
    assert "CONF_778899" in evidence.confirmation_reference


def test_verifier_level_2_soft_confirmation_unverified():
    verifier = ApplicationVerifier()
    html = """
    <html>
        <body>
            <p>Thank you for applying. We will review your profile shortly.</p>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/apply/thankyou",
        page_title="Thank You",
    )
    # Per tasks/goal.md, soft confirmation without explicit reference is SUBMISSION_UNVERIFIED
    assert evidence.confirmed is False
    assert evidence.status == JobStatus.SUBMISSION_UNVERIFIED
    assert evidence.verification_level == "LEVEL_2_THANK_YOU_MESSAGE"


def test_verifier_level_3_already_applied_state():
    verifier = ApplicationVerifier()
    html = """
    <html>
        <body>
            <button class="applied-btn" disabled>Already Applied</button>
            <p>You have already applied for this vacancy on 2026-09-20.</p>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/job-listings-123",
        page_title="OCI Architect Job",
    )
    assert evidence.confirmed is True
    assert evidence.status == JobStatus.APPLIED_CONFIRMED
    assert evidence.verification_level == "LEVEL_3_BUTTON_ALREADY_APPLIED"


def test_verifier_barrier_captcha_detected():
    verifier = ApplicationVerifier()
    html = """
    <html>
        <body>
            <div id="cf-turnstile">Please verify you are human to proceed</div>
            <iframe src="https://challenges.cloudflare.com"></iframe>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/challenge",
        page_title="Security Check",
    )
    assert evidence.confirmed is False
    assert evidence.status == JobStatus.APPLICATION_BLOCKED
    assert evidence.verification_level == "BARRIER_CAPTCHA"


def test_verifier_barrier_login_required():
    verifier = ApplicationVerifier()
    html = """
    <html>
        <body>
            <div class="login-layer">
                <h2>Login to Apply</h2>
                <input type="text" placeholder="Enter your email ID" />
            </div>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/login",
        page_title="Candidate Login",
    )
    assert evidence.confirmed is False
    assert evidence.status == JobStatus.NEEDS_MANUAL_INTERVENTION
    assert evidence.verification_level == "BARRIER_LOGIN"


def test_verifier_barrier_external_ats_redirect():
    verifier = ApplicationVerifier()
    html = """
    <html>
        <body>
            <h1>Welcome to Workday Career Portal</h1>
            <p>Apply for Oracle Cloud Architect</p>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://oracle.wd3.myworkdayjobs.com/careers/job/123",
        page_title="Workday Jobs",
    )
    assert evidence.confirmed is False
    assert evidence.status == JobStatus.EXTERNAL_APPLICATION_REQUIRED
    assert evidence.verification_level == "BARRIER_EXTERNAL_ATS"


def test_verifier_unverified_generic_page():
    verifier = ApplicationVerifier()
    html = """
    <html>
        <body>
            <p>Naukri Search Results for Cloud Architect</p>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/jobs",
        page_title="Naukri Jobs",
    )
    assert evidence.confirmed is False
    assert evidence.status == JobStatus.SUBMISSION_UNVERIFIED
    assert evidence.verification_level == "NO_CONFIRMATION_FOUND"


def test_verifier_loose_text_without_badge_or_ref_demoted_to_unverified():
    verifier = ApplicationVerifier()
    # Has confirmation words, but NO badge and NO reference ID
    html = """
    <html>
        <body>
            <h1>Careers FAQ</h1>
            <p>Your application was submitted successfully in our previous system.</p>
            <p>For questions you have already applied to, please check your inbox.</p>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/faq",
        page_title="FAQ",
    )
    assert evidence.confirmed is False
    assert evidence.status == JobStatus.SUBMISSION_UNVERIFIED
    assert evidence.verification_level == "HEURISTIC_TEXT_UNVERIFIED"


def test_verifier_no_false_login_barrier_on_authenticated_page():
    verifier = ApplicationVerifier()
    # Real authenticated listing page with footer links like "Candidate Login" and hidden login layer
    html = """
    <html>
        <head><title>Architect - Generative AI - Nagarro - Bengaluru</title></head>
        <body>
            <div class="job-header">
                <h1>Architect- Generative AI</h1>
                <div class="company-name">Nagarro</div>
                <button class="applied-btn already-applied"><span class="already-applied">Already Applied</span></button>
            </div>
            <div class="login-layer" style="display:none"></div>
            <footer>
                <a href="/nlogin/login">Candidate Login</a>
                <a href="/employer/login">Employer Login</a>
            </footer>
        </body>
    </html>
    """
    evidence = verifier.verify_submission(
        page_content=html,
        final_url="https://www.naukri.com/job-listings-architect-generative-ai-nagarro-bengaluru-020926022745",
        page_title="Architect - Generative AI - Nagarro - Bengaluru",
    )
    assert evidence.confirmed is True
    assert evidence.status == JobStatus.APPLIED_CONFIRMED
    assert evidence.verification_level == "LEVEL_3_BUTTON_ALREADY_APPLIED"
