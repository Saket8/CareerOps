import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv("/u01/CareerOps/.env")
smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
smtp_port = int(os.getenv("SMTP_PORT", 587))
username = os.getenv("SMTP_USERNAME", "sauravskt8@gmail.com")
password = os.getenv("SMTP_PASSWORD")

if not username or not password:
    raise ValueError("SMTP_USERNAME or SMTP_PASSWORD not set in /u01/CareerOps/.env")

# 2. Email Recipients and Thread Headers
to_recipients = ["shubendu.das@apexit.com"]
cc_recipients = [username]
all_recipients = to_recipients + cc_recipients

in_reply_to_id = "<PH0PR04MB9943440DBD0D8572B7CDCCD464EA7A2@PH0PR04MB994344.namprd04.prod.outlook.com>"
references_str = (
    "<PH0PR04MB99434434C3C3EDC65CA7858DA9EA7E2@PH0PR04MB994344.namprd04.prod.outlook.com> "
    "<6afab383.2ba6c529.16a0b4.009e@mx.google.com> "
    "<PH0PR04MB9943440DBD0D8572B7CDCCD464EA7A2@PH0PR04MB994344.namprd04.prod.outlook.com>"
)
subject = "Re: Job Opportunity -Senior OCI Security role-Permanent Position-(Hybrid/Remote)"

# 3. Create Multipart Message
msg = MIMEMultipart("mixed")
msg["From"] = f"Saket Saurav <{username}>"
msg["To"] = ", ".join(to_recipients)
msg["Cc"] = ", ".join(cc_recipients)
msg["Subject"] = subject
msg["In-Reply-To"] = in_reply_to_id
msg["References"] = references_str

# 4. Message Bodies
text_body = """Dear Shubendu,

Thank you for your follow-up email.

As requested, please find attached my updated master CV in both PDF (Saket_Saurav_Resume.pdf) and Word (Saket_Saurav_Resume.docx) formats.

Summary of Updated Profile Details:
• Current Role & Employer: Principal Cloud Architect (Enterprise Cloud & Security) at Cognizant (Nov 2024 – Present)
• Total Experience: 12 Years
• Relevant OCI & Cloud Security Architecture Experience: 6.5 Years
• Current Location: Noida (Delhi NCR)
• Preferred Mode: Hybrid / Remote
• Official Notice Period: 90 Days (Official / Negotiable)

Key Competencies & Architect Scope:
- Deep specialization in Oracle Cloud Infrastructure (OCI), Zero-Trust security frameworks, IAM federation (Azure AD / Okta / SAML 2.0 SSO), SCIM provisioning, and air-gapped isolation.
- Hands-on network architecture: Hub-and-Spoke VCN, DRG, Palo Alto VM-Series firewalls, IPSec VPN, and private DNS.
- Enterprise container platform engineering on private OKE clusters with FSS persistent storage and Kubernetes RBAC.
- Modular Infrastructure-as-Code (Terraform) reducing deployment lead times and eliminating environment drift.
- Certified OCI Architect Professional and DevOps Professional.

Please let me know if you require any additional details or documents. I look forward to the next steps.

Best regards,
Saket Saurav
Principal Cloud Architect (Enterprise Cloud & Security)
Cognizant
Phone: +91-7028481800
Email: sauravskt8@gmail.com
LinkedIn: https://www.linkedin.com/in/saket-saurav-31326b57/
GitHub: https://github.com/Saket8
"""

html_body = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; font-size: 14px; }
  .highlight-card { background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px 16px; margin: 16px 0; border-radius: 4px; max-width: 680px; }
  .table-details { border-collapse: collapse; width: 100%; max-width: 680px; margin: 16px 0; }
  .table-details td { padding: 8px 12px; border: 1px solid #e2e8f0; }
  .table-details td.label { font-weight: 600; background-color: #f8fafc; width: 38%; color: #334155; }
  .table-details td.value { background-color: #ffffff; color: #0f172a; }
  ul { margin: 8px 0; padding-left: 20px; }
  li { margin-bottom: 4px; }
</style>
</head>
<body>
<p>Dear Shubendu,</p>

<p>Thank you for your follow-up email.</p>

<p>As requested, please find attached my updated master CV in both PDF (<code>Saket_Saurav_Resume.pdf</code>) and Word (<code>Saket_Saurav_Resume.docx</code>) formats for your detailed review.</p>

<table class="table-details">
  <tr><td class="label">Current Employer & Role</td><td class="value"><strong>Cognizant</strong> &mdash; Principal Cloud Architect (Enterprise Cloud & Security)<br><em>(Nov 2024 &ndash; Present)</em></td></tr>
  <tr><td class="label">Total Experience</td><td class="value"><strong>12 Years</strong></td></tr>
  <tr><td class="label">Relevant OCI & Cloud Security</td><td class="value"><strong>6.5 Years</strong></td></tr>
  <tr><td class="label">Current Location</td><td class="value">Noida (Delhi NCR)</td></tr>
  <tr><td class="label">Preferred Work Mode</td><td class="value">Hybrid / Remote</td></tr>
  <tr><td class="label">Official Notice Period</td><td class="value">90 Days (Official / Negotiable)</td></tr>
</table>

<div class="highlight-card">
  <strong>Key Architecture & Security Highlights:</strong>
  <ul>
    <li>Deep specialization in Oracle Cloud Infrastructure (OCI), Zero-Trust security frameworks, IAM federation (Azure AD / Okta / SAML 2.0 SSO), SCIM provisioning, and air-gapped isolation.</li>
    <li>Hands-on network architecture: Hub-and-Spoke VCN, DRG, Palo Alto VM-Series firewalls, IPSec VPN, and private DNS.</li>
    <li>Enterprise container platform engineering on private OKE clusters with FSS persistent storage and Kubernetes RBAC.</li>
    <li>Modular Infrastructure-as-Code (Terraform) reducing deployment lead times by ~60% and eliminating configuration drift.</li>
    <li>Certified OCI Architect Professional and DevOps Professional.</li>
  </ul>
</div>

<p>Please let me know if you need any additional information or have any questions. I look forward to the next steps in the discussion.</p>

<p>Best regards,<br>
<strong>Saket Saurav</strong><br>
Principal Cloud Architect (Enterprise Cloud & Security)<br>
Cognizant<br>
Phone: +91-7028481800<br>
Email: sauravskt8@gmail.com<br>
LinkedIn: <a href="https://www.linkedin.com/in/saket-saurav-31326b57/">https://www.linkedin.com/in/saket-saurav-31326b57/</a><br>
GitHub: <a href="https://github.com/Saket8">https://github.com/Saket8</a></p>
</body>
</html>
"""

alt_part = MIMEMultipart("alternative")
alt_part.attach(MIMEText(text_body, "plain", "utf-8"))
alt_part.attach(MIMEText(html_body, "html", "utf-8"))
msg.attach(alt_part)

# 5. Attach Master Resumes
pdf_path = Path("/u01/CareerOps/resumes/master/Saket_Saurav_Resume.pdf")
docx_path = Path("/u01/CareerOps/resumes/master/Saket_Saurav_OCI.docx")

if not pdf_path.exists():
    raise FileNotFoundError(f"PDF not found at {pdf_path}")
if not docx_path.exists():
    raise FileNotFoundError(f"DOCX not found at {docx_path}")

with open(pdf_path, "rb") as f:
    pdf_attach = MIMEApplication(f.read(), Name="Saket_Saurav_Resume.pdf")
pdf_attach["Content-Disposition"] = 'attachment; filename="Saket_Saurav_Resume.pdf"'
msg.attach(pdf_attach)
print(f"Attached {pdf_path.name} ({pdf_path.stat().st_size} bytes)")

with open(docx_path, "rb") as f:
    docx_attach = MIMEApplication(f.read(), Name="Saket_Saurav_Resume.docx")
docx_attach["Content-Disposition"] = 'attachment; filename="Saket_Saurav_Resume.docx"'
msg.attach(docx_attach)
print(f"Attached Saket_Saurav_Resume.docx ({docx_path.stat().st_size} bytes)")

# 6. Send Email via SMTP
print(f"Connecting to {smtp_server}:{smtp_port}...")
with smtplib.SMTP(smtp_server, smtp_port, timeout=25) as server:
    server.starttls()
    server.login(username, password)
    server.send_message(msg, to_addrs=all_recipients)

print("Email successfully sent to:", all_recipients)
