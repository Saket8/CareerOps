import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("/u01/CareerOps/.env")
smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
smtp_port = int(os.getenv("SMTP_PORT", 587))
username = os.getenv("SMTP_USERNAME", "sauravskt8@gmail.com")
password = os.getenv("SMTP_PASSWORD")

if not username or not password:
    raise ValueError("SMTP_USERNAME or SMTP_PASSWORD not set in /u01/CareerOps/.env")

to_recipients = ["shubendu.das@apexit.com"]
cc_recipients = [username]
all_recipients = to_recipients + cc_recipients

in_reply_to_id = "<PH0PR04MB99434434C3C3EDC65CA7858DA9EA7E2@PH0PR04MB994344.namprd04.prod.outlook.com>"
subject = "Re: Job Opportunity -Senior OCI Security role-Permanent Position-(Hybrid/Remote)"

msg = MIMEMultipart("mixed")
msg["From"] = f"Saket Saurav <{username}>"
msg["To"] = ", ".join(to_recipients)
msg["Cc"] = ", ".join(cc_recipients)
msg["Subject"] = subject
msg["In-Reply-To"] = in_reply_to_id
msg["References"] = in_reply_to_id

text_body = """Dear Shubendu,

Please note the direct, updated link to my LinkedIn profile for your reference:
https://www.linkedin.com/in/saket-saurav-31326b57/

(Apologies for the slight typo in the profile URL link in the earlier signature).

Thank you, and I look forward to connecting!

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
  .highlight-card { background-color: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px 16px; margin: 16px 0; border-radius: 4px; max-width: 600px; }
</style>
</head>
<body>
<p>Dear Shubendu,</p>

<p>Please note the direct, updated link to my LinkedIn profile for your reference:</p>

<div class="highlight-card">
  <strong>LinkedIn Profile:</strong> <a href="https://www.linkedin.com/in/saket-saurav-31326b57/">https://www.linkedin.com/in/saket-saurav-31326b57/</a>
</div>

<p><em>(Apologies for the slight typo in the profile URL in my earlier signature).</em></p>

<p>Thank you, and I look forward to connecting!</p>

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

def send():
    print(f"Connecting to {smtp_server}:{smtp_port}...")
    with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(msg, to_addrs=all_recipients)
    print("Correction email successfully sent to:", all_recipients)

if __name__ == "__main__":
    send()
