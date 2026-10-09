import os
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv("/u01/CareerOps/.env")

LI_AT = os.environ.get("LINKEDIN_LI_AT", "")
USER_DATA_DIR = "/u01/CareerOps/artifacts/chrome_linkedin_profile"
AUTH_STATE_FILE = Path("/u01/CareerOps/artifacts/linkedin_auth.json")
EVIDENCE_DIR = Path("/u01/CareerOps/artifacts/evidence")
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

print(f"Headline char count: {len(HEADLINE)} / 220")
print(f"About char count: {len(ABOUT)} / 2600")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled'],
        viewport={'width': 1440, 'height': 900}
    )
    
    # Inject li_at cookie
    context.add_cookies([{
        'name': 'li_at',
        'value': LI_AT,
        'domain': '.www.linkedin.com',
        'path': '/',
        'httpOnly': True,
        'secure': True,
        'sameSite': 'None'
    }, {
        'name': 'li_at',
        'value': LI_AT,
        'domain': '.linkedin.com',
        'path': '/',
        'httpOnly': True,
        'secure': True,
        'sameSite': 'None'
    }])
    
    page = context.new_page()
    
    print("\n--- Step 1: Verifying Authenticated Session ---")
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=40000)
    time.sleep(5)
    print("Feed URL:", page.url)
    print("Feed Title:", page.title())
    
    page.screenshot(path=str(EVIDENCE_DIR / "linkedin_feed_authenticated.png"))
    print("Saved evidence: artifacts/evidence/linkedin_feed_authenticated.png")
    
    # Save auth state
    context.storage_state(path=str(AUTH_STATE_FILE))
    print("Exported storage state to", AUTH_STATE_FILE)

    print("\n--- Step 2: Checking & Enforcing Stealth Privacy Toggle ---")
    # LinkedIn privacy settings for sharing profile edits
    page.goto("https://www.linkedin.com/mypreferences/d/settings/privacy", wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    print("Privacy settings URL:", page.url)
    page.screenshot(path=str(EVIDENCE_DIR / "linkedin_privacy_settings.png"))
    
    context.close()
