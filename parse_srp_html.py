import urllib.request
import re
import json

url = "https://www.naukri.com/oracle-cloud-infrastructure-architect-jobs"
req = urllib.request.Request(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)

with urllib.request.urlopen(req, timeout=15) as resp:
    html = resp.read().decode("utf-8", errors="ignore")

print(f"HTML length: {len(html)}")

# Check for next_data or srpState or job tuples
if "__NEXT_DATA__" in html:
    print("Found __NEXT_DATA__")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        data = json.loads(m.group(1))
        print("NEXT_DATA keys:", list(data.keys()))

# Check for self.__next_f
next_f_matches = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html)
print(f"self.__next_f matches count: {len(next_f_matches)}")

# Look for job titles or company names in the raw html
job_matches = re.findall(r'\"title\":\"([^\"]+)\"', html)
print(f"Found titles in JSON strings: {len(job_matches)}")
if job_matches:
    print("Sample titles:", job_matches[:5])

# Also check for companyName
companies = re.findall(r'\"companyName\":\"([^\"]+)\"', html)
print(f"Found companies: {len(companies)}")
if companies:
    print("Sample companies:", companies[:5])

# Check for jobId
job_ids = re.findall(r'\"jobId\":\"([^\"]+)\"', html)
print(f"Found jobIds: {len(job_ids)}")
if job_ids:
    print("Sample jobIds:", job_ids[:5])
