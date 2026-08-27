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
from core.analytics import track

load_dotenv()

_platform_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL_DEFAULT     = "claude-sonnet-4-6"
MODEL_HAIKU       = "claude-haiku-4-5-20251001"


def _get_client_and_model(tenant_cfg: dict):
    """
    Return the correct Anthropic client and model for this tenant.
    If tenant has BYOK key → use theirs.
    Otherwise → use platform key.
    """
    from core.supabase_client import sb, maybe_single
    from core.crypto import decrypt

    try:
        slug   = tenant_cfg.get("TENANT_ID", "")
        tenant = maybe_single(sb.table("tenants").select(
            "billing_mode, ai_api_key_enc, ai_model"
        ).eq("slug", slug))

        if tenant and tenant.get("billing_mode") == "byok" \
                and tenant.get("ai_api_key_enc"):
            key    = decrypt(tenant["ai_api_key_enc"])
            model  = tenant.get("ai_model") or MODEL_DEFAULT
            client = anthropic.Anthropic(api_key=key)
            return client, model

    except Exception as e:
        print(f"[engine] BYOK lookup failed, using platform key: {e}")

    return _platform_client, MODEL_DEFAULT


# Spelling variants customers use that don't appear in the catalogue itself.
_MODEL_ALIASES = {"hrv": "HR-V", "hr v": "HR-V", "crv": "CR-V", "cr v": "CR-V"}

_CATALOGUE_CACHE: dict = {}
_CATALOGUE_TTL   = 300  # seconds


def _catalogue_terms(tenant_uuid: str | None) -> tuple[dict, dict]:
    """
    Build {keyword: canonical} maps for brands and models from the tenant's
    cars table. Cached briefly — this runs on every message, but the
    catalogue changes only when a sync runs.
    """
    if not tenant_uuid:
        return {}, {}

    import time
    hit = _CATALOGUE_CACHE.get(tenant_uuid)
    if hit and time.time() - hit[0] < _CATALOGUE_TTL:
        return hit[1], hit[2]

    from core.supabase_client import sb
    rows = sb.table("cars").select("brand,model") \
             .eq("tenant_id", tenant_uuid).execute().data or []

    brands = {r["brand"].lower(): r["brand"] for r in rows if r.get("brand")}
    models = {r["model"].lower(): r["model"] for r in rows if r.get("model")}
    for alias, canonical in _MODEL_ALIASES.items():
        if canonical.lower() in models:
            models[alias] = canonical

    _CATALOGUE_CACHE[tenant_uuid] = (time.time(), brands, models)
    return brands, models


def _rebate_label(r: dict) -> str:
    """Customer-facing wording for one rebate."""
    return (r.get("rebate_display") or r.get("rebate_name")
            or r.get("description") or r.get("rebate_type") or "").strip()


def _format_rebates(rebates: list[dict]) -> str:
    """
    Render a car's rebates for the prompt.

    Cash rebates and freebies are kept apart on purpose: a freebie carries
    amount 0 with its worth in `freebie_value`, so folding it into the cash
    total would have the bot quote a discount that was never offered.
    Eligibility flags are surfaced so the bot caveats rather than promises.
    """
    if not rebates:
        return ""

    cash, freebies = [], []
    for r in rebates:
        amount = float(r.get("amount") or 0)
        if amount > 0:
            cash.append(r)
        elif r.get("rebate_type") == "freebie" or r.get("freebie_value"):
            freebies.append(r)

    parts = []
    if cash:
        total  = sum(float(r.get("amount") or 0) for r in cash)
        labels = ", ".join(dict.fromkeys(filter(None, (_rebate_label(r) for r in cash))))
        parts.append(f"Rebat: RM{total:,.0f}" + (f" ({labels})" if labels else ""))
    if freebies:
        labels = ", ".join(dict.fromkeys(filter(None, (_rebate_label(r) for r in freebies))))
        parts.append("Percuma: " + (labels or "hadiah promosi"))

    if not parts:
        return ""

    caveats = []
    if any(r.get("requires_code") for r in rebates):
        caveats.append("perlu kod promo")
    if any(r.get("new_customer_only") for r in rebates):
        caveats.append("pelanggan baharu sahaja")
    if caveats:
        parts.append("Syarat: " + ", ".join(caveats))

    return " | " + " | ".join(parts)


