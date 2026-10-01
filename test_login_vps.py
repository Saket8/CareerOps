import os
import time
from playwright.sync_api import sync_playwright

username = os.environ.get("NAUKRI_USERNAME", "")
password = os.environ.get("NAUKRI_PASSWORD", "")

# Ensure DISPLAY is set for Xvfb
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    page = context.new_page()

    login_url = "https://www.naukri.com/nlogin/login"
    print(f"Navigating to login URL: {login_url}")
    resp = page.goto(login_url, wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(3000)
    print("Page URL:", page.url)
    print("Page Title:", page.title())
    page.screenshot(path="login_page.png")

    user_field = page.locator("#usernameField")
    pass_field = page.locator("#passwordField")
    print("Username field count:", user_field.count())
    print("Password field count:", pass_field.count())

    if user_field.count() > 0 and pass_field.count() > 0:
        print("Filling credentials...")
        user_field.fill(username)
        pass_field.fill(password)
        page.screenshot(path="login_filled.png")

        login_btn = page.locator("button:has-text('Login'), button.blue-btn").first
        print("Login button visible:", login_btn.is_visible())
        login_btn.click()
        page.wait_for_timeout(6000)

        print("Post-click URL:", page.url)
        print("Post-click Title:", page.title())
        page.screenshot(path="login_result.png")

        profile_drawer = page.locator(".nI-gNb-drawer, .view-profile-wrapper, .nI-gNb-menuItems")
        print("Profile indicators count:", profile_drawer.count())

        # Check for error messages or OTP
        error_msg = page.locator(".server-err, .err, [class*='error']").all_text_contents()
        print("Error messages found:", error_msg)

    browser.close()
