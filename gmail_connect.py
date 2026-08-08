import base64
import os

# Google sometimes returns scopes in a different order or bundles an
# extra implied scope, which makes oauthlib raise a scope-mismatch
# error even though access is fine. This relaxes that strict check.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.modify = read + manage labels + create drafts, but NOT send.
# gmail.send is added separately so send_email() still works, but you
# can drop it if you want the AI-drafting flow to be send-proof.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

TOKEN_PATH = "token.json"


def get_gmail_service():
    """Authenticates and returns a Gmail API service object.

    Stores/reads the token as plain JSON (matching the .json filename)
    rather than pickle, since that's the standard format Google's own
    libraries expect and produce.
    """
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _extract_body(payload) -> str:
    """Pulls the plain-text body out of a Gmail message payload."""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode(
                        "utf-8", errors="ignore"
                    )
            # handle nested multipart (e.g. multipart/alternative inside multipart/mixed)
            if "parts" in part:
                nested = _extract_body(part)
                if nested:
                    return nested
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return ""


def _looks_promotional(subject: str, body: str) -> bool:
    """Catches obvious marketing/event-invite emails that don't have
    List-Unsubscribe headers but are clearly not personal correspondence."""
    signal_phrases = [
        "unsubscribe", "webinar", "free live session", "register now",
        "limited time", "act now", "claim your", "% off", "new device",
        "sign in to your account", "you were logged in", "certificate",
        "shortcut", "don't miss", "exclusive offer", "join us live",
    ]
    text = f"{subject} {body}".lower()
    return any(phrase in text for phrase in signal_phrases)


def _fetch_messages(service, message_ids):
    """Given a list of message IDs, fetches full details for each."""
    emails = []
    for mid in message_ids:
        msg = service.users().messages().get(
            userId="me", id=mid["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "")
        body = _extract_body(msg["payload"])
        is_read = "UNREAD" not in msg.get("labelIds", [])
        is_bulk = "List-Unsubscribe" in headers or "List-Id" in headers

        emails.append({
            "id": msg["id"],
            "thread_id": msg["threadId"],
            "from": sender,
            "subject": subject,
            "body": body,
            "is_read": is_read,
            "is_bulk": is_bulk or _looks_promotional(subject, body),
        })

    return emails


def get_recent_emails(service, max_results: int = 5):
    """Returns the N most recent messages in the inbox."""
    results = service.users().messages().list(
        userId="me", maxResults=max_results
    ).execute()
    message_ids = results.get("messages", [])
    return _fetch_messages(service, message_ids)


def get_unread_emails(service, max_results: int = 10):
    """Returns unread messages in the primary inbox — excludes
    Promotions, Social, and Updates tabs, which are almost always
    newsletters/notifications that don't need a reply draft."""
    query = (
        "is:unread in:inbox "
        "-category:promotions -category:social -category:updates -category:forums"
    )
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    message_ids = results.get("messages", [])
    return _fetch_messages(service, message_ids)


def search_emails(service, query, max_results: int = 5):
    """Searches messages using Gmail search syntax."""
    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    message_ids = results.get("messages", [])
    return _fetch_messages(service, message_ids)


def get_thread_text(service, thread_id) -> str:
    """Returns the full thread as concatenated text, for AI context."""
    thread = service.users().threads().get(userId="me", id=thread_id).execute()
    chunks = []
    for msg in thread["messages"]:
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body = _extract_body(msg["payload"])
        chunks.append(
            f"From: {headers.get('From')}\n"
            f"Subject: {headers.get('Subject')}\n\n"
            f"{body}"
        )
    return "\n\n---\n\n".join(chunks)


def send_email(service, to, subject, body):
    """Sends an email immediately. Use create_draft_reply() instead
    if you want a human to review before sending."""
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    return sent


def create_new_draft(service, to, subject, body):
    """Creates a brand-new (non-reply) draft — starts a fresh thread,
    unlike create_draft_reply() which attaches to an existing one."""
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()
    return draft


def create_draft_reply(service, thread_id, to, subject, body):
    """Creates a draft reply attached to an existing thread, for
    the user to review/edit/send manually in Gmail."""
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw, "threadId": thread_id}},
    ).execute()
    return draft


def mark_as_read(service, message_id):
    """Removes the UNREAD label so re-runs don't reprocess this message."""
    service.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()