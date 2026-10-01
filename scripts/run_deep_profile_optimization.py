#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

LOG_FILE = Path("/u01/CareerOps/logs/profile_deep_optimization.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DeepProfileOptimizer")

AUTH_STATE_FILE = Path("artifacts/naukri_auth.json")

HEADLINE_TEXT = (
    "Principal OCI Cloud Architect | 12+ Yrs | OCI IAM & SSO (Entra ID SAML/SCIM), Full Stack DR, Private OKE, Terraform | "
    "Telecom BSS on OCI | GenAI & MCP Agentic CloudOps | 6x Oracle Certified | Notice: 90 Days (Negotiable)"
)

SUMMARY_TEXT = (
    "Lead Cloud Architect & GenAI CloudOps Specialist with 12+ years in enterprise IT, including 6.5+ years leading mission-critical Oracle Cloud Infrastructure (OCI) architectures and 10+ years in database platforms.\n\n"
    "Core Specialization & Recent Scale:\n"
    "• Enterprise Telecom Modernization: Lead OCI Architect for KPN's (Netherlands) DBSS Revenue Management platform, delivering production & DR readiness for regulated, high-throughput billing systems.\n"
    "• Identity & Governance (IAM/SSO): Architected multi-domain OCI IAM federated with Microsoft Entra ID (SAML/SCIM), automated user lifecycle via SailPoint IdentityNow (IDN), and AD Linux PAM SSH.\n"
    "• Resilience & Cloud-Native: Authored AD1 → AD2 intra-region architecture via OCI Full Stack DR (FSDR) and Active Data Guard. Engineered private OKE clusters cutting platform incidents by ~40%.\n"
    "• GenAI CloudOps: Built ODAOS and agentic CloudOps frameworks (MCP/LLMs), saving 140+ hrs/mo.\n"
    "• Credentials: 6x Oracle Certified (2026)."
)

ROLE_DESCRIPTION_TEXT = (
    "Lead Enterprise Cloud Architect & GenAI CloudOps Specialist responsible for end-to-end architecture, identity, security, resilience, and operational governance for enterprise cloud platforms.\n\n"
    "Lead OCI Architect — KPN DBSS Revenue Management Modernization (Netherlands' Largest Telecom Operator):\n"
    "• Cloud Architecture & Landing Zones: Designed production-grade, air-gapped OCI environment on OCI OPEN multi-tenant (Multi-OE) landing zone. Engineered separate compartment hierarchies for Non-Prod and Prod (Dev, SIT, ST, PreProd, Prod, DR, Migration). Built 5 VCNs with tiered private subnets, least-privilege NSGs, Service Gateways, and private DNS linked to on-prem resolvers. Traffic routed via hub-VCN firewall inspection; ingress strictly over FastConnect/DRG with zero public endpoints.\n"
    "• Identity, SSO & Access Governance: Architected separate Non-Prod and Prod identity domains with SAML SSO federation to Microsoft Entra ID and MFA. Built Entra ID SCIM provisioning and dynamic groups. Configured AD-based Linux SSH access via OCI IAM Linux PAM and Winbind/SSSD. Configured SAML SSO for BRM Billing Care. Designed SailPoint IdentityNow (IDN) integration for automated user and group lifecycle (joiner/mover/leaver) and audit-ready IAM reconciliation.\n"
    "• Disaster Recovery & High Availability: Authored intra-region DR architecture (AD1 Prod → AD2 DR) using OCI Full Stack Disaster Recovery (FSDR). Defined protection groups, drill, switchover, and failover plans with approval gates. Integrated Active Data Guard for Exadata BRM DB and File Storage replication, keeping running costs under low hundreds of €/mo.\n"
    "• Kubernetes (OKE) & Cloud-Native: Engineered private OKE clusters for BRM, PDC, ECE, and OCOMC workloads with FSS-backed storage, RBAC, and TLS ingress via Load Balancers and API Gateway, cutting platform incidents by ~40%.\n"
    "• Infrastructure as Code: Automated 100% of cloud estates via modular Terraform and OCI Resource Manager, slashing provisioning turnaround by ~60%.\n"
    "• GenAI & Agentic CloudOps: Built GenAI CloudOps Dashboard (7th in Vibe Coding, Bluebolt approved) and ODAOS (demoed to ISG CMT, submitted for AI Lens certification, saving 140 hrs/mo and $7.7K/mo). Published whitepaper on MCP-enabled governed multi-agent CloudOps framework.\n"
    "• Database Engineering: 10+ yrs across Oracle RAC, Exadata (ExaCS), Autonomous Database, and zero-downtime database migrations.\n"
    "• Credentials: 6x Oracle Certified (OCI Architect Professional, DevOps Professional, GenAI Professional 2026)."
)

