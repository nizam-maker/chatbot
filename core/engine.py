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

_platform_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL_DEFAULT     = "claude-sonnet-4-20250514"


def _get_client_and_model(tenant_cfg: dict):
    """
    Return the correct Anthropic client and model for this tenant.
    If tenant has BYOK key → use theirs.
    Otherwise → use platform key.
    """
    from core.supabase_client import sb
    from core.crypto import decrypt

    try:
        slug   = tenant_cfg.get("TENANT_ID", "")
        tenant = sb.table("tenants").select(
            "billing_mode, ai_api_key_enc, ai_model"
        ).eq("slug", slug).single().execute().data

        if tenant and tenant.get("billing_mode") == "byok" \
                and tenant.get("ai_api_key_enc"):
            key    = decrypt(tenant["ai_api_key_enc"])
            model  = tenant.get("ai_model") or MODEL_DEFAULT
            client = anthropic.Anthropic(api_key=key)
            return client, model

    except Exception as e:
        print(f"[engine] BYOK lookup failed, using platform key: {e}")

    return _platform_client, MODEL_DEFAULT


def _db_context(user_msg: str) -> str:
    """
    Query Supabase for cars and rebates based on message keywords.
    Returns a formatted string injected into the system prompt.
    """
    try:
        from core.supabase_client import sb

        msg_lower = user_msg.lower()

        # Detect brand mentions
        brands = {
            "perodua": "Perodua", "proton": "Proton",
            "honda":   "Honda",   "toyota": "Toyota"
        }

        # Detect model mentions
        models = {
            "axia":  "Axia",   "myvi":  "Myvi",   "bezza": "Bezza",
            "ativa": "Ativa",  "alza":  "Alza",
            "saga":  "Saga",   "x50":   "X50",    "x70":   "X70",
            "s70":   "S70",
            "city":  "City",   "hr-v":  "HR-V",   "hrv":   "HR-V",
            "civic": "Civic",
            "vios":  "Vios",   "yaris": "Yaris",  "veloz": "Veloz",
        }

        matched_brand = next(
            (v for k, v in brands.items() if k in msg_lower), None)
        matched_model = next(
            (v for k, v in models.items() if k in msg_lower), None)

        # Price range detection
        max_price = None
        for kw, price in {
            "bawah 50k": 50000,  "under 50k": 50000,
            "bawah 60k": 60000,  "under 60k": 60000,
            "bawah 80k": 80000,  "under 80k": 80000,
            "bawah 100k": 100000,"under 100k": 100000,
            "50k": 50000, "60k": 60000,
            "80k": 80000, "100k": 100000,
        }.items():
            if kw in msg_lower:
                max_price = price
                break

        # Skip if no relevant keywords at all
        general_kw = ["harga", "price", "murah", "mahal", "stok",
                      "stock", "rebat", "rebate", "promosi", "promo",
                      "loan", "pinjaman", "spec", "spesifikasi",
                      "kereta", "car", "beli", "buy"]
        if not matched_brand and not matched_model and not max_price:
            if not any(k in msg_lower for k in general_kw):
                return ""

        # ── Query Supabase ────────────────────────────────────
        q = sb.table("cars").select("*").eq("status", "available")

        if matched_brand:
            q = q.ilike("brand", f"%{matched_brand}%")
        if matched_model:
            q = q.ilike("model", f"%{matched_model}%")
        if max_price:
            q = q.lte("price_otr", max_price)

        cars = q.order("price_otr").limit(8).execute().data or []

        # General question — return top available cars
        if not cars and not matched_brand and not matched_model:
            cars = sb.table("cars").select("*")\
                .eq("status", "available")\
                .order("price_otr").limit(6).execute().data or []

        if not cars:
            return ""

        lines = ["[Structured database — available cars]"]

        for c in cars:
            # Get active rebates for this car
            rebates = sb.table("rebates").select("*")\
                .eq("car_id", c["car_id"])\
                .eq("is_active", True)\
                .execute().data or []

            rebate_str = ""
            if rebates:
                total      = sum(r["amount"] for r in rebates)
                types      = ", ".join(set(r["rebate_type"] for r in rebates))
                rebate_str = f" | Rebat: RM{total:,.0f} ({types})"

            lines.append(
                f"• {c['brand']} {c['model']} {c['variant']} ({c['year']}) — "
                f"RM{c['price_otr']:,.0f} OTR | "
                f"Stok: {c['stock']} unit | "
                f"Warna: {c['colour']} | "
                f"Fuel: {c['fuel_cons']} km/l | "
                f"Engine: {c['engine_cc']}cc {c['transmission']}"
                f"{rebate_str}"
            )

        return "\n".join(lines)

    except Exception as e:
        print(f"[engine] DB context error: {e}")
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

    # 3. Query structured DB (Supabase) for prices, stock, rebates
    db_context = _db_context(user_msg)

    # 4. Check for lead capture opportunity
    from core.leads import (
        should_ask_for_contact, get_lead_prompt,
        process_lead_from_message
    )

    print(f"[debug] session contact_asked={session.get('contact_asked')} lead_captured={session.get('lead_captured')} msg={user_msg[:30]}", flush=True)



    # Process contact info from current message
    lead_updates = process_lead_from_message(user_msg, session, tenant_id)
    print(f"[debug] lead_updates={lead_updates}", flush=True)
    session.update(lead_updates)

    # 5. Build system prompt — inject all context layers
    system = tenant_cfg["SYSTEM_PROMPT"]

    if db_context:
        system += f"\n\n{db_context}"
    if context:
        system += f"\n\n[Knowledge base — brochures & specs]\n{context}"

    # Inject lead capture prompt if intent detected
    if should_ask_for_contact(session):
        system += get_lead_prompt(session.get("car_interest", ""))
        session["contact_asked"] = True

    if session.get("summary"):
        system += f"\n\n[Customer saga so far]\n{session['summary']}"
    if session.get("customer_name"):
        system += f"\n\nCustomer name: {session['customer_name']}"

    # 5. Build message history (last 10 turns from memory)
    messages = session["messages"] + [
        {"role": "user", "content": user_msg}
    ]

    # 6. Get correct client + model (platform or BYOK)
    client, model = _get_client_and_model(tenant_cfg)

    # 7. Call Claude
    response = client.messages.create(
        model      = model,
        max_tokens = 1000,
        system     = system,
        messages   = messages,
    )
    reply = response.content[0].text

    # 7. Update session memory
    session = add_message(session, "user",      user_msg)
    session = add_message(session, "assistant", reply)
    save_session(session)

    return {
        "reply":         reply,
        "session_id":    session_id,
        "customer_name": session.get("customer_name", ""),
        "car_interest":  session.get("car_interest",  ""),
    }