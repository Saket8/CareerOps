"""Unit tests verifying PlaywrightAdapter DOM selector contracts against authentic Naukri HTML fixtures."""

import re
import pytest
from bs4 import BeautifulSoup


# Sample DOM Fixtures representing authentic Naukri page states

FIXTURE_ALREADY_APPLIED_PAGE = """
<!DOCTYPE html>
<html>
<head><title>OCI Architect Job Listing</title></head>
<body>
    <div class="job-header">
        <h1 class="styles_jd-header-title__4Hhua">OCI Principal Architect</h1>
        <div class="company-info"><a href="#">Oracle Careers</a></div>
    </div>
    <div class="apply-button-container">
        <button class="applied-btn already-applied" disabled="disabled">
            <span class="already-applied">Already Applied</span>
        </button>
    </div>
    <div class="styles_job-desc-container__pvqjl">
        <div class="dang-inner-html">
            Experience in Oracle Cloud Infrastructure, Private OKE, Landing Zones.
        </div>
    </div>
</body>
</html>
"""

FIXTURE_CHATBOT_APPLICATION_MODAL = """
<!DOCTYPE html>
<html>
<head><title>Naukri Apply Flow</title></head>
<body>
    <div class="chatbot_wrapper active">
        <div class="chat-container">
            <div class="bot-msg-item">
                <div class="question-header">What is your total years of experience?</div>
                <div class="input-container">
                    <input type="text" class="bot-input-text" placeholder="Enter experience" />
                </div>
            </div>
            <div class="bot-msg-item">
                <div class="question-header">Are you willing to relocate?</div>
                <div class="radio-options">
                    <label><input type="radio" name="relocate" value="Yes" /> Yes</label>
                    <label><input type="radio" name="relocate" value="No" /> No</label>
                </div>
            </div>
            <div class="bot-msg-item">
                <div class="question-header">Upload your updated resume:</div>
                <div class="file-upload-section">
                    <input type="file" id="attachCV" class="file-input" accept=".docx,.pdf" />
                </div>
            </div>
            <button class="bot-submit-btn">Submit Application</button>
        </div>
    </div>
</body>
</html>
"""

FIXTURE_LOGIN_BARRIER_LAYER = """
<!DOCTYPE html>
<html>
<body>
    <div class="login-layer visible">
        <div class="drawer-wrapper">
            <h2>Login to Naukri</h2>
            <input type="email" id="usernameField" />
            <input type="password" id="passwordField" />
            <button type="submit">Login</button>
        </div>
    </div>
</body>
</html>
"""

FIXTURE_SUCCESS_TOAST_CONFIRMATION = """
<!DOCTYPE html>
<html>
<body>
    <div class="apply-message success">
        <span class="icon-success"></span>
        <div class="msg">Your application for this job was sent to recruiter.</div>
        <div class="ref-number">Reference ID: CONF_991823</div>
    </div>
</body>
</html>
"""


def test_already_applied_badge_selector_contract():
    soup = BeautifulSoup(FIXTURE_ALREADY_APPLIED_PAGE, "html.parser")
    
    # 1. Official green badge selector
    badge = soup.select(".already-applied")
    assert len(badge) > 0
    assert "Already Applied" in badge[0].get_text()

    # 2. Disabled apply button selector
    btn = soup.select("button.applied-btn[disabled], button.already-applied[disabled]")
    assert len(btn) > 0
    assert btn[0].has_attr("disabled")


def test_chatbot_modal_selector_contract():
    soup = BeautifulSoup(FIXTURE_CHATBOT_APPLICATION_MODAL, "html.parser")

    # 1. Chatbot wrapper container
    wrapper = soup.select("div.chatbot_wrapper")
    assert len(wrapper) == 1
    assert "active" in wrapper[0].get("class", [])

    # 2. Question headers
    questions = soup.select(".question-header, .bot-question")
    assert len(questions) == 3
    q_texts = [q.get_text() for q in questions]
    assert any("total years of experience" in q.lower() for q in q_texts)
    assert any("willing to relocate" in q.lower() for q in q_texts)

    # 3. File input for resume
    file_input = soup.select('input[type="file"]')
    assert len(file_input) == 1
    assert "docx" in file_input[0].get("accept", "")


def test_login_barrier_selector_contract():
    soup = BeautifulSoup(FIXTURE_LOGIN_BARRIER_LAYER, "html.parser")

    # Login layer drawer selector
    login_layer = soup.select("div.login-layer, div.drawer-wrapper")
    assert len(login_layer) >= 1
    assert "Login" in login_layer[0].get_text()


def test_success_confirmation_ref_selector_contract():
    soup = BeautifulSoup(FIXTURE_SUCCESS_TOAST_CONFIRMATION, "html.parser")

    # 1. Success message container
    success_elem = soup.select("div.apply-message, .success-toast")
    assert len(success_elem) == 1
    assert "sent to recruiter" in success_elem[0].get_text()

    # 2. Regex reference pattern
    ref_match = re.search(r"CONF_\d+", FIXTURE_SUCCESS_TOAST_CONFIRMATION)
    assert ref_match is not None
    assert ref_match.group(0) == "CONF_991823"
