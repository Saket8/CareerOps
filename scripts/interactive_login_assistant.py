import os
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv("/u01/CareerOps/.env")
username = os.environ.get("LINKEDIN_USERNAME")
password = os.environ.get("LINKEDIN_PASSWORD")
evidence_dir = Path("artifacts/evidence")
evidence_dir.mkdir(parents=True, exist_ok=True)

user_data_dir = "/u01/CareerOps/artifacts/chrome_linkedin_profile"

print("Starting LinkedIn Interactive Login Assistant...")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled'
        ],
        viewport={'width': 1280, 'height': 800}
    )
    page = context.new_page()
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
    time.sleep(3)
    
    # Check if already authenticated
    if "feed" in page.url:
        print("Already logged in!")
        context.storage_state(path="artifacts/linkedin_auth.json")
        context.close()
        exit(0)
        
    print("Navigated to login page:", page.url)
    
    # Fill username and password
    inputs = page.locator('input').all()
    for inp in inputs:
        box = inp.bounding_box()
        if box and box['width'] > 50:
            if inp.get_attribute('type') == 'email':
                inp.click()
                page.keyboard.type(username, delay=30)
            elif inp.get_attribute('type') == 'password':
                inp.click()
                page.keyboard.type(password, delay=30)
                
    buttons = page.locator('button').all()
    for btn in buttons:
        box = btn.bounding_box()
        if box and box['width'] > 50 and 'Sign in' in btn.inner_text():
            btn.click()
            break
            
    time.sleep(8)
    print("Post submit URL:", page.url)
    print("Post submit Title:", page.title())
    
    page.screenshot(path=str(evidence_dir / "login_step_current.png"))
    print("Saved screenshot to artifacts/evidence/login_step_current.png")
    
    # Check what kind of challenge LinkedIn gave:
    text = page.locator('body').inner_text()
    print("\nPage text:\n", text[:500])
    
    context.close()
