import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv

load_dotenv('/u01/CareerOps/.env')
username = os.environ.get('SMTP_USERNAME')
password = os.environ.get('SMTP_PASSWORD')

print(f"Connecting to imap.gmail.com with {username}...")
try:
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(username, password)
    print("IMAP Login successful!")
    
    mail.select("INBOX")
    status, messages = mail.search(None, '(FROM "linkedin")')
    print("LinkedIn messages count:", len(messages[0].split()) if messages[0] else 0)
    
    if messages[0]:
        latest_ids = messages[0].split()[-5:]
        for mid in reversed(latest_ids):
            res, data = mail.fetch(mid, "(RFC822)")
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8", errors="ignore")
                    print(f"ID {mid.decode()}: Date: {msg.get('Date')} | Subject: {subject}")
                    
    mail.close()
    mail.logout()
except Exception as e:
    print("IMAP Error:", e)
