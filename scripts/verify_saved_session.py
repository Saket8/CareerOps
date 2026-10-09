import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

COOKIE_JSON = Path("artifacts/linkedin_cookies.json")
AUTH_FILE = Path("artifacts/linkedin_auth.json")

print(f"Loading cookies from {COOKIE_JSON}...")
with open(COOKIE_JSON) as f:
    raw_cookies = json.load(f)

# Re-build clean storage_state
pw_cookies = []
for c in raw_cookies:
    cookie = {
        "name": c["name"],
        "value": c["value"],
        "domain": c["domain"],
        "path": c["path"],
        "httpOnly": c["httpOnly"],
        "secure": c["secure"],
        "sameSite": "None" if c.get("sameSite") in ["no_restriction", "None", None] else "Lax"
    }
    if c.get("expirationDate"):
        cookie["expires"] = c["expirationDate"]
    pw_cookies.append(cookie)

storage_state = {
    "cookies": pw_cookies,
    "origins": []
}

with open(AUTH_FILE, "w") as f:
    json.dump(storage_state, f, indent=2)

print(f"Saved {len(pw_cookies)} cookies to {AUTH_FILE}")

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled']
    )
    context = browser.new_context(
        storage_state=str(AUTH_FILE),
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900}
    )
    page = context.new_page()
    
    print("Navigating to https://www.linkedin.com/feed/ ...")
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=40000)
    time.sleep(4)
    print("Page URL:", page.url)
    print("Page Title:", page.title())
    
    is_authenticated = "feed" in page.url and "login" not in page.url
    print(f"Is Authenticated: {is_authenticated}")
    
    if is_authenticated:
        # Save fresh storage_state
        context.storage_state(path=str(AUTH_FILE))
        print("Updated auth state saved successfully!")
    else:
        print("Redirected to:", page.url)
        
    browser.close()
