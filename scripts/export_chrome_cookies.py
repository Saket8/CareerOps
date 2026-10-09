# Script to explain cookie extraction or inspect exported cookies
import json
from pathlib import Path

cookie_file = Path("artifacts/linkedin_auth.json")
if cookie_file.exists():
    with open(cookie_file) as f:
        data = json.load(f)
    cookies = data.get("cookies", [])
    print(f"Total cookies in {cookie_file}: {len(cookies)}")
    for c in cookies:
        print(f"  {c['name']} ({c['domain']}): {c['value'][:15]}...")
else:
    print("No cookie file yet.")
