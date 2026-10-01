import os
from playwright.sync_api import sync_playwright

if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
    )
    context = browser.new_context(
        storage_state="artifacts/naukri_auth.json",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    page = context.new_page()

    test_url = "https://www.naukri.com/job-listings-cloud-architect-ey-delhi-ncr-10-to-15-years-180926017260"
    print(f"Navigating to {test_url} with storage_state...")
    page.goto(test_url, wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(3000)

    print("Page URL:", page.url)
    print("Page Title:", page.title())
    page.screenshot(path="auth_listing.png")

    # Check header indicators
    drawer = page.locator(".nI-gNb-drawer, .view-profile-wrapper, a[href*='profile'], .nI-gNb-header")
    print(f"Header profile indicators count: {drawer.count()}")

    for sel in [".nI-gNb-drawer", ".view-profile-wrapper", "a[href*='mnjuser/profile']", ".nI-gNb-header__wrapper", "#apply-button", ".apply-button", ".already-applied"]:
        print(f"Selector '{sel}' count: {page.locator(sel).count()}")

    # Check cookies present in context
    cookies = context.cookies()
    cookie_names = [c["name"] for c in cookies]
    print("Context cookies:", cookie_names)
    print("Has nauk_at:", "nauk_at" in cookie_names)
    print("Has nauk_rt:", "nauk_rt" in cookie_names)

    browser.close()