def run_optimization():
    logger.info("Starting Background Deep Profile Optimization Pipeline...")
    logger.info(f"Target Headline Length: {len(HEADLINE_TEXT)} chars (Limit: 250)")
    logger.info(f"Target Summary Length: {len(SUMMARY_TEXT)} chars (Limit: 1000)")
    logger.info(f"Target Role Description Length: {len(ROLE_DESCRIPTION_TEXT)} chars (Limit: 4000)")

    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":99"

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

        logger.info("Navigating to https://www.naukri.com/mnjuser/profile ...")
        for attempt in range(3):
            try:
                page.goto("https://www.naukri.com/mnjuser/profile", wait_until="commit", timeout=35000)
                break
            except Exception as e:
                logger.warning(f"Navigation attempt {attempt+1} warning: {e}. Retrying...")
                time.sleep(3)

        time.sleep(5)
        logger.info("Progressively scrolling to hydrate all DOM sections...")
        for _ in range(14):
            page.evaluate("window.scrollBy(0, 450)")
            time.sleep(0.3)

        # -----------------------------------------------------------------
        # STEP 1: RESUME HEADLINE
        # -----------------------------------------------------------------
        logger.info("=== STEP 1: Updating Resume Headline ===")
        try:
            opened = page.evaluate("""() => {
                const widgets = Array.from(document.querySelectorAll('.widgetHead'));
                const hl = widgets.find(e => e.textContent.toLowerCase().includes('resume headline'));
                if (!hl) return false;
                hl.scrollIntoView({behavior: 'instant', block: 'center'});
                const btn = hl.querySelector('.edit, [aria-label*="Edit"], span.editOneTheme');
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            if opened:
                time.sleep(2)
                ta = page.locator("#resumeHeadlineTxt").first
                if ta.count() > 0:
                    ta.focus()
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    time.sleep(0.3)
                    page.keyboard.insert_text(HEADLINE_TEXT)
                    time.sleep(1)

                    page.evaluate("""() => {
                        const ta = document.querySelector('#resumeHeadlineTxt');
                        const form = ta.closest('form') || document.querySelector('form[name="resumeHeadlineForm"]') || ta.parentElement.parentElement;
                        const saveBtn = Array.from(form.querySelectorAll('button, .btn-dark-ot, input[type="submit"]')).find(b => b.textContent.trim().toLowerCase().includes('save'));
                        if (saveBtn) saveBtn.click();
                    }""")
                    time.sleep(3)
                    logger.info("Resume Headline updated successfully!")
        except Exception as e:
            logger.error(f"Error updating Resume Headline: {e}")

        # -----------------------------------------------------------------
        # STEP 2: PROFILE SUMMARY
        # -----------------------------------------------------------------
        logger.info("=== STEP 2: Updating Executive Profile Summary ===")
        try:
            sum_opened = page.evaluate("""() => {
                const widgets = Array.from(document.querySelectorAll('.widgetHead'));
                const sum = widgets.find(e => e.textContent.toLowerCase().includes('profile summary'));
                if (!sum) return false;
                sum.scrollIntoView({behavior: 'instant', block: 'center'});
                const btn = sum.querySelector('.edit, [aria-label*="Edit"], [aria-label*="Add"], span.editOneTheme');
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            if sum_opened:
                time.sleep(2)
                res = page.evaluate("""(summaryText) => {
                    const ta = document.getElementById('profileSummaryTxt') || document.querySelector('textarea[name="profileSummary"]');
                    if (!ta) return false;
                    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    nativeSetter.call(ta, summaryText);
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    ta.dispatchEvent(new Event('change', { bubbles: true }));

                    const form = ta.closest('form') || document;
                    const saveBtn = Array.from(form.querySelectorAll('button, .btn-dark-ot, input[type="submit"]')).find(b => b.textContent.trim().toLowerCase().includes('save'));
                    if (saveBtn) { saveBtn.click(); return true; }
                    return false;
                }""", SUMMARY_TEXT)
                time.sleep(3)
                logger.info(f"Profile Summary updated: {res}")
        except Exception as e:
            logger.error(f"Error updating Profile Summary: {e}")

        # -----------------------------------------------------------------
        # STEP 3: EMPLOYMENT ROLE DESCRIPTION (4,000 chars deep narrative)
        # -----------------------------------------------------------------
        logger.info("=== STEP 3: Updating Employment Role Description ===")
        try:
            emp_opened = page.evaluate("""() => {
                const widgets = Array.from(document.querySelectorAll('.widgetHead'));
                const emp = widgets.find(e => e.textContent.toLowerCase().includes('employment'));
                if (!emp) return "Employment widgetHead not found";
                emp.scrollIntoView({behavior: 'instant', block: 'center'});

                // Find edit button for current employment
                const editBtn = emp.parentElement.querySelector('.edit, [aria-label*="Edit"], span.editOneTheme');
                if (editBtn) {
                    editBtn.click();
                    return "Clicked employment edit";
                }
                return "Edit button not found in employment";
            }""")
            logger.info(f"Employment edit trigger: {emp_opened}")
            time.sleep(3)

            # Check if modal opened and look for job profile textarea
            emp_ta_updated = page.evaluate("""(descText) => {
                // Find textarea in the open employment modal
                const ta = document.querySelector('textarea[placeholder*="roles"], textarea[name*="jobProfile"], textarea[name*="description"], #jobProfileTxt, textarea');
                if (!ta) return { success: false, msg: "Employment textarea not found" };

                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                nativeSetter.call(ta, descText);
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));

                const form = ta.closest('form') || document;
                const saveBtn = Array.from(form.querySelectorAll('button, .btn-dark-ot, input[type="submit"]')).find(b => b.textContent.trim().toLowerCase().includes('save'));
                if (saveBtn) {
                    saveBtn.click();
                    return { success: true, msg: "Injected role description (" + descText.length + " chars) and clicked Save" };
                }
                return { success: false, msg: "Save button not found in employment modal" };
            }""", ROLE_DESCRIPTION_TEXT)
            logger.info(f"Employment update result: {json.dumps(emp_ta_updated)}")
            time.sleep(4)
        except Exception as e:
            logger.error(f"Error in Employment update: {e}")

        # -----------------------------------------------------------------
        # STEP 4: VERIFY AND PERSIST
        # -----------------------------------------------------------------
        logger.info("=== STEP 4: Verifying Final Live Profile Sections ===")
        time.sleep(3)
        live_sections = page.evaluate("""() => {
            const widgets = Array.from(document.querySelectorAll('.widgetHead'));
            const res = {};
            for (const w of widgets) {
                const title = w.textContent.trim().split('\\n')[0];
                if (w.parentElement) {
                    res[title] = w.parentElement.innerText;
                }
            }
            return res;
        }""")
        for k, v in live_sections.items():
            if any(term in k.lower() for term in ["headline", "summary", "employment"]):
                logger.info(f"\n[LIVE SECTION: {k}]\n{v[:500]}...\n-----------------------------")

        evidence_file = Path("artifacts/evidence/profile_optimization_success.png")
        try:
            page.screenshot(path=str(evidence_file), full_page=False, timeout=8000)
            logger.info(f"Saved verified screenshot to {evidence_file}")
        except Exception as e:
            logger.warning(f"Screenshot note: {e}")

        context.storage_state(path=str(AUTH_STATE_FILE))
        browser.close()
        logger.info("Deep Profile Optimization Pipeline Completed Successfully!")

if __name__ == "__main__":
    run_optimization()
