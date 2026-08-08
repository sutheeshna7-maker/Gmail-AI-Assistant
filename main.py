import os
import time

from google import genai
from google.genai import errors as genai_errors

from gmail_connect import (
    get_gmail_service,
    get_unread_emails,
    get_thread_text,
    create_draft_reply,
    mark_as_read,
)

# Set this in your environment rather than hardcoding it:
#   Windows (PowerShell):  $env:GEMINI_API_KEY="your_key_here"
#   Then restart PyCharm so it picks up the env var.
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# Adjust this to match how you actually write emails.
REPLY_STYLE_GUIDE = """
- Always polite, professional, and courteous in tone — never casual or curt.
- Well-articulated and polished: clear structure, confident word choice, no filler.
- Acknowledge the sender's message specifically before responding to it.
- Concise — get to the point without sounding abrupt. No rambling, no repetition.
- Avoid over-apologizing, excessive hedging, or generic corporate phrases
  ("please don't hesitate to reach out", "I hope this email finds you well").
- Sound competent and considered, not stiff or robotic.
- Always write the reply in English, even if the incoming email or your
  instructions are in Tamil, Tanglish, or any other language.
- Sign off with just my first name.
"""


def draft_reply_text(thread_text: str, max_retries: int = 5) -> str:
    """Sends the thread to Gemini and returns a plain-text reply body.
    Retries on transient server errors (503 = model overloaded)."""
    prompt = (
        "Here is an email thread (oldest to newest):\n\n"
        f"{thread_text}\n\n"
        "Write a reply to the most recent message.\n\n"
        f"Style guide:\n{REPLY_STYLE_GUIDE}\n\n"
        "Reply with ONLY the email body text. "
        "No subject line, no commentary, no markdown."
    )

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
            )
            return response.text.strip()
        except genai_errors.ServerError as e:
            wait = 10 * (attempt + 1)
            print(f"  Model overloaded (attempt {attempt + 1}/{max_retries}), retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError("Gemini API is overloaded after multiple retries. Try again in a few minutes.")


def extract_sender_email(from_header: str) -> str:
    """From_header looks like 'Jane Doe <jane@example.com>' — pull just the address."""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0].strip()
    return from_header.strip()


def run(max_emails: int = 10, mark_processed_as_read: bool = True):
    service = get_gmail_service()
    unread = get_unread_emails(service, max_results=max_emails)

    if not unread:
        print("No unread emails.")
        return

    for email in unread:
        if email.get("is_bulk"):
            print(f"Skipping (newsletter/notification): {email['subject']}")
            continue

        print(f"Processing: {email['subject']} (from {email['from']})")

        thread_text = get_thread_text(service, email["thread_id"])
        reply_body = draft_reply_text(thread_text)

        create_draft_reply(
            service,
            thread_id=email["thread_id"],
            to=extract_sender_email(email["from"]),
            subject=email["subject"],
            body=reply_body,
        )

        if mark_processed_as_read:
            mark_as_read(service, email["id"])

        print(f"  -> Draft created for: {email['subject']}\n")


if __name__ == "__main__":
    run()