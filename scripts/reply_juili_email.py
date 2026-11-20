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
username = os.getenv("SMTP_USERNAME")
password = os.getenv("SMTP_PASSWORD")

if not username or not password:
    raise ValueError("SMTP_USERNAME or SMTP_PASSWORD not set in /u01/CareerOps/.env")

# 2. Email Recipients and Thread Headers
to_recipients = ["Juili.Kotangale@ltm.com"]
cc_recipients = ["Juili.Kotangale@ltmindtree.com", username]
all_recipients = to_recipients + cc_recipients

in_reply_to_id = "<PN4P287MB4389B17093E862FA956A1454ED652@PN4P287MB4389.INDP287.PROD.OUTLOOK.COM>"
subject = "Re: LTM - Urgent Opening -TPM & Architect"

# 3. Create Multipart Message
msg = MIMEMultipart("mixed")
msg["From"] = f"Saket Saurav <{username}>"
msg["To"] = ", ".join(to_recipients)
msg["Cc"] = ", ".join(cc_recipients)
msg["Subject"] = subject
msg["In-Reply-To"] = in_reply_to_id
msg["References"] = in_reply_to_id

# 4. Message Bodies
text_body = """Dear Juili,

Thank you for reaching out regarding the open positions at LTM.

I am applying for the AI Architect / AI Solution Architect role. Please find my candidate details below along with my master resume attached in both PDF and Word formats:

• Skill Applied for: AI Architect (AI Solution Architect)
• Full Name: Saket Saurav
• Contact Number: +91-7028481800
• Total Experience: 12 Years
• Relevant Experience: 
  - Generative AI, LLMs, Agentic AI, RAG & Azure OpenAI: 5.0 Years
  - Enterprise Cloud Architecture (OCI, Azure, AWS) & Python: 6.5 Years
• Current Company: Cognizant
• Current Location: Noida
• Preferred Location: PAN India (Noida / Remote / Hybrid)
• Current CTC: 30 LPA
• Expected CTC: Negotiable / As per company standards
• Notice Period: 90 Days (Official / Negotiable)
• DOB: Available upon interview shortlisting / verification
• PAN Card no.: Available upon interview shortlisting / verification
• Gender: Male
• Ex-Employee: No

Brief Overview of Profile:
- Currently Principal Cloud Engineer (OCI) / Manager-Projects at Cognizant with 12+ years of enterprise IT engineering excellence.
- Deep hands-on experience designing and implementing GenAI and Agentic AI architectures, RAG pipelines, LLM fine-tuning/orchestration, Vector DBs (Pinecone, Azure AI Search), and cloud-native solutions.
- Proven track record leading cloud-native architectures on Azure, OCI, and multi-cloud environments, container orchestration (OKE/Kubernetes), and Infrastructure as Code (Terraform).

Please find attached my master resume in both PDF (Saket_Saurav_Resume.pdf) and Word (Saket_Saurav_Resume.docx) formats for your detailed review.

Looking forward to hearing from you.

Best regards,
Saket Saurav
Principal Cloud Engineer / Manager-Projects
Phone: +91-7028481800
Email: sauravskt8@gmail.com
"""

html_body = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.6; font-size: 14px; }
  .table-details { border-collapse: collapse; width: 100%; max-width: 650px; margin: 16px 0; }
  .table-details td { padding: 8px 12px; border: 1px solid #e2e8f0; }
  .table-details td.label { font-weight: 600; background-color: #f8fafc; width: 35%; color: #334155; }
  .table-details td.value { background-color: #ffffff; color: #0f172a; }
  .highlight-card { background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px 16px; margin: 16px 0; border-radius: 4px; }
  ul { margin: 8px 0; padding-left: 20px; }
  li { margin-bottom: 4px; }
</style>
</head>
<body>
<p>Dear Juili,</p>

<p>Thank you for reaching out regarding the open positions at LTM.</p>

<p>I am pleased to submit my application for the <strong>AI Architect (AI Solution Architect)</strong> position. Below are the requested candidate details:</p>

<table class="table-details">
  <tr><td class="label">Skill Applied for</td><td class="value"><strong>AI Architect (AI Solution Architect)</strong></td></tr>
  <tr><td class="label">Full Name</td><td class="value">Saket Saurav</td></tr>
  <tr><td class="label">Contact Number</td><td class="value">+91-7028481800</td></tr>
  <tr><td class="label">Total Experience</td><td class="value">12 Years</td></tr>
  <tr><td class="label">Relevant Experience</td><td class="value">5.0 Years (GenAI, LLMs, Agentic AI, RAG) / 6.5 Years (Cloud Architecture & Python)</td></tr>
  <tr><td class="label">Current Company</td><td class="value">Cognizant</td></tr>
  <tr><td class="label">Current Location</td><td class="value">Noida</td></tr>
  <tr><td class="label">Preferred Location</td><td class="value">PAN India (Noida / Hybrid / Remote)</td></tr>
  <tr><td class="label">Current CTC</td><td class="value">30 LPA</td></tr>
  <tr><td class="label">Expected CTC</td><td class="value">Negotiable / As per company standards</td></tr>
  <tr><td class="label">Notice Period</td><td class="value">90 Days (Official / Negotiable)</td></tr>
  <tr><td class="label">DOB</td><td class="value">Available upon interview shortlisting / verification</td></tr>
  <tr><td class="label">PAN Card no.</td><td class="value">Available upon interview shortlisting / verification</td></tr>
  <tr><td class="label">Gender</td><td class="value">Male</td></tr>
  <tr><td class="label">Ex-Employee</td><td class="value">No</td></tr>
</table>

<div class="highlight-card">
  <strong>Key Architectural Highlights:</strong>
  <ul>
    <li><strong>GenAI & Agentic AI Systems:</strong> Deep hands-on experience designing production RAG pipelines, LLM orchestration (LangChain, LangGraph), local LLMs, and Model Context Protocol (MCP) servers.</li>
    <li><strong>Cloud & Enterprise Scalability:</strong> 6.5+ years architecting enterprise cloud estates across Azure, OCI, and AWS, including private Kubernetes (OKE) clusters and zero-trust IAM.</li>
    <li><strong>Modern IaC & Automation:</strong> Modular Terraform and Python frameworks delivering high operational reliability and zero drift.</li>
  </ul>
</div>

<p>I have attached my master resume in both PDF (<code>Saket_Saurav_Resume.pdf</code>) and Word (<code>Saket_Saurav_Resume.docx</code>) formats for your review.</p>

<p>Looking forward to discussing how my experience can contribute to LTM's AI growth.</p>

<p>Best regards,<br>
<strong>Saket Saurav</strong><br>
Principal Cloud Engineer / Manager-Projects<br>
Phone: +91-7028481800<br>
Email: sauravskt8@gmail.com</p>
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
