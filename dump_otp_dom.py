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
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080}
    )
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)
    page = context.new_page()
    page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=35000)
    page.wait_for_timeout(2000)

    user_field = page.locator("#usernameField")
    pass_field = page.locator("#passwordField")
    user_field.fill(os.environ.get("NAUKRI_USERNAME", ""))
    pass_field.fill(os.environ.get("NAUKRI_PASSWORD", ""))
    page.locator("button:has-text('Login'), button.blue-btn").first.click()
    page.wait_for_timeout(4000)

    # Dump all inputs
    inputs = page.locator("input").all()
    print(f"Total inputs on page: {len(inputs)}")
    for i, inp in enumerate(inputs):
        try:
            print(f"Input {i}: type={inp.get_attribute('type')}, class={inp.get_attribute('class')}, id={inp.get_attribute('id')}, maxlength={inp.get_attribute('maxlength')}, html={inp.evaluate('el => el.outerHTML')}")
        except Exception as e:
            print(f"Input {i} err: {e}")

    # Dump buttons
    buttons = page.locator("button").all()
    print(f"Total buttons: {len(buttons)}")
    for b in buttons:
        try:
            print(f"Button: text='{b.text_content().strip()}', class={b.get_attribute('class')}, html={b.evaluate('el => el.outerHTML')}")
        except Exception as e:
            pass

    browser.close()
