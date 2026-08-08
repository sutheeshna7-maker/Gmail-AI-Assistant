import os
import json
from groq import Groq
from gmail_connect import (
    get_gmail_service,
    get_recent_emails,
    search_emails,
    send_email
)

# -----------------------------
# Gmail Connection
# -----------------------------
service = get_gmail_service()
print("Connected to Gmail successfully!")

# -----------------------------
# Groq Client
# -----------------------------
client = Groq(api_key=os.environ["GROQ_API_KEY"])

# -----------------------------
# Read Recent Emails
# -----------------------------
inbox = get_recent_emails(service, max_results=5)


# -----------------------------
# Show Inbox
# -----------------------------
def show_inbox(inbox):
    for email in inbox:
        read_status = "✅" if email["is_read"] else "🔴"
        print(f"{read_status} {email['sender']} - {email['subject']}")


# -----------------------------
# Unread Emails
# -----------------------------
def unread_emails(inbox):
    result = []

    for email in inbox:
        if not email["is_read"]:
            result.append(email)

    return result


# -----------------------------
# AI Summary
# -----------------------------
def summarize_email(email):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": f"Summarize this email in one short sentence.\n\n{email['body']}"
            }
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# AI Classification
# -----------------------------
def classify_email(email):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": (
                    "Classify this email into exactly one category.\n\n"
                    "Priority = Work emails, OTPs, security alerts, interviews, invoices, deadlines, meetings.\n"
                    "Spam = Advertisements, promotions, newsletters, unwanted notifications.\n"
                    "Personal = Friends, family, greetings, casual conversations.\n\n"
                    "Reply ONLY with: Priority, Spam, or Personal.\n\n"
                    f"Subject: {email['subject']}\n"
                    f"Body: {email['body']}"
                )
            }
        ]
    )

    return response.choices[0].message.content.strip()


# -----------------------------
# AI Draft Reply
# -----------------------------
def draft_reply(email):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": (
                    "Write a short professional reply."
                    " Keep it under 3 sentences.\n\n"
                    f"Subject: {email['subject']}\n"
                    f"Body: {email['body']}"
                )
            }
        ]
    )

    return response.choices[0].message.content


# -----------------------------
# AI Task Extraction (JSON)
# -----------------------------
def extract_tasks(email):

    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        temperature=0,

        messages=[

            {
                "role": "system",
                "content":
                    "You are an AI assistant that extracts structured information from emails. "
                    "Return ONLY valid JSON. "
                    "Never return markdown. "
                    "Never explain anything."
            },

            {
                "role": "user",
                "content": f"""
Read this email.

Extract

1. Tasks
2. Deadlines
3. Meetings

Return ONLY this JSON.

{{
    "tasks":[
        {{
            "task":"",
            "deadline":""
        }}
    ],

    "meetings":[
        {{
            "title":"",
            "time":""
        }}
    ]
}}

If there are no tasks return

{{
    "tasks":[],
    "meetings":[]
}}

Subject:
{email["subject"]}

Body:
{email["body"]}
"""
            }
        ]
    )

    try:
        return json.loads(response.choices[0].message.content)

    except Exception:

        print("\n⚠ AI returned invalid JSON\n")
        print(response.choices[0].message.content)

        return {
            "tasks": [],
            "meetings": []
        }


# -----------------------------
# SHOW INBOX
# -----------------------------
print("\nRecent Emails\n")
show_inbox(inbox)


# -----------------------------
# UNREAD EMAILS
# -----------------------------
print("\nUnread Emails\n")
show_inbox(unread_emails(inbox))


# -----------------------------
# SUMMARY
# -----------------------------
print("\nSummary of First Email\n")
print(summarize_email(inbox[0]))


# -----------------------------
# CLASSIFICATION
# -----------------------------
print("\nClassification\n")

for email in inbox:
    category = classify_email(email)
    print(f"{email['subject']} -> {category}")


# -----------------------------
# DRAFT REPLY
# -----------------------------
print("\nDraft Reply\n")
print(draft_reply(inbox[0]))


# -----------------------------
# SEARCH
# -----------------------------
print("\nSearch Results (LinkedIn)\n")

results = search_emails(
    service,
    "from:linkedin",
    max_results=3
)

show_inbox(results)


# -----------------------------
# TASK EXTRACTION
# -----------------------------
print()
print("=" * 70)
print("AI TASK EXTRACTION (JSON)")
print("=" * 70)

for email in inbox:

    result = extract_tasks(email)

    print()
    print(f"📧 Subject : {email['subject']}")
    print()

    print("📋 Tasks")

    if result["tasks"]:

        for task in result["tasks"]:

            print(f"• {task['task']}")

            if task["deadline"]:
                print(f"   📅 Deadline : {task['deadline']}")

    else:
        print("No Tasks")

    print()

    print("📅 Meetings")

    if result["meetings"]:

        for meeting in result["meetings"]:

            print(f"• {meeting['title']}")
            print(f"   🕒 Time : {meeting['time']}")

    else:
        print("No Meetings")

    print("-" * 70)