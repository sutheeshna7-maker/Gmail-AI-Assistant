"""
Compose a brand-new email (not a reply) with an AI-suggested draft.

Run this separately from main.py:
    python compose.py

It asks for the recipient and a short description of what you want to say,
then creates a Gmail draft (to field pre-filled, body AI-written) for you
to review and send manually.
"""

import time

from google import genai
from google.genai import errors as genai_errors

from gmail_connect import get_gmail_service, create_new_draft

client = genai.Client()  # picks up GEMINI_API_KEY from environment automatically

REPLY_STYLE_GUIDE = """
- Always polite, professional, and courteous in tone — never casual or curt.
- Well-articulated and polished: clear structure, confident word choice, no filler.
- Concise — get to the point without sounding abrupt. No rambling, no repetition.
- Avoid over-apologizing, excessive hedging, or generic corporate phrases
  ("please don't hesitate to reach out", "I hope this email finds you well").
- Sound competent and considered, not stiff or robotic.
- Sign off with just my first name.
"""


def polish_email(raw_text: str, max_retries: int = 5) -> str:
    """Takes the user's own rough draft and rewrites it in a polished,
    professional tone — keeps their intent and content, just improves
    the phrasing, structure, and tone."""
    prompt = (
        "Here is a rough email draft written by the user:\n\n"
        f"{raw_text}\n\n"
        f"Rewrite it following this style guide:\n{REPLY_STYLE_GUIDE}\n\n"
        "Keep the original meaning, intent, and all key details/facts exactly "
        "as given — do not add new information or change what is being asked. "
        "Only improve the wording, tone, grammar, and structure.\n\n"
        "Reply with ONLY the rewritten email body text. No subject line, "
        "no commentary, no markdown, no explanation of changes."
    )

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt,
            )
            return response.text.strip()
        except genai_errors.ServerError:
            wait = 10 * (attempt + 1)
            print(f"  Model overloaded (attempt {attempt + 1}/{max_retries}), retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError("Gemini API is overloaded after multiple retries. Try again in a few minutes.")


def main():
    to = input("Recipient email: ").strip()
    subject = input("Subject: ").strip()
    print("Type your email content below.")
    print("When done, type END on its own line and press Enter:\n")

    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)
    raw_text = "\n".join(lines)

    print("\nPolishing your draft...")
    body = polish_email(raw_text)

    service = get_gmail_service()
    create_new_draft(service, to=to, subject=subject, body=body)

    print(f"\nDraft created — To: {to} | Subject: {subject}")
    print("Check your Gmail Drafts folder to review and send.\n")
    print("--- Polished version ---")
    print(body)


if __name__ == "__main__":
    main()