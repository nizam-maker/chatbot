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

    # 3. Build system prompt — inject knowledge context + customer saga
    system = tenant_cfg["SYSTEM_PROMPT"]

    if context:
        system += f"\n\n[Relevant knowledge]\n{context}"

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