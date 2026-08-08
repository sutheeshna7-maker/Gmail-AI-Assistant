import base64
import os
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]


def get_gmail_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token_file:
            token_file.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    return service


def extract_body(payload):
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return "(No plain text body found)"
    else:
        data = payload["body"].get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return "(No body)"


def _fetch_messages(service, message_ids):
    emails = []
    for msg in message_ids:
        msg_data = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()

        headers = msg_data["payload"]["headers"]
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No subject)")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "(Unknown sender)")

        body = extract_body(msg_data["payload"])
        is_read = "UNREAD" not in msg_data.get("labelIds", [])

        emails.append({
            "sender": sender,
            "subject": subject,
            "body": body,
            "is_read": is_read
        })

    return emails


def get_recent_emails(service, max_results=5):
    results = service.users().messages().list(userId="me", maxResults=max_results).execute()
    message_ids = results.get("messages", [])
    return _fetch_messages(service, message_ids)


def search_emails(service, query, max_results=5):
    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    message_ids = results.get("messages", [])
    return _fetch_messages(service, message_ids)


def send_email(service, to, subject, body):
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent