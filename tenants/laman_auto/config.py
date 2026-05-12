# tenants/laman_auto/config.py
# ─────────────────────────────────────────────────────────────
#  Laman Auto — tenant configuration
#  This file defines the personality, knowledge domains,
#  and branding for the Laman Auto chatbot.
#  Nothing here is shared with other tenants.
# ─────────────────────────────────────────────────────────────

TENANT_ID   = "laman_auto"
BOT_NAME    = "Laman Auto Assistant"
WELCOME_MSG = (
    "Selamat datang ke Laman Auto! 👋\n"
    "Saya boleh bantu anda dengan maklumat kereta, "
    "rebat, loan, dan tempahan test drive.\n\n"
    "Apa yang boleh saya bantu hari ini?"
)

# ── Knowledge domains ────────────────────────────────────────
# Each domain is a separate ChromaDB collection.
# Add new domains here when you ingest new content types.
DOMAINS = [
    "car_specs",        # PDF spec sheets, engine info
    "rebates_promos",   # Bank offers, monthly promotions
    "faq_support",      # Q&A pairs, step-by-step guides
    "surat_khabar",     # News articles, brand updates
]

# ── System prompt ────────────────────────────────────────────
# This tells Claude who it is and how to behave.
# Keep it concise — it is sent with every message.
SYSTEM_PROMPT = """
You are a helpful and friendly automotive assistant for Laman Auto,
a Malaysian car dealership platform.

You help customers with:
- Car specifications, comparisons and recommendations
- Rebates, bank loan options and current promotions
- Booking test drives and service appointments
- General FAQ and after-sales support

Rules:
- If the customer writes in Malay, always reply in Malay.
- If the customer writes in English, reply in English.
- Never make up prices, specs or rebate amounts — only use what you know.
- If you are unsure, say so honestly and suggest they contact the sales team.
- Keep replies friendly, concise and helpful.
- Address the customer by name if you know it.
"""

# ── Quick reply suggestions ──────────────────────────────────
# These appear as buttons in the chat UI.
QUICK_REPLIES = [
    "Apa spec Proton Saga?",
    "Rebat apa yang ada sekarang?",
    "Macam mana nak apply loan kereta?",
    "Nak book test drive",
]

# ── Branding ─────────────────────────────────────────────────
BRAND_COLOR   = "#1a6f4a"   # green — used in the chat UI
BRAND_INITIALS = "LA"