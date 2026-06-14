# core/tenant_api.py
# ─────────────────────────────────────────────────────────────
#  Per-tenant external API integration — lets the chatbot pull
#  live car list/detail/price data directly from a tenant's own
#  website API, configured generically per tenant via the
#  "external_api" JSON column on tenant_sync_keys.
# ─────────────────────────────────────────────────────────────

import httpx

# Fields the rest of the app expects on a "car" dict (matches the cars table).
CAR_FIELDS = [
    "car_id", "brand", "model", "variant", "year", "price_otr",
    "stock", "status", "colour", "transmission", "fuel_cons", "engine_cc",
]


def get_external_api_config(tenant_id: str) -> dict | None:
    """Return the tenant's external_api config dict, or None if not configured."""
    from core.supabase_client import sb, maybe_single

    row = maybe_single(
        sb.table("tenant_sync_keys").select("external_api").eq("tenant_id", tenant_id)
    )
    config = row.get("external_api") if row else None
    if not config or not config.get("base_url"):
        return None
    return config


def _apply_field_map(item: dict, field_map: dict) -> dict:
    """Translate a tenant's JSON object into our internal car field names."""
    mapped = {}
    for our_field in CAR_FIELDS:
        source_field = field_map.get(our_field, our_field)
        if source_field in item:
            mapped[our_field] = item[source_field]
    return mapped


def fetch_live_cars(tenant_id: str, car_id: str = None,
                     brand: str = None, model: str = None) -> list[dict] | None:
    """
    Fetch live car list/detail/price from a tenant's configured external API.
    Returns None if no config exists, the request fails, or the response
    can't be parsed — callers should fall back to the cached `cars` table.
    """
    config = get_external_api_config(tenant_id)
    if not config:
        return None

    base_url    = config["base_url"].rstrip("/")
    field_map   = config.get("field_map") or {}
    auth_header = config.get("auth_header")
    auth_value  = config.get("auth_value")

    if car_id and config.get("detail_path"):
        path = config["detail_path"].replace("{car_id}", car_id)
    else:
        path = config.get("list_path", "/")

    url = base_url + path
    headers = {}
    if auth_header and auth_value:
        headers[auth_header] = auth_value

    params = {}
    if brand:
        params["brand"] = brand
    if model:
        params["model"] = model

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=4)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[tenant_api] live fetch failed for tenant {tenant_id}: {e}")
        return None

    # Accept either a bare list or {"cars": [...]} / {"data": [...]}
    if isinstance(data, dict):
        items = data.get("cars") or data.get("data") or [data]
    elif isinstance(data, list):
        items = data
    else:
        return None

    if not isinstance(items, list):
        items = [items]

    return [_apply_field_map(item, field_map) for item in items if isinstance(item, dict)]
