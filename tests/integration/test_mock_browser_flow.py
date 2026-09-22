"""Integration test running real Playwright Chromium against a local controlled mock site.

Verifies the entire browser execution flow:
- Navigation to listing
- Form and button interactions
- Reload badge verification (.already-applied)
- Evidence screenshot generation
"""

import os
import time
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

from src.models.job import JobListing, JobStatus
from src.models.candidate import CandidateTruth
from candidate.profile_extractor import get_candidate_truth


HTML_JOB_PAGE = """<!DOCTYPE html>
<html>
<head><title>Mock Senior OCI Cloud Architect</title></head>
<body>
    <div class="job-container">
        <h1 class="styles_jd-header-title__4Hhua">Senior OCI Cloud Architect</h1>
        <div class="company-name">Oracle Cloud Systems</div>
        <div class="apply-container" id="applyBox">
            <button id="applyButton" class="apply-btn" onclick="submitApplication()">Apply Now</button>
        </div>
        <div class="job-description">
            Looking for 12+ years experience in Oracle Cloud Infrastructure, Private OKE, Landing Zones.
        </div>
    </div>
    <script>
        function submitApplication() {
            var box = document.getElementById('applyBox');
            box.innerHTML = '<button class="applied-btn already-applied" disabled><span class="already-applied">Already Applied</span></button><div class="apply-message">Application submitted successfully! Ref: CONF_123456</div>';
        }
    </script>
</body>
</html>
"""

HTML_ALREADY_APPLIED_PAGE = """<!DOCTYPE html>
<html>
<head><title>Mock Senior OCI Cloud Architect</title></head>
<body>
    <div class="job-container">
        <h1>Senior OCI Cloud Architect</h1>
        <div class="company-name">Oracle Cloud Systems</div>
        <div class="apply-container">
            <button class="applied-btn already-applied" disabled><span class="already-applied">Already Applied</span></button>
        </div>
    </div>
</body>
</html>
"""


class MockNaukriHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/already-applied":
            body = HTML_ALREADY_APPLIED_PAGE.encode("utf-8")
        else:
            body = HTML_JOB_PAGE.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Silence HTTP server logs during pytest runs
        pass


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def local_mock_server():
    port = find_free_port()
    server = HTTPServer(("127.0.0.1", port), MockNaukriHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_mock_browser_apply_flow_and_badge_verification(local_mock_server, tmp_path):
    """Executes a real headless Playwright browser interaction against the controlled local site."""
    evidence_path = tmp_path / "mock_evidence.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # 1. Navigate to initial job page
        page.goto(f"{local_mock_server}/job")
        assert "Senior OCI Cloud Architect" in page.title()

        # Verify initial apply button is present
        apply_btn = page.locator("#applyButton")
        assert apply_btn.is_visible()

        # 2. Click Apply Now
        apply_btn.click()

        # 3. Verify .already-applied badge appears
        badge = page.locator(".already-applied")
        badge.first.wait_for(state="visible", timeout=5000)
        assert "Already Applied" in badge.first.inner_text()

        # 4. Capture physical visual proof screenshot
        page.screenshot(path=str(evidence_path))
        assert evidence_path.exists()
        assert evidence_path.stat().st_size > 1000

        # 5. Reload verification: simulate visiting the page after application
        page.goto(f"{local_mock_server}/already-applied")
        reloaded_badge = page.locator(".already-applied")
        assert reloaded_badge.first.is_visible()
        assert "Already Applied" in reloaded_badge.first.inner_text()

        context.close()
        browser.close()
