# core/supabase_client.py
# ─────────────────────────────────────────────────────────────
#  Supabase client — single shared instance
#  Used by dashboard routes, scraper, file manager
# ─────────────────────────────────────────────────────────────

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # service_role key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Tenant helpers ────────────────────────────────────────────

def get_tenant(slug: str) -> dict | None:
    """Get tenant config by slug."""
    res = sb.table("tenants").select("*").eq("slug", slug).single().execute()
    return res.data


def get_all_tenants() -> list:
    """Get all active tenants."""
    res = sb.table("tenants").select("*").eq("is_active", True).execute()
    return res.data or []


def upsert_tenant(data: dict) -> dict:
    """Create or update a tenant."""
    res = sb.table("tenants").upsert(data).execute()
    return res.data


# ── Document helpers ──────────────────────────────────────────

def get_documents(tenant_id: str) -> list:
    """Get all documents for a tenant."""
    res = sb.table("documents")\
        .select("*")\
        .eq("tenant_id", tenant_id)\
        .order("created_at", desc=True)\
        .execute()
    return res.data or []


def upsert_document(data: dict) -> dict:
    """Insert or update a document record."""
    res = sb.table("documents").upsert(data).execute()
    return res.data


def toggle_document(doc_id: str, enabled: bool):
    """Enable or disable a document."""
    sb.table("documents")\
        .update({"is_enabled": enabled})\
        .eq("id", doc_id)\
        .execute()


def delete_document(doc_id: str):
    """Delete a document record."""
    sb.table("documents").delete().eq("id", doc_id).execute()


# ── Scraper URL helpers ───────────────────────────────────────

def get_scraper_urls(tenant_id: str, enabled_only: bool = True) -> list:
    """Get scraper URLs for a tenant."""
    q = sb.table("scraper_urls")\
        .select("*")\
        .eq("tenant_id", tenant_id)
    if enabled_only:
        q = q.eq("is_enabled", True)
    return q.order("created_at").execute().data or []


def upsert_scraper_url(data: dict) -> dict:
    """Add or update a scraper URL."""
    res = sb.table("scraper_urls").upsert(data).execute()
    return res.data


def update_scraper_status(url_id: str, status: str,
                          chunk_count: int = 0, error: str = None):
    """Update scrape result for a URL."""
    from datetime import datetime
    sb.table("scraper_urls").update({
        "last_status":  status,
        "last_scraped": datetime.utcnow().isoformat(),
        "chunk_count":  chunk_count,
        "error_msg":    error,
    }).eq("id", url_id).execute()


def delete_scraper_url(url_id: str):
    """Remove a scraper URL."""
    sb.table("scraper_urls").delete().eq("id", url_id).execute()


# ── Cars & rebates helpers ────────────────────────────────────

def get_cars(tenant_id: str) -> list:
    """Get all cars for a tenant."""
    res = sb.table("cars")\
        .select("*")\
        .eq("tenant_id", tenant_id)\
        .order("price_otr")\
        .execute()
    return res.data or []


def upsert_car(data: dict) -> dict:
    res = sb.table("cars").upsert(data).execute()
    return res.data


def get_rebates(tenant_id: str, active_only: bool = True) -> list:
    q = sb.table("rebates")\
        .select("*")\
        .eq("tenant_id", tenant_id)
    if active_only:
        q = q.eq("is_active", True)
    return q.execute().data or []


# ── Chat session helpers ──────────────────────────────────────

def save_chat_session(session: dict):
    """Upsert a chat session to Supabase."""
    sb.table("chat_sessions").upsert({
        "session_key":   session["session_id"],
        "tenant_id":     session.get("tenant_id"),
        "customer_name": session.get("customer_name", ""),
        "car_interest":  session.get("car_interest", ""),
        "last_intent":   session.get("last_intent", ""),
        "messages":      session.get("messages", []),
        "summary":       session.get("summary", ""),
        "msg_count":     len(session.get("messages", [])),
    }, on_conflict="session_key").execute()


def get_chat_sessions(tenant_id: str, limit: int = 50) -> list:
    res = sb.table("chat_sessions")\
        .select("*")\
        .eq("tenant_id", tenant_id)\
        .order("updated_at", desc=True)\
        .limit(limit)\
        .execute()
    return res.data or []


# ── API key helpers ───────────────────────────────────────────

def validate_api_key(key_value: str) -> dict | None:
    """Validate a public API key and return the tenant."""
    res = sb.table("api_keys")\
        .select("*, tenants(*)")\
        .eq("key_value", key_value)\
        .eq("is_active", True)\
        .single()\
        .execute()
    return res.data


def generate_api_key(tenant_id: str, key_type: str = "public") -> str:
    """Generate and store a new API key for a tenant."""
    import secrets
    prefix = "pk" if key_type == "public" else "sk"
    slug   = tenant_id[:4]
    key    = f"{prefix}_{slug}_{secrets.token_urlsafe(16)}"
    sb.table("api_keys").insert({
        "tenant_id": tenant_id,
        "key_type":  key_type,
        "key_value": key,
    }).execute()
    return key