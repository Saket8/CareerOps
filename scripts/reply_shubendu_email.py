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

in_reply_to_id = "<PH0PR04MB99434434C3C3EDC65CA7858DA9EA7E2@PH0PR04MB994344.namprd04.prod.outlook.com>"
subject = "Re: Job Opportunity -Senior OCI Security role-Permanent Position-(Hybrid/Remote)"

# 3. Create Multipart Message
msg = MIMEMultipart("mixed")
msg["From"] = f"Saket Saurav <{username}>"
msg["To"] = ", ".join(to_recipients)
msg["Cc"] = ", ".join(cc_recipients)
msg["Subject"] = subject
msg["In-Reply-To"] = in_reply_to_id
msg["References"] = in_reply_to_id

# 4. Message Bodies
text_body = """Dear Shubendu,

Thank you for reaching out regarding the Senior OCI Security opportunity at Apex IT.

I am very interested in this role and would love to explore how my enterprise cloud security and OCI architecture expertise aligns with Apex IT's strategic vision.

Please find my requested candidate details below:

• Total Years of Experience: 12 Years
• Relevant Experience: 
  - OCI Security Framework, Infrastructure Controls & SaaS/OIC Security: 6.5 Years
  - Enterprise Cloud Architecture (OCI, Azure, AWS) & IaC (Terraform): 6.5 Years
  - Enterprise Database Administration & Controls: 12 Years
• Current Employer: Cognizant
• Current Location: Noida (Delhi NCR)
• Hometown: Noida (Delhi NCR)
• Official Notice Period: 90 Days (Official / Negotiable)
• Last Working Day if resigned: Currently employed with Cognizant (serving notice upon offer finalization)
• Highest Qualification: B.Tech in Electronics & Communication Engineering
• Preferred Working Mode (Hybrid/Remote): Hybrid / Remote (Comfortable with both)

Profile Summary & Key Competencies:
- Principal Cloud Engineer (OCI) / Manager-Projects at Cognizant with 12+ years of enterprise IT experience.
- Deep expertise in OCI Security Framework, Zero-Trust network topologies, Palo Alto VM-Series firewalls, DRG/VCN architecture, and security compliance.
- Extensive experience in Identity and Access Management (IAM), including Azure AD / Microsoft Entra ID federation, SAML 2.0 / SSO, SCIM provisioning, Okta, and Linux PAM automation.
- Proven track record implementing OCI IAM Database Environment Isolation, container security on Kubernetes (OKE), and modular Terraform automation.
- Certified Oracle Cloud Infrastructure Architect Professional & DevOps Professional.

I have attached my updated master resume in both PDF (Saket_Saurav_Resume.pdf) and Word (Saket_Saurav_Resume.docx) formats for your detailed review.

Looking forward to hearing from you regarding the next steps in the discussion.

Best regards,
Saket Saurav
Principal Cloud Engineer (OCI) / Manager-Projects
Phone: +91-7028481800
Email: sauravskt8@gmail.com
LinkedIn: https://www.linkedin.com/in/saket-saurav-31326b57/
"""

html_body = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; font-size: 14px; }
  .table-details { border-collapse: collapse; width: 100%; max-width: 680px; margin: 16px 0; }
  .table-details td { padding: 8px 12px; border: 1px solid #e2e8f0; }
  .table-details td.label { font-weight: 600; background-color: #f8fafc; width: 38%; color: #334155; }
  .table-details td.value { background-color: #ffffff; color: #0f172a; }
  .highlight-card { background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px 16px; margin: 16px 0; border-radius: 4px; max-width: 680px; }
  ul { margin: 8px 0; padding-left: 20px; }
  li { margin-bottom: 4px; }
</style>
</head>
<body>
<p>Dear Shubendu,</p>

<p>Thank you for reaching out regarding the <strong>Senior OCI Security</strong> opportunity at <strong>Apex IT</strong>.</p>

<p>I am very interested in this role. Below are the requested candidate details for your review:</p>

<table class="table-details">
  <tr><td class="label">Total Years of Experience</td><td class="value"><strong>12 Years</strong></td></tr>
  <tr><td class="label">Relevant Experience</td><td class="value"><strong>6.5 Years</strong> in OCI Security Framework, Infrastructure Controls, IAM & SaaS/OIC Security</td></tr>
  <tr><td class="label">Current Employer</td><td class="value"><strong>Cognizant</strong> (Principal Cloud Engineer / Manager-Projects)</td></tr>
  <tr><td class="label">Current Location</td><td class="value">Noida (Delhi NCR)</td></tr>
  <tr><td class="label">Hometown</td><td class="value">Noida (Delhi NCR)</td></tr>
  <tr><td class="label">Official Notice Period</td><td class="value">90 Days (Official / Negotiable)</td></tr>
  <tr><td class="label">Last Working Day if resigned</td><td class="value">Currently employed with Cognizant (serving notice upon offer finalization)</td></tr>
  <tr><td class="label">Highest Qualification</td><td class="value">B.Tech in Electronics & Communication Engineering</td></tr>
  <tr><td class="label">Preferred Working Mode</td><td class="value"><strong>Hybrid / Remote</strong> (Open to both)</td></tr>
</table>

<div class="highlight-card">
  <strong>Core Architectural & Security Highlights:</strong>
  <ul>
    <li><strong>OCI Security & Infrastructure Controls:</strong> Deep hands-on experience designing OCI security frameworks, hub-and-spoke VCN topologies, DRG/LPG routing, Palo Alto VM-Series firewalls, and Network Security Groups (NSGs).</li>
    <li><strong>Enterprise IAM & Zero Trust:</strong> Spearheaded federated identity integration between OCI and enterprise IAM (Azure AD / Entra ID, Okta) using SAML 2.0 / SSO, SCIM provisioning, and Linux PAM access controls.</li>
    <li><strong>SaaS & OIC Security:</strong> Experience hardening cloud integrations, confidential application patterns in OCI IAM, and database environment isolation.</li>
    <li><strong>Automation & IaC:</strong> Modular Terraform and OCI Resource Manager pipelines delivering zero-drift, compliant infrastructure deployments.</li>
    <li><strong>Certified Professional:</strong> Oracle Cloud Infrastructure Architect Professional & OCI DevOps Professional.</li>
  </ul>
</div>

<p>I have attached my updated master resume in both PDF (<code>Saket_Saurav_Resume.pdf</code>) and Word (<code>Saket_Saurav_Resume.docx</code>) formats for your detailed review.</p>

<p>I look forward to speaking with you and discussing how my experience can support Apex IT's clients and team.</p>

<p>Best regards,<br>
<strong>Saket Saurav</strong><br>
Principal Cloud Engineer (OCI) / Manager-Projects<br>
Phone: +91-7028481800<br>
Email: sauravskt8@gmail.com<br>
LinkedIn: <a href="https://www.linkedin.com/in/saket-saurav-31326b57/">https://www.linkedin.com/in/saket-saurav-31326b57/</a></p>
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

if pdf_path.exists():
    with open(pdf_path, "rb") as f:
        pdf_attach = MIMEApplication(f.read(), Name="Saket_Saurav_Resume.pdf")
    pdf_attach["Content-Disposition"] = 'attachment; filename="Saket_Saurav_Resume.pdf"'
    msg.attach(pdf_attach)
    print(f"Attached {pdf_path.name} ({pdf_path.stat().st_size} bytes)")

if docx_path.exists():
    with open(docx_path, "rb") as f:
        docx_attach = MIMEApplication(f.read(), Name="Saket_Saurav_Resume.docx")
    docx_attach["Content-Disposition"] = 'attachment; filename="Saket_Saurav_Resume.docx"'
    msg.attach(docx_attach)
    print(f"Attached Saket_Saurav_Resume.docx ({docx_path.stat().st_size} bytes)")

# 6. Send Email via SMTP
print(f"Connecting to {smtp_server}:{smtp_port}...")
with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
    server.starttls()
    server.login(username, password)
    server.send_message(msg, to_addrs=all_recipients)

print("Email successfully sent to:", all_recipients)
