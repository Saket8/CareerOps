import os
import sys
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_STATE_FILE = Path("artifacts/naukri_auth.json")

def inspect():
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
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            storage_state=str(AUTH_STATE_FILE) if AUTH_STATE_FILE.exists() else None
        )
        page = context.new_page()

        print("Navigating to https://www.naukri.com/mnjuser/profile ...", flush=True)
        page.goto("https://www.naukri.com/mnjuser/profile", wait_until="commit", timeout=30000)
        time.sleep(5)

        for _ in range(12):
            page.evaluate("window.scrollBy(0, 450)")
            time.sleep(0.3)

        # Inspect Employment section
        emp_info = page.evaluate("""() => {
            const widgets = Array.from(document.querySelectorAll('.widgetHead'));
            const emp = widgets.find(e => e.textContent.toLowerCase().includes('employment'));
            if (!emp) return "Employment widget not found";
            const parent = emp.parentElement;
            const editBtns = Array.from(parent.querySelectorAll('.edit, [aria-label*="Edit"], [aria-label*="Add"], span.editOneTheme, .addDetail')).map(b => ({
                text: b.innerText.trim(),
                aria: b.getAttribute('aria-label'),
                class: b.className,
                outer: b.outerHTML
            }));
            return {
                text: parent.innerText.slice(0, 800),
                editBtns: editBtns
            };
        }""")
        print("=== EMPLOYMENT INSPECTION ===")
        print(json.dumps(emp_info, indent=2), flush=True)

        # Inspect Projects section
        proj_info = page.evaluate("""() => {
            const widgets = Array.from(document.querySelectorAll('.widgetHead'));
            const pr = widgets.find(e => e.textContent.toLowerCase().includes('project'));
            if (!pr) return "Projects widget not found";
            const parent = pr.parentElement;
            const editBtns = Array.from(parent.querySelectorAll('.edit, [aria-label*="Edit"], [aria-label*="Add"], span.editOneTheme, .addDetail')).map(b => ({
                text: b.innerText.trim(),
                aria: b.getAttribute('aria-label'),
                class: b.className,
                outer: b.outerHTML
            }));
            return {
                text: parent.innerText.slice(0, 800),
                editBtns: editBtns
            };
        }""")
        print("\n=== PROJECTS INSPECTION ===")
        print(json.dumps(proj_info, indent=2), flush=True)

        browser.close()

if __name__ == "__main__":
    inspect()
