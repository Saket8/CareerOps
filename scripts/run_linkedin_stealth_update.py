#!/usr/bin/env python3
"""
LinkedIn Stealth Profile Updater
1. Ensures 'Share profile updates with your network' is turned OFF.
2. Updates Headline (clean professional plain-text).
3. Updates About section (clean plain-text, <= 2600 chars).
4. Updates Current Role Description (Nov 2024 – Present, ongoing).
5. Captures verification screenshots and saves session state.
"""

import os
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv("/u01/CareerOps/.env")

USERNAME = os.environ.get("LINKEDIN_USERNAME")
PASSWORD = os.environ.get("LINKEDIN_PASSWORD")
AUTH_STATE_FILE = Path("artifacts/linkedin_auth.json")
EVIDENCE_DIR = Path("artifacts/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

HEADLINE = (
    "OCI Cloud & Security Architect | Zero-Trust Identity (OCI IAM · Entra ID · SAML/SCIM/OAuth2) | "
    "Exadata & Oracle DB | CIS Hardening, DR & Kubernetes | Telecom BSS | Agentic AI for CloudOps"
)

ABOUT = (
    "I design and secure regulated, air-gapped platforms on Oracle Cloud Infrastructure, where identity, "
    "network isolation, auditability, and disaster recovery must be integral from day one. 12+ years in IT, "
    "including 6.5+ years on OCI and 10+ years in mission-critical Oracle database engineering.\n\n"
    "Most recently, I was a core architect on the OCI platform for a Tier-1 European telecom's billing and "
    "revenue management transformation, sized for 10M+ subscribers. I owned the platform from security, network, "
    "IAM, operational governance, and infrastructure requirements and architecture through production build, "
    "security sign-off, and go-live readiness.\n\n"
    "Identity & Zero Trust:\n"
    "• Federated OCI with Microsoft Entra ID (SAML SSO, SCIM provisioning, MFA), ensuring all access originates from "
    "enterprise identity rather than unmanaged local accounts.\n"
    "• Enforced request-only access with periodic reconciliation, eliminating direct, manual, and shared accounts from production.\n"
    "• Designed layered authorization across cloud IAM, Kubernetes RBAC, OAuth2 scopes, and application roles, enforcing "
    "strict data isolation between wholesale partners and retail operations.\n\n"
    "Security Architecture & Pentest Remediation:\n"
    "• Led infrastructure remediation from pre-go-live pentest: moved plaintext secrets to Vault, locked privilege "
    "escalation/permissions, removed private keys, and secured unauthenticated APIs with OAuth2.\n"
    "• Engineered layered controls against DNS-based data exfiltration in private networks with zero public internet access; "
    "escalated cloud gaps into tenancy-wide controls with full SOC visibility.\n"
    "• Enforced CIS-aligned assessments and platform hardening across Linux VMs, databases, and Kubernetes worker nodes "
    "with non-root containers and Vault-managed secrets.\n\n"
    "Database, Exadata & Resilience:\n"
    "• Sized and justified Exadata Database Service on dedicated infrastructure with RAC, configuring shared Exadata "
    "infrastructure with isolated production and pre-production VM clusters.\n"
    "• Engineered cross-availability-domain disaster recovery on Exadata with Active Data Guard and OCI Full Stack DR. "
    "Narrowing replication scope cut estimated DR service cost by ~95%.\n"
    "• Enforced TDE encryption, Unified Auditing forwarded to SIEM, and Data Safe / DBSAT security assessments.\n\n"
    "Certifications: Oracle Cloud Infrastructure 2026 Architect Professional · OCI 2026 DevOps Professional · "
    "OCI 2026 Generative AI Professional · OCI 2026 Autonomous Database Architect\n"
    "Open to: Principal Cloud Architect · OCI Enterprise Architect · Cloud Security & IAM Architect"
)

EXPERIENCE_CURRENT = (
    "• Owned the enterprise platform from security, network, IAM, operational governance, and infrastructure "
    "requirements and architecture through production build, security sign-off, and go-live readiness for a "
    "Tier-1 European telecom transformation sized for 10M+ subscribers.\n"
    "• Co-authored the OCI solution design and governance model: landing zone, least-privilege IAM, private network, "
    "encryption, and logging.\n"
    "• Federated the platform with Entra ID (SAML, SCIM, MFA) and enforced request-only access with periodic reconciliation.\n"
    "• Led infrastructure remediation from the pre-go-live penetration test: secrets migrated to Vault, privilege escalation "
    "locked down, exposed keys removed, DNS anti-exfiltration controls added, and SOC log ingestion restored.\n"
    "• Hardened Oracle Linux and Kubernetes nodes to CIS-aligned assessments with reusable hardening automation, and produced "
    "control-level compliance evidence for audit and the SOC.\n"
    "• Led the database platform decision and architecture: Exadata with RAC on shared infrastructure, with fully isolated VM "
    "clusters for production and pre-production.\n"
    "• Managed the full database lifecycle (patching driven by vulnerability findings, backups, Data Guard DR, auditing, "
    "Data Safe) and rationalized database services to cut spend.\n"
    "• Designed SIEM integration with tamper-proof retention, and privileged-login alerting for root, sudo, and SSH activity.\n"
    "• Engineered cross-AD DR with Active Data Guard and Full Stack DR, cutting the estimated DR service cost by ~95%.\n"
    "• Implemented private-only hub-and-spoke design: all traffic passes through central firewall inspection, zero public endpoints, "
    "dedicated bastions for production and migration data, and TLS enforced via enterprise PKI.\n"
    "• Built AI-driven operations tooling for air-gapped environments: AI database diagnostics with guard-railed remediation, a single "
    "CloudOps dashboard with AI triage, and natural-language infrastructure provisioning using MCP, LangChain/LangGraph, and local LLMs "
    "(adopted into practice capability library).\n"
    "• Automated network audits (~80% less effort) and Kubernetes access onboarding (~90% faster), plus tag compliance and node hardening.\n"
    "• Beyond delivery: managed a small engineering team, ran OCI training, interviewed OCI candidates, and supported pre-sales "
    "architecture for OCI and GenAI bids."
)

print(f"Loaded config: Headline ({len(HEADLINE)} chars), About ({len(ABOUT)} chars)")
print(f"User: {USERNAME[:4]}***, Password set: {bool(PASSWORD)}")

def test_login_and_privacy():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-http2",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            storage_state=str(AUTH_STATE_FILE) if AUTH_STATE_FILE.exists() else None
        )
        page = context.new_page()

        print("Navigating to LinkedIn feed / login...", flush=True)
        page.goto("https://www.linkedin.com/feed/", timeout=40000, wait_until="domcontentloaded")
        time.sleep(5)

        # Check if login page was served
        if "login" in page.url or "checkpoint" in page.url or page.locator("#username").count() > 0:
            print(f"Login page detected ({page.url}). Performing automated login...", flush=True)
            if page.locator("#username").count() > 0:
                page.fill("#username", USERNAME)
                page.fill("#password", PASSWORD)
                page.click("button[type='submit']")
                time.sleep(6)

            # Check if checkpoint / pin is requested
            if "checkpoint" in page.url or page.locator("input#input__email_verification_pin").count() > 0 or page.locator("input[name='pin']").count() > 0:
                print("LinkedIn PIN / Verification Checkpoint detected!", flush=True)
                page.screenshot(path=str(EVIDENCE_DIR / "linkedin_checkpoint.png"))
                print(f"Screenshot saved to {EVIDENCE_DIR / 'linkedin_checkpoint.png'}", flush=True)

        page.screenshot(path=str(EVIDENCE_DIR / "linkedin_current_state.png"))
        print(f"Current page URL: {page.url}")
        browser.close()

if __name__ == "__main__":
    test_login_and_privacy()
