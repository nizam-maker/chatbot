# core/engine.py
# ─────────────────────────────────────────────────────────────
#  The AI brain — wires memory + retrieval + Claude API
#  Works for ANY tenant — behaviour is driven by config.py
# ─────────────────────────────────────────────────────────────

import os
import anthropic
from dotenv import load_dotenv

from core.memory import load_session, save_session, add_message
from core.ingest import retrieve

load_dotenv()

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL   = "claude-sonnet-4-20250514"


def _db_context(user_msg: str) -> str:
    """
    Query the structured database based on keywords in the user message.
    Returns a formatted string injected into the system prompt.
    """
    try:
        from tenants.laman_auto.schema import (
            search_cars, get_active_rebates, get_cars_by_brand
        )

        msg_lower = user_msg.lower()
        lines     = []

        # Detect brand mentions
        brands = {
            "perodua": "Perodua", "proton": "Proton",
            "honda": "Honda",     "toyota": "Toyota"
        }
        # Detect model mentions
        models = {
            "axia": "Axia",   "myvi": "Myvi",   "bezza": "Bezza",
            "saga": "Saga",   "x50": "X50",     "x70": "X70",
            "city": "City",   "hr-v": "HR-V",   "hrv": "HR-V",
            "vios": "Vios",   "yaris": "Yaris"
        }

        matched_brand = next(
            (v for k, v in brands.items() if k in msg_lower), None
        )
        matched_model = next(
            (v for k, v in models.items() if k in msg_lower), None
        )

        # Price range detection
        max_price = None
        price_keywords = {
            "bawah 50k": 50_000,  "under 50k": 50_000,
            "bawah 60k": 60_000,  "under 60k": 60_000,
            "bawah 80k": 80_000,  "under 80k": 80_000,
            "bawah 100k": 100_000,"under 100k": 100_000,
        }
        for kw, price in price_keywords.items():
            if kw in msg_lower:
                max_price = price
                break

        # Query cars from DB
        cars = search_cars(
            brand     = matched_brand,
            max_price = max_price,
        )

        # If specific model mentioned, filter further
        if matched_model:
            cars = [c for c in cars if matched_model.lower() in c.model.lower()]

        if cars:
            lines.append("[Structured database — available cars]")
            for c in cars[:6]:  # limit to 6 results
                rebates = get_active_rebates(c.car_id)
                rebate_str = ""
                if rebates:
                    total = sum(r.amount for r in rebates)
                    rebate_str = f" | Rebat: RM{total:,.0f}"

                lines.append(
                    f"• {c.brand} {c.model} {c.variant} ({c.year}) — "
                    f"RM{c.price_otr:,.0f} OTR | "
                    f"Stok: {c.stock} unit | "
                    f"Warna: {c.colour} | "
                    f"Fuel: {c.fuel_cons} km/l"
                    f"{rebate_str}"
                )

        return "\n".join(lines)

    except Exception as e:
        # DB not available — fail silently, ChromaDB still works
        return ""


def chat(
    user_msg:    str,
    session_id:  str,
    tenant_cfg:  dict,
    customer_id: str = "guest",
) -> dict:
    """
    Send a user message and get a reply.

    tenant_cfg must contain:
        TENANT_ID     str
        SYSTEM_PROMPT str
        DOMAINS       list[str]

    Returns:
        {
          "reply":         str,
          "session_id":    str,
          "customer_name": str,
          "car_interest":  str,
        }
    """
    tenant_id = tenant_cfg["TENANT_ID"]

    # 1. Load episodic memory for this session
    session = load_session(session_id)
    session["tenant_id"]   = tenant_id
    session["customer_id"] = customer_id

    # 2. Retrieve relevant knowledge chunks from ChromaDB
    chunks  = retrieve(user_msg, tenant_id, tenant_cfg["DOMAINS"], n=4)
    context = "\n\n".join(chunks) if chunks else ""

    # 3. Query structured database for prices, stock, rebates
    db_context = _db_context(user_msg)

    # 4. Build system prompt — inject knowledge context + DB data + customer saga
    system = tenant_cfg["SYSTEM_PROMPT"]

    if db_context:
        system += f"\n\n{db_context}"
    if context:
        system += f"\n\n[Knowledge base — brochures & specs]\n{context}"
    if session.get("summary"):
        system += f"\n\n[Customer saga so far]\n{session['summary']}"
    if session.get("customer_name"):
        system += f"\n\nCustomer name: {session['customer_name']}"

    # 4. Build message history (last 10 turns from memory)
    messages = session["messages"] + [
        {"role": "user", "content": user_msg}
    ]

    # 5. Call Claude
    response = _client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=system,
        messages=messages,
    )
    reply = response.content[0].text

    # 6. Update session memory
    session = add_message(session, "user",      user_msg)
    session = add_message(session, "assistant", reply)
    save_session(session)

    return {
        "reply":         reply,
        "session_id":    session_id,
        "customer_name": session.get("customer_name", ""),
        "car_interest":  session.get("car_interest",  ""),
    }