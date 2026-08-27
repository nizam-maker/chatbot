# core/sync.py
# ─────────────────────────────────────────────────────────────
#  Pull-and-persist for tenant external APIs.
#
#  core/tenant_api.py fetches live data per chat message and throws it
#  away. This module does the other half: fetch on demand and upsert into
#  the tenant's cached tables (the `target_table` on each config row), so
#  the chatbot answers from fresh data even when the live call is skipped
#  — which is most of the time, since live pull only fires for specific
#  brand/model questions.
# ─────────────────────────────────────────────────────────────

from datetime import datetime, timezone

from core.tenant_api import list_external_apis, fetch_live_data, _pivot_spec_row

# Columns we're allowed to write per target table. Anything a tenant sends
# that isn't listed is dropped rather than failing the whole upsert.
WRITABLE_COLUMNS = {
    "cars": {
        "car_id", "tenant_id", "brand", "model", "variant", "year",
        "body_type", "segment", "price_otr", "price_basic", "sst_exempt",
        "engine_cc", "transmission", "fuel_type", "power_hp", "torque_nm",
        "fuel_cons", "stock", "colour", "condition", "status", "spec_pdf_url",
    },
    "car_specs":    {"car_id", "tenant_id", "spec_key", "spec_value", "updated_at"},
    "rebates":      {"id", "tenant_id", "car_id", "amount", "rebate_type",
                     "description", "valid_from", "valid_until", "is_active",
                     "rebate_id", "rebate_name", "rebate_display", "rebate_value",
                     "freebie_value", "price_after_rebate", "requires_code",
                     "new_customer_only", "stackable"},
    "news_updates": {"id", "tenant_id", "title", "body", "source_url",
                     "published_at", "updated_at"},
}

# Conflict target used for upserts, per table.
CONFLICT_KEY = {
    "cars":         "car_id",
    "car_specs":    "tenant_id,car_id,spec_key",
    "news_updates": "id",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _clean(rows: list[dict], table: str, tenant_id: str) -> list[dict]:
    """Scope rows to the tenant and drop unknown columns."""
    allowed = WRITABLE_COLUMNS[table]
    out = []
    for r in rows:
        row = {k: v for k, v in r.items() if k in allowed}
        row["tenant_id"] = tenant_id
        if "updated_at" in allowed:
            row["updated_at"] = _now()
        out.append(row)
    return out


def _normalise_rebate(item: dict) -> dict | None:
    """
    Map a rebate feed row onto the `rebates` table.

    Tenants describe a rebate with `rebate_amount` (cash off OTR) while our
    column is `amount`. Freebies are the awkward case: they carry
    `rebate_amount: 0` and put the gift's worth in `freebie_value`, so a
    truthiness check on the amount would silently drop every freebie. Only
    rows with no car and no usable value at all are discarded.
    """
    if not item.get("car_id"):
        return None

    row = dict(item)

    if "amount" not in row:
        row["amount"] = row.get("rebate_amount", 0) or 0

    # A freebie is worth mentioning even though it takes nothing off the price.
    if not row["amount"] and not row.get("freebie_value") \
            and row.get("rebate_type") != "freebie":
        return None

    row.setdefault("is_active", True)
    # `description` is what the customer hears; prefer the tenant's own wording.
    if not row.get("description"):
        row["description"] = row.get("rebate_name") or row.get("rebate_display")

    return row


def sync_api(api_config: dict, deactivate_missing: bool = True) -> dict:
    """
    Fetch one external API and persist it into its target table.
    Returns a per-API result dict; never raises.
    """
    from core.supabase_client import sb

    tenant_id = api_config["tenant_id"]
    api_type  = api_config["api_type"]
    table     = api_config["target_table"]
    name      = api_config.get("name") or api_type

    result = {"api": name, "api_type": api_type, "table": table,
              "fetched": 0, "written": 0, "deactivated": 0, "status": "ok"}

    items = fetch_live_data(api_config)
    if items is None:
        result["status"] = "fetch_failed"
        return result
    result["fetched"] = len(items)

    try:
        if api_type == "spec":
            # Flat rows fan out into one row per attribute.
            pairs = [p for item in items for p in _pivot_spec_row(item)]
            rows  = _clean(pairs, "car_specs", tenant_id)
            if rows:
                sb.table("car_specs").upsert(
                    rows, on_conflict=CONFLICT_KEY["car_specs"]).execute()
            result["written"] = len(rows)

        elif api_type == "stock":
            rows = [r for r in _clean(items, "cars", tenant_id) if r.get("car_id")]
            if rows:
                sb.table("cars").upsert(
                    rows, on_conflict=CONFLICT_KEY["cars"]).execute()
            result["written"] = len(rows)

            # Reconcile: a car the feed no longer lists is not sellable.
            # Marked unavailable rather than deleted, so nothing is lost and
            # a later feed can bring it back.
            if deactivate_missing and rows:
                feed_ids = {r["car_id"] for r in rows}
                existing = sb.table("cars").select("car_id,status") \
                    .eq("tenant_id", tenant_id).eq("status", "available") \
                    .execute().data or []
                stale = [c["car_id"] for c in existing if c["car_id"] not in feed_ids]
                for i in range(0, len(stale), 50):
                    sb.table("cars").update({"status": "unavailable"}) \
                      .eq("tenant_id", tenant_id) \
                      .in_("car_id", stale[i:i + 50]).execute()
                result["deactivated"] = len(stale)

        elif api_type == "rebate":
            # No natural key, so this is a replace. An empty feed is
            # ambiguous — "no promotions" or "endpoint not ready yet" — and
            # wiping manually-entered rebates on the second reading is not
            # recoverable, so an empty feed is treated as a no-op.
            if not items:
                result["status"] = "skipped_empty_feed"
                return result
            rows = [r for r in (_normalise_rebate(i) for i in items) if r]
            rows = _clean(rows, "rebates", tenant_id)
            sb.table("rebates").delete().eq("tenant_id", tenant_id).execute()
            if rows:
                sb.table("rebates").insert(rows).execute()
            result["written"] = len(rows)

        elif api_type == "news":
            rows = [r for r in _clean(items, "news_updates", tenant_id) if r.get("title")]
            if rows:
                sb.table("news_updates").upsert(
                    rows, on_conflict=CONFLICT_KEY["news_updates"]).execute()
            result["written"] = len(rows)

        else:
            result["status"] = f"unsupported api_type '{api_type}'"

    except Exception as e:
        result["status"] = f"write_failed: {e}"

    return result


def sync_tenant(tenant_id: str, api_type: str = None,
                deactivate_missing: bool = True) -> dict:
    """Run every active external API for a tenant (optionally one type)."""
    apis = list_external_apis(tenant_id, api_type=api_type, active_only=True)

    # Stock first: specs and rebates reference cars.car_id.
    order = {"stock": 0, "spec": 1, "rebate": 2, "news": 3}
    apis.sort(key=lambda a: order.get(a["api_type"], 9))

    results = [sync_api(a, deactivate_missing=deactivate_missing) for a in apis]
    return {
        "tenant_id": tenant_id,
        "synced_at": _now(),
        "results":   results,
        "ok":        all(r["status"] in ("ok", "skipped_empty_feed") for r in results),
    }
