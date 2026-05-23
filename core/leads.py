# core/leads.py
# ─────────────────────────────────────────────────────────────
#  Lead capture — detects buying intent, extracts contact info,
#  saves to Supabase, sends email alert to sales team
# ─────────────────────────────────────────────────────────────

import os
import re
import logging
import smtplib
from email.mime.text    import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime           import datetime
from dotenv             import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────
SMTP_HOST   = os.getenv("SMTP_HOST",   "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = os.getenv("SMTP_USER",   "")
SMTP_PASS   = os.getenv("SMTP_PASS",   "")
SALES_EMAIL = os.getenv("SALES_EMAIL", "")

# ── Intent keywords ───────────────────────────────────────────
BUYING_INTENT_KEYWORDS = [
    # Malay
    "nak beli", "ingin beli", "berminat", "nak tempah", "nak book",
    "test drive", "berapa harga", "boleh arrange", "macam mana nak",
    "nak tahu lebih", "boleh hubungi", "proceed", "confirm",
    "nak ambil", "buat keputusan", "pilih", "deposit",
    # English
    "want to buy", "interested", "book", "purchase", "proceed",
    "how much", "can i get", "i want", "let me know", "contact me",
    "arrange", "when can", "available",
]

# ── Phone number patterns (Malaysia) ─────────────────────────
PHONE_PATTERNS = [
    r"(?:60|0)?1[0-9]{8,9}",           # 01XXXXXXXX — no separator
    r"(?:60|0)?1[0-9][-\s][0-9]{7,8}", # 01X-XXXXXXX — with separator
    r"(?:60|0)?3[-\s]?[0-9]{7,8}",     # 03-XXXXXXXX
    r"\b0[0-9]{9,10}\b",               # general 10-11 digit MY
]

# ── Name patterns ─────────────────────────────────────────────
NAME_PATTERNS = [
    r"(?:nama saya|my name is|i am|i'm|panggil saya|call me)\s+([A-Za-z\s]{2,30})",
    r"(?:nama:|name:)\s*([A-Za-z\s]{2,30})",
]


def has_buying_intent(messages: list[dict]) -> bool:
    """
    Check if the conversation shows buying intent.
    Requires at least 3 user messages AND intent keywords.
    """
    user_messages = [m for m in messages if m["role"] == "user"]
    if len(user_messages) < 3:
        return False

    # Check last 5 messages for intent keywords
    recent = " ".join(
        m["content"].lower() for m in messages[-5:]
        if m["role"] == "user"
    )
    return any(kw in recent for kw in BUYING_INTENT_KEYWORDS)


def extract_phone(text: str) -> str | None:
    """Extract Malaysian phone number from text."""
    # Remove common words that might confuse the regex
    cleaned = text.replace("telefon", "").replace("phone", "")\
                  .replace("nombor", "").replace("number", "")
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, cleaned)
        if match:
            phone = re.sub(r"[\s\-]", "", match.group())
            if 10 <= len(phone) <= 12:
                return phone
    return None


def extract_name(text: str) -> str | None:
    """Extract name from text using common patterns."""
    for pattern in NAME_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip().title()
            if 2 <= len(name) <= 40:
                return name
    return None


def should_ask_for_contact(session: dict) -> bool:
    """
    Decide if the bot should ask for contact info.
    Only ask once per session, after buying intent detected.
    """
    if session.get("lead_captured"):
        return False
    if session.get("contact_asked"):
        return False
    return has_buying_intent(session.get("messages", []))


def get_lead_prompt(car_interest: str = "") -> str:
    """
    Return a natural prompt asking for contact info.
    Injected into the system prompt when intent is detected.
    """
    car_part = f" tentang {car_interest}" if car_interest else ""
    return f"""
LEAD CAPTURE INSTRUCTION (inject naturally into response):
The customer has shown buying interest{car_part}.
In your next response, naturally ask for their name and phone number.
Example: "Untuk saya bantu anda dengan lebih lanjut, boleh saya dapatkan nama dan nombor telefon anda? Pasukan jualan kami akan hubungi anda secepatnya."
Only ask ONCE. After asking, set a reminder that contact was requested.
Do NOT ask again in subsequent messages.
"""


def save_lead(
    session_id:   str,
    tenant_id:    str,
    name:         str,
    phone:        str,
    car_interest: str = "",
    source:       str = "chatbot"
) -> dict | None:
    """Save lead to Supabase customers table."""
    try:
        from core.supabase_client import sb

        # Only columns that exist in the customers table
        data = {
            "name":       name or "Unknown",
            "phone":      phone,
            "interest":   car_interest,
            "source":     source,
            "session_id": session_id,
            "notified":   False,
        }

        res = sb.table("customers").upsert(
            data, on_conflict="phone"
        ).execute()

        logger.info(f"[leads] Lead saved: {name} {phone}")
        return res.data[0] if res.data else None

    except Exception as e:
        logger.error(f"[leads] Save failed: {e}")
        return None


def send_lead_email(
    name:         str,
    phone:        str,
    car_interest: str,
    session_id:   str,
    tenant_name:  str = "Laman Auto"
) -> bool:
    """Send email notification to sales team."""
    if not SMTP_USER or not SMTP_PASS or not SALES_EMAIL:
        logger.warning("[leads] Email not configured — skipping notification")
        return False

    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = f"🚗 New Lead — {name} | {tenant_name}"
        msg["From"]    = SMTP_USER
        msg["To"]      = SALES_EMAIL

        html = f"""
<html><body style="font-family:sans-serif;padding:20px">
  <h2 style="color:#1a6f4a">New Lead from Chatbot 🎉</h2>
  <table style="border-collapse:collapse;width:100%;max-width:500px">
    <tr><td style="padding:8px;border:1px solid #e2e0d8;font-weight:bold;background:#f4f3ef">Name</td>
        <td style="padding:8px;border:1px solid #e2e0d8">{name}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e2e0d8;font-weight:bold;background:#f4f3ef">Phone</td>
        <td style="padding:8px;border:1px solid #e2e0d8">
          <a href="tel:{phone}">{phone}</a></td></tr>
    <tr><td style="padding:8px;border:1px solid #e2e0d8;font-weight:bold;background:#f4f3ef">Interest</td>
        <td style="padding:8px;border:1px solid #e2e0d8">{car_interest or "General inquiry"}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e2e0d8;font-weight:bold;background:#f4f3ef">Time</td>
        <td style="padding:8px;border:1px solid #e2e0d8">{datetime.now().strftime("%d %b %Y, %I:%M %p")}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e2e0d8;font-weight:bold;background:#f4f3ef">Session</td>
        <td style="padding:8px;border:1px solid #e2e0d8;font-size:12px;color:#7a7870">{session_id}</td></tr>
  </table>
  <p style="margin-top:16px;color:#7a7870;font-size:13px">
    This lead was captured automatically by the {tenant_name} chatbot.
  </p>
</body></html>"""

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, SALES_EMAIL, msg.as_string())

        logger.info(f"[leads] Email sent to {SALES_EMAIL}")
        return True

    except Exception as e:
        logger.error(f"[leads] Email failed: {e}")
        return False


def process_lead_from_message(
    user_msg:  str,
    session:   dict,
    tenant_id: str
) -> dict:
    """
    Check if the user message contains contact info.
    If found, save lead and send email.
    Returns updated session flags.
    """
    updates = {}

    # Already captured — skip
    if session.get("lead_captured"):
        return updates

    # Look for phone number in any message after buying intent shown
    phone = extract_phone(user_msg)
    if not phone:
        return updates

    # Got a phone number — extract name from message or session
    name = (
        extract_name(user_msg)
        or session.get("customer_name")
        or ""
    )
    car_interest = session.get("car_interest", "")

    # Save to Supabase
    save_lead(
        session_id   = session.get("session_id", ""),
        tenant_id    = tenant_id,
        name         = name,
        phone        = phone,
        car_interest = car_interest,
    )

    # Send email alert
    send_lead_email(
        name         = name,
        phone        = phone,
        car_interest = car_interest,
        session_id   = session.get("session_id", ""),
    )

    updates["lead_captured"] = True
    updates["customer_name"] = name or session.get("customer_name", "")
    logger.info(f"[leads] ✓ Lead captured: {name} {phone} — {car_interest}")
    return updates