# core/tenant_api.py
# ─────────────────────────────────────────────────────────────
#  Per-tenant external API integration — lets the chatbot pull
#  live data (stock, spec, rebate, news, ...) directly from a
#  tenant's own website API. Each tenant can configure any number
#  of these via the tenant_external_apis table, one row per API.
# ─────────────────────────────────────────────────────────────

import httpx

# api_type -> table the fetched rows get upserted into.
TARGET_TABLE_BY_TYPE = {
    "stock": "cars",
    "spec":  "car_specs",
    "rebate": "rebates",
    "news":  "news_updates",
}


def list_external_apis(tenant_id: str, api_type: str = None, active_only: bool = True) -> list[dict]:
    """Return the tenant's configured external APIs, optionally filtered by type."""
    from core.supabase_client import sb

    q = sb.table("tenant_external_apis").select("*").eq("tenant_id", tenant_id)
    if api_type:
        q = q.eq("api_type", api_type)
    if active_only:
        q = q.eq("is_active", True)
    return q.execute().data or []


def get_external_api(tenant_id: str, api_type: str) -> dict | None:
    """Return the first active config of a given type for a tenant, or None."""
    apis = list_external_apis(tenant_id, api_type=api_type, active_only=True)
    return apis[0] if apis else None


def _apply_field_map(item: dict, field_map: dict) -> dict:
    """Translate a tenant's JSON object into our internal field names."""
    if not field_map:
        return item
    mapped = {}
    for our_field, source_field in field_map.items():
        if source_field in item:
            mapped[our_field] = item[source_field]
    # Keep any fields already using our naming that aren't in the map.
    for k, v in item.items():
        if k not in field_map.values():
            mapped.setdefault(k, v)
    return mapped


def fetch_live_data(api_config: dict, item_id: str = None, **params) -> list[dict] | None:
    """
    Fetch live data from a tenant's configured external API.
    Returns None if the request fails or the response can't be parsed —
    callers should fall back to the cached table.
    """
    base_url    = api_config["base_url"].rstrip("/")
    field_map   = api_config.get("field_map") or {}
    auth_header = api_config.get("auth_header")
    auth_value  = api_config.get("auth_value")

    if item_id and api_config.get("detail_path"):
        path = api_config["detail_path"].replace("{car_id}", item_id).replace("{id}", item_id)
    else:
        path = api_config.get("list_path", "/")

    url = base_url + path
    headers = {}
    if auth_header and auth_value:
        headers[auth_header] = auth_value

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=4)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[tenant_api] live fetch failed for api '{api_config.get('name')}': {e}")
        return None

    # Accept either a bare list or {"cars": [...]} / {"data": [...]}.
    # Check for the key's presence, not truthiness — an empty list is a
    # valid "no rows" answer and must not fall through to [data], which
    # would hand back the response envelope itself as a fake item.
    if isinstance(data, dict):
        for key in ("cars", "data", "items", "results"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return None

    if not isinstance(items, list):
        items = [items]

    return [_apply_field_map(item, field_map) for item in items if isinstance(item, dict)]


def fetch_live_cars(tenant_id: str, car_id: str = None,
                     brand: str = None, model: str = None) -> list[dict] | None:
    """Fetch live car list/detail/price from the tenant's active 'stock' API, if any."""
    config = get_external_api(tenant_id, "stock")
    if not config:
        return None

    params = {}
    if brand:
        params["brand"] = brand
    if model:
        params["model"] = model

    return fetch_live_data(config, item_id=car_id, **params)


# Flat spec field -> customer-facing label, in display order. Tenants
# generally expose one rich row per car, but car_specs (and the engine) are
# key-value, so a flat row is fanned out into one pair per attribute.
# `suffix` is appended to bare numeric values that carry no unit.
SPEC_LABELS = [
    ("engine",           "Enjin",                 ""),
    ("engine_cc",        "Kapasiti enjin",        "cc"),
    ("power",            "Kuasa",                 ""),
    ("power_hp",         "Kuasa",                 " hp"),
    ("torque",           "Tork",                  ""),
    ("torque_nm",        "Tork",                  " Nm"),
    ("transmission",     "Transmisi",             ""),
    ("fuel_type",        "Jenis bahan api",       ""),
    ("fuel_cons_raw",    "Penggunaan bahan api",  ""),
    ("fuel_cons",        "Penggunaan bahan api",  " km/L"),
    ("seating_capacity", "Tempat duduk",          " orang"),
    ("boot_space",       "Ruang bagasi",          " L"),
    ("features",         "Ciri-ciri",             ""),
]

# Identity/join fields — never rendered as a spec attribute.
_SPEC_SKIP = {"car_id", "brand", "model", "variant", "year", "tenant_id",
              "status", "price_otr", "stock", "colour", "updated_at"}


_MAX_SPEC_LEN = 220


def _clean_spec_value(value) -> str:
    """
    Flatten a spec value for the prompt. Feed values are often HTML-derived
    free text — entities, embedded newlines, a whole features list — and go
    straight into the system prompt, so they're unescaped, collapsed onto
    one line and capped.
    """
    import html
    import re

    # Feeds are sometimes double-escaped ("&amp;amp;"), so unescape until it
    # settles rather than assuming a single pass is enough.
    text = str(value)
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded

    text = re.sub(r"\s*[\r\n]+\s*", ", ", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,/")
    if len(text) > _MAX_SPEC_LEN:
        text = text[:_MAX_SPEC_LEN].rsplit(", ", 1)[0].rstrip(" ,") + ", …"
    return text


def _pivot_spec_row(item: dict) -> list[dict]:
    """
    Fan a flat spec row out into car_specs-shaped {car_id, spec_key,
    spec_value} pairs. Rows already in key-value shape pass through
    untouched, so a tenant may emit either form.
    """
    if "spec_key" in item:
        return [item]

    car_id = item.get("car_id")
    if not car_id:
        return []

    seen = set()
    pairs = []
    for field, label, suffix in SPEC_LABELS:
        if label in seen or field not in item:
            continue
        value = item[field]
        if value is None or value == "":
            continue
        text = _clean_spec_value(value)
        # Only add a unit when the source value doesn't already carry one.
        if suffix and not any(ch.isalpha() for ch in text):
            text += suffix
        pairs.append({"car_id": car_id, "spec_key": label, "spec_value": text})
        seen.add(label)

    # Anything the tenant sends that isn't in SPEC_LABELS is still shown,
    # under a humanised version of its own field name.
    for field, value in item.items():
        if field in _SPEC_SKIP or value is None or value == "":
            continue
        if any(field == f for f, _, _ in SPEC_LABELS):
            continue
        label = field.replace("_", " ").capitalize()
        if label in seen:
            continue
        pairs.append({"car_id": car_id, "spec_key": label,
                      "spec_value": _clean_spec_value(value)})
        seen.add(label)

    return pairs


def fetch_live_specs(tenant_id: str, car_id: str = None) -> list[dict] | None:
    """
    Fetch live car specs from the tenant's active 'spec' API, if any.
    Returns car_specs-shaped rows regardless of whether the tenant emits
    flat rows or key-value pairs. Returns None when nothing usable came
    back, so callers fall back to the cached car_specs table.
    """
    config = get_external_api(tenant_id, "spec")
    if not config:
        return None

    items = fetch_live_data(config, item_id=car_id)
    if not items:
        return None

    pairs = [p for item in items for p in _pivot_spec_row(item)]
    return pairs or None


def fetch_live_rebates(tenant_id: str, car_id: str = None) -> list[dict] | None:
    """Fetch live rebates/discounts from the tenant's active 'rebate' API, if any."""
    config = get_external_api(tenant_id, "rebate")
    if not config:
        return None
    return fetch_live_data(config, item_id=car_id)


def fetch_live_news(tenant_id: str) -> list[dict] | None:
    """Fetch live news/updates from the tenant's active 'news' API, if any."""
    config = get_external_api(tenant_id, "news")
    if not config:
        return None
    return fetch_live_data(config)