def _db_context(user_msg: str, tenant_id: str) -> str:
    """
    Query Supabase for cars and rebates based on message keywords.
    Returns a formatted string injected into the system prompt.

    tenant_id is the tenant slug (e.g. "laman_auto") — used to scope the
    cars query to this tenant and to look up any live external car API.
    """
    try:
        from core.supabase_client import sb, get_tenant
        from core.tenant_api import (fetch_live_cars, fetch_live_specs,
                                     fetch_live_news, fetch_live_rebates)

        tenant_row  = get_tenant(tenant_id)
        tenant_uuid = tenant_row["id"] if tenant_row else None

        msg_lower = user_msg.lower()

        news_kw = ["berita", "news", "terkini", "update", "pengumuman", "announcement"]
        spec_kw = ["spec", "spesifikasi", "horsepower", "torque", "dimension", "kuasa"]
        rebate_kw = ["rebat", "rebate", "diskaun", "discount", "promosi", "promo"]
        wants_news = any(k in msg_lower for k in news_kw)
        wants_spec = any(k in msg_lower for k in spec_kw)
        wants_rebate = any(k in msg_lower for k in rebate_kw)

        # Brands and models are read from the tenant's own catalogue rather
        # than hardcoded — a hardcoded list silently misses whatever the
        # tenant adds, and the question then falls through to a generic
        # cheapest-cars answer about the wrong cars entirely.
        brands, models = _catalogue_terms(tenant_uuid)

        matched_brand = next(
            (v for k, v in brands.items() if k in msg_lower), None)
        # Longest first, so "city hatchback" wins over "city".
        matched_model = next(
            (v for k, v in sorted(models.items(), key=lambda kv: -len(kv[0]))
             if k in msg_lower), None)

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
                      "kereta", "car", "beli", "buy"] + news_kw
        if not matched_brand and not matched_model and not max_price \
                and not wants_news:
            if not any(k in msg_lower for k in general_kw):
                return ""

        # News/updates — not car-scoped, handled separately from the cars query.
        news_lines = []
        if wants_news:
            live_news = fetch_live_news(tenant_uuid) if tenant_uuid else None
            if live_news:
                for n in live_news[:5]:
                    if n.get("title"):
                        news_lines.append(f"• {n['title']}" + (f" — {n['body']}" if n.get("body") else ""))
            elif tenant_uuid:
                cached = sb.table("news_updates").select("*") \
                    .eq("tenant_id", tenant_uuid) \
                    .order("published_at", desc=True).limit(5).execute().data or []
                for n in cached:
                    news_lines.append(f"• {n['title']}" + (f" — {n['body']}" if n.get("body") else ""))

            # Pure news question (no car/price signal) — return news only.
            car_kw = [k for k in general_kw if k not in news_kw]
            if not matched_brand and not matched_model and not max_price \
                    and not any(k in msg_lower for k in car_kw):
                if not news_lines:
                    return ""
                return "[Latest news & updates]\n" + "\n".join(news_lines)

        # ── Rebates ───────────────────────────────────────────
        # Fetched before the cars query so a rebate question can be scoped
        # to cars that actually carry one. Live API first, cached table as
        # fallback — same pattern as cars/specs/news.
        rebates_by_car = {}
        live_rebates = fetch_live_rebates(tenant_uuid) if tenant_uuid else None
        if live_rebates:
            for r in live_rebates:
                if r.get("car_id") and r.get("amount") and r.get("is_active", True):
                    rebates_by_car.setdefault(r["car_id"], []).append(r)
        elif tenant_uuid:
            cached_rebates = sb.table("rebates").select("*") \
                .eq("tenant_id", tenant_uuid).eq("is_active", True) \
                .execute().data or []
            for r in cached_rebates:
                if r.get("car_id"):
                    rebates_by_car.setdefault(r["car_id"], []).append(r)

        # ── Query Supabase ────────────────────────────────────
        q = sb.table("cars").select("*").eq("status", "available")
        if tenant_uuid:
            q = q.eq("tenant_id", tenant_uuid)

        # "Ada rebate tak?" with no car named — show cars that have a
        # rebate, not simply the cheapest ones.
        if wants_rebate and rebates_by_car \
                and not matched_brand and not matched_model and not max_price:
            q = q.in_("car_id", list(rebates_by_car))

        if matched_brand:
            q = q.ilike("brand", f"%{matched_brand}%")
        if matched_model:
            q = q.ilike("model", f"%{matched_model}%")
        if max_price:
            q = q.lte("price_otr", max_price)

        cars = q.order("price_otr").limit(8).execute().data or []

        # The customer named a car and we stock it, but every variant is
        # sold out. Answer with the real reason rather than no context at
        # all — an empty context invites the model to guess at prices.
        sold_out = False
        if not cars and (matched_brand or matched_model):
            q_any = sb.table("cars").select("*")
            if tenant_uuid:
                q_any = q_any.eq("tenant_id", tenant_uuid)
            if matched_brand:
                q_any = q_any.ilike("brand", f"%{matched_brand}%")
            if matched_model:
                q_any = q_any.ilike("model", f"%{matched_model}%")
            cars = q_any.order("price_otr").limit(8).execute().data or []
            sold_out = bool(cars)

        # A rebate question with nothing to show means there are no active
        # promotions — say so, instead of falling through to a list of
        # unrelated cars that carry no rebate at all.
        if wants_rebate and not rebates_by_car \
                and not matched_brand and not matched_model and not max_price:
            return ("[Rebat & promosi]\n"
                    "Tiada rebat atau promosi aktif buat masa ini.")

        if wants_rebate and not cars and not matched_brand and not matched_model:
            return ("[Rebat & promosi]\n"
                    "Tiada rebat atau promosi aktif buat masa ini.")

        # General question — return top available cars
        if not cars and not matched_brand and not matched_model:
            q2 = sb.table("cars").select("*").eq("status", "available")
            if tenant_uuid:
                q2 = q2.eq("tenant_id", tenant_uuid)
            cars = q2.order("price_otr").limit(6).execute().data or []

        if not cars:
            if wants_news and news_lines:
                return "[Latest news & updates]\n" + "\n".join(news_lines)
            return ""

        # If asking about a specific brand/model, prefer live price/stock
        # from the tenant's own API (if configured) over the cached values.
        if tenant_uuid and (matched_brand or matched_model):
            live_cars = fetch_live_cars(tenant_uuid, brand=matched_brand, model=matched_model)
            if live_cars:
                live_by_id = {lc["car_id"]: lc for lc in live_cars if lc.get("car_id")}
                for c in cars:
                    live = live_by_id.get(c["car_id"])
                    if live:
                        c.update(live)

        # Live specs (if a spec API is configured) — merged in per car_id.
        specs_by_car = {}
        if wants_spec and tenant_uuid:
            live_specs = fetch_live_specs(tenant_uuid)
            if live_specs:
                for s in live_specs:
                    specs_by_car.setdefault(s.get("car_id"), []).append(s)
            else:
                car_ids = [c["car_id"] for c in cars]
                cached_specs = sb.table("car_specs").select("*") \
                    .eq("tenant_id", tenant_uuid).in_("car_id", car_ids).execute().data or []
                for s in cached_specs:
                    specs_by_car.setdefault(s["car_id"], []).append(s)

        if sold_out:
            lines = ["[Structured database — model in catalogue but NO STOCK "
                     "right now. Tell the customer it is currently unavailable "
                     "and offer to take their details or suggest alternatives. "
                     "Prices below are for reference only.]"]
        else:
            lines = ["[Structured database — available cars]"]

        for c in cars:
            rebate_str = _format_rebates(rebates_by_car.get(c["car_id"], []))

            spec_str = ""
            car_specs = specs_by_car.get(c["car_id"])
            if car_specs:
                spec_str = " | Spec: " + ", ".join(
                    f"{s.get('spec_key')}: {s.get('spec_value')}" for s in car_specs if s.get("spec_key"))

            lines.append(
                f"• {c['brand']} {c['model']} {c['variant']} ({c['year']}) — "
                f"RM{c['price_otr']:,.0f} OTR | "
                f"Stok: {c['stock']} unit | "
                f"Warna: {c['colour']} | "
                f"Fuel: {c['fuel_cons']} km/l | "
                f"Engine: {c['engine_cc']}cc {c['transmission']}"
                f"{rebate_str}{spec_str}"
            )

        if wants_news and news_lines:
            lines.insert(0, "[Latest news & updates]\n" + "\n".join(news_lines) + "\n")

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

    if not session.get("messages"):
        track("chat_start", tenant_id, session_id=session_id,
              customer_id=customer_id, data={"source": "widget"})

    track("message_sent", tenant_id,
          session_id=session_id,
          customer_id=customer_id,
          data={"question": user_msg[:200]})

    # 2. Retrieve relevant knowledge chunks from ChromaDB
    chunks  = retrieve(user_msg, tenant_id, tenant_cfg["DOMAINS"], n=4)
    context = "\n\n".join(chunks) if chunks else ""

    # 3. Query structured DB (Supabase) for prices, stock, rebates
    db_context = _db_context(user_msg, tenant_id)

    if db_context:
        for brand in ["Perodua", "Proton", "Honda", "Toyota"]:
            if brand.lower() in user_msg.lower():
                for model in ["Axia", "Myvi", "Bezza", "Ativa", "Alza",
                              "Saga", "X50", "X70", "S70",
                              "City", "HR-V", "Civic",
                              "Vios", "Yaris", "Veloz"]:
                    if model.lower() in user_msg.lower():
                        track("car_queried", tenant_id,
                              session_id=session_id,
                              data={"brand": brand, "model": model})
                        break

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

    # 5. Build system prompt — static tenant prompt (cached) + dynamic context
    #    Splitting these into separate blocks lets Claude cache the tenant
    #    prompt across requests (it rarely changes), so only the dynamic
    #    part (DB/RAG context, lead prompt, summary) is billed at full price.
    dynamic_parts = []

    if db_context:
        dynamic_parts.append(db_context)
    if context:
        dynamic_parts.append(f"[Knowledge base — brochures & specs]\n{context}")
    if db_context and context:
        dynamic_parts.append(
            "Note: if price or stock figures conflict between the "
            "structured database and the knowledge base, always use the "
            "structured database — it is more current."
        )

    # Inject lead capture prompt if intent detected
    if should_ask_for_contact(session):
        dynamic_parts.append(get_lead_prompt(session.get("car_interest", "")))
        session["contact_asked"] = True

    # Ground the model's reply in what actually happened on the backend —
    # never let it improvise a "your info is recorded" confirmation that
    # didn't really happen.
    if lead_updates.get("lead_just_saved"):
        saved = lead_updates["lead_just_saved"]
        dynamic_parts.append(
            f"LEAD CAPTURE RESULT: Successfully recorded — name: {saved['name']}, "
            f"phone: {saved['phone']}. Confirm this to the customer and let them "
            "know the sales team will contact them soon."
        )
    elif lead_updates.get("phone_invalid_hint"):
        dynamic_parts.append(
            "LEAD CAPTURE RESULT: The customer just provided a phone number that "
            "looks incomplete or invalid (Malaysian mobile numbers have 10-11 "
            "digits). Do NOT say their information has been recorded. Instead, "
            "politely point out the number looks incomplete and ask them to "
            "re-confirm it."
        )
    elif lead_updates.get("lead_save_failed"):
        dynamic_parts.append(
            "LEAD CAPTURE RESULT: Saving the customer's contact info just failed "
            "on the backend. Do NOT say their information has been recorded. "
            "Apologize briefly and ask them to repeat their name and phone number."
        )

    if session.get("summary"):
        dynamic_parts.append(f"[Customer saga so far]\n{session['summary']}")
    if session.get("customer_name"):
        dynamic_parts.append(f"Customer name: {session['customer_name']}")

    system = [
        {
            "type":          "text",
            "text":          tenant_cfg["SYSTEM_PROMPT"],
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if dynamic_parts:
        system.append({"type": "text", "text": "\n\n".join(dynamic_parts)})

    # 5. Build message history (last 10 turns from memory)
    messages = session["messages"] + [
        {"role": "user", "content": user_msg}
    ]

    # 6. Get correct client + model (platform or BYOK)
    client, model = _get_client_and_model(tenant_cfg)

    # Route simple, low-stakes messages (no DB/RAG context retrieved, short
    # text) to the cheaper Haiku model. Only applies to platform-billed
    # tenants — BYOK tenants keep whatever model they explicitly chose.
    if model == MODEL_DEFAULT and not db_context and not context and len(user_msg) < 80:
        model = MODEL_HAIKU

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