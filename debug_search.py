from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]
    )
    # Test 1: Fresh context, no storage state, realistic headers
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        }
    )
    page = context.new_page()
    url = "https://www.naukri.com/oracle-cloud-infrastructure-architect-jobs"
    print("Testing clean context without stale cookies to:", url)
    resp = page.goto(url, timeout=30000, wait_until="domcontentloaded")
    print("HTTP Status:", resp.status if resp else "None")
    print("Page Title:", page.title())
    
    tuples = page.locator("div.cust-job-tuple, div.srp-jobtuple").count()
    print("Job tuples found:", tuples)
    
    # Test 2: Homepage
    home_resp = page.goto("https://www.naukri.com/", timeout=30000, wait_until="domcontentloaded")
    print("Homepage Status:", home_resp.status if home_resp else "None")
    print("Homepage Title:", page.title())

    browser.close()
