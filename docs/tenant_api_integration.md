# Tenant API Integration Guide

This guide is for a tenant's developer (e.g. laman_auto) integrating their
website with the ChatPlatform chatbot. It covers:

1. Authentication (sync key)
2. Leads — pull, mark-as-notified, webhook push
3. Car inventory — bulk push (cached data)
4. Car inventory — live pull (real-time price/stock)
5. How `field_map` makes this work for any tenant

> This file is written as a generic template — replace example values with
> your own tenant's data. The mechanism is identical for every tenant; only
> the configuration (sync key, base URL, field names) differs.

---

## 1. Authentication — Sync Key

All `/api/sync/*` endpoints are authenticated with an `X-Sync-Key` header.

- Get/regenerate your key from the dashboard: **API Manager**
  (`/dashboard/tenant/api`) → **Sync Key** card → **Regenerate key**.
- This calls `POST /api/tenant/{tenant_id}/sync-key/generate` and returns a
  new key of the form `sk_sync_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
- Treat this key like a password — regenerating it invalidates the old one
  immediately.

Every request below must include:

```
X-Sync-Key: sk_sync_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json
```

---

## 2. Leads

### 2.1 Pull new leads

```
GET /api/sync/leads
X-Sync-Key: sk_sync_...
```

Response:

```json
{
  "leads": [
    {
      "id": "uuid",
      "name": "Ahmad",
      "phone": "+60123456789",
      "interest": "Perodua Myvi",
      "source": "chatbot",
      "session_id": "...",
      "notified": false,
      "tenant_id": "...",
      "created_at": "2026-06-10T08:00:00Z"
    }
  ],
  "count": 1
}
```

Poll this endpoint periodically (e.g. every 1-5 minutes) to pick up new
leads captured by the chatbot.

### 2.2 Mark a lead as notified

After you've processed a lead (e.g. imported it into your CRM), mark it so
it doesn't show up again:

```
PATCH /api/sync/leads/{lead_id}/notified
X-Sync-Key: sk_sync_...
```

Response: `{"status": "ok"}`

### 2.3 Webhook push (real-time, optional)

Instead of polling, you can configure a **Webhook URL** in the **Lead
Webhook** card on the API Manager page. As soon as the chatbot captures a
lead, ChatPlatform will `POST` it to your URL with the same `X-Sync-Key`
header for verification:

```
POST <your webhook_url>
X-Sync-Key: sk_sync_...
Content-Type: application/json

{ ...lead object... }
```

Your endpoint should respond `2xx` quickly; failures are logged but not
retried.

---

## 3. Car Inventory — Bulk Push (cached data)

Push your full (or incremental) inventory to ChatPlatform. This populates
the `cars` table that the chatbot uses by default for price/stock answers.

```
POST /api/sync/stock
X-Sync-Key: sk_sync_...
Content-Type: application/json

{
  "cars": [
    {
      "car_id":       "PROTON-SAGA-2024",
      "brand":        "Proton",
      "model":        "Saga",
      "variant":      "Premium CVT",
      "year":         2024,
      "price_otr":    48800,
      "stock":        7,
      "status":       "available",
      "colour":       "Silver",
      "transmission": "CVT",
      "fuel_cons":    16.9,
      "engine_cc":    1332
    }
  ]
}
```

Response: `{"status": "ok", "synced": 1}`

This is an **upsert** keyed on `car_id` — send the same `car_id` again to
update price/stock, or to add new models. Run this on a schedule (e.g.
hourly/nightly) to keep the cache fresh.

| Field         | Type    | Notes                                   |
|---------------|---------|------------------------------------------|
| `car_id`      | string  | Your unique SKU/ID — used as the key    |
| `brand`       | string  | e.g. "Proton"                           |
| `model`       | string  | e.g. "Saga"                             |
| `variant`     | string  | e.g. "Premium CVT"                      |
| `year`        | number  |                                          |
| `price_otr`   | number  | On-the-road price (RM)                  |
| `stock`       | number  | Units available                         |
| `status`      | string  | `"available"` to show in chat           |
| `colour`      | string  |                                          |
| `transmission`| string  | e.g. "CVT", "Manual"                    |
| `fuel_cons`   | number  | km/l                                     |
| `engine_cc`   | number  |                                          |

---

## 4. Car Inventory — Live Pull (real-time price/stock)

If your website already has its own API for cars, you can let the chatbot
call it **live** at chat time for price/stock questions — instead of (or in
addition to) the bulk push above. This is configured in the **External Car
API (live price & stock)** card on the API Manager page.

### 4.1 What your API needs to provide

- A **list endpoint** that returns all (or available) cars, e.g. `GET /cars`
- Optionally, a **detail endpoint** for one car by ID, e.g. `GET /cars/{car_id}`
- Optional auth via a single header (e.g. `X-API-Key: <secret>`)

The response can be either a bare JSON array, or an object containing the
array under `"cars"` or `"data"`:

```json
[
  { "sku": "PROTON-SAGA-2024", "make": "Proton", "model": "Saga", "price": 48800, "qty": 7 }
]
```

or

```json
{ "cars": [ { "sku": "...", "make": "...", "price": 48800, "qty": 7 } ] }
```

### 4.2 Configure it in the dashboard

Open **API Manager → External Car API** and fill in:

| Field              | Example                          | Notes                                    |
|--------------------|-----------------------------------|--------------------------------------------|
| Base URL           | `https://laman-auto.com.my/api`   | No trailing slash needed                  |
| List path          | `/cars`                           | Appended to base URL                      |
| Detail path        | `/cars/{car_id}`                  | `{car_id}` is replaced at request time    |
| Auth header name   | `X-API-Key`                       | Leave blank if no auth needed             |
| Auth header value  | `your-secret-token`               | Stored encrypted; shown masked afterwards |
| Field mapping (JSON) | see below                        | Maps your field names → ours              |

Click **Save**, then **Test connection** to confirm ChatPlatform can reach
and parse your API.

### 4.3 Field mapping

`field_map` is a JSON object mapping **our** field name → **your** field
name. Only fields you include are pulled; anything not listed (or not
present in your response) is simply ignored — the chatbot falls back to the
cached value from the bulk push for that field.

```json
{
  "car_id":    "sku",
  "brand":     "make",
  "model":     "model",
  "price_otr": "price",
  "stock":     "qty"
}
```

With this mapping, a response item like
`{"sku": "PROTON-SAGA-2024", "make": "Proton", "model": "Saga", "price": 47500, "qty": 3}`
is translated internally to
`{"car_id": "PROTON-SAGA-2024", "brand": "Proton", "model": "Saga", "price_otr": 47500, "stock": 3}`,
which the chatbot merges onto the matching cached car (by `car_id`) before
answering — so customers always get your latest price/stock.

If your API already uses our field names (`car_id`, `brand`, `model`,
`variant`, `year`, `price_otr`, `stock`, `status`, `colour`, `transmission`,
`fuel_cons`, `engine_cc`), you can leave `field_map` empty.

### 4.4 Behaviour notes

- Live pull is **best-effort**: if your API is slow, unreachable, or returns
  an error, the chatbot silently falls back to the cached `cars` table data
  (from section 3) — chat never breaks because of this.
- Live pull is only triggered when the customer asks about a specific
  brand/model that already exists in the cached `cars` table (via the bulk
  push). It enriches that row with live price/stock — it does not add new
  cars to the catalog. To add new models, use the bulk push (section 3).
- Requests have a 4-second timeout.

---

## 5. Adding a new tenant (for ChatPlatform operators)

This entire integration is generic — no backend code changes are needed for
a new tenant:

1. Generate a sync key for the new tenant from API Manager.
2. New tenant's developer implements the same `/api/sync/*` calls above
   using their own sync key.
3. If they want live price/stock, they fill in the External Car API card
   with their own `base_url` + `field_map` matching their API's JSON shape.

All configuration lives in the `tenant_sync_keys` table (`sync_key`,
`webhook_url`, `external_api` columns), scoped per `tenant_id`.

---

## 6. Row shapes per `api_type`

An external API row (`tenant_external_apis`) has an `api_type`. Each type is
consumed differently by the chatbot and expects a **different JSON row
shape** — they are not interchangeable. Pointing all types at the same
endpoint does not work: the rows are matched against different tables.

`field_map` translates your field names to ours, so the names below are the
*target* names, not necessarily what your API must literally emit.

### 6.1 `stock` → `cars` table

Answers: *"Ada stock Myvi tak?"*, *"Berapa harga Saga?"*

Row shape (same as the bulk push, section 3):

```json
{
  "car_id": "PROTON-SAGA-2024-PREMIUM", "brand": "Proton", "model": "Saga",
  "variant": "Premium CVT", "year": 2024, "price_otr": 48800, "stock": 7,
  "status": "available", "colour": "Silver", "transmission": "CVT",
  "fuel_cons": 16.9, "engine_cc": 1332
}
```

`car_id` is **required** — it is the join key. Live rows are merged onto
cached `cars` rows by `car_id`; a live row whose `car_id` is not already in
`cars` is ignored. Live pull enriches, it never inserts.

### 6.2 `spec` → `car_specs` table

Answers: *"Apa spec Myvi 1.6?"*

`car_specs` is **key–value (EAV)**, not one row per car. Primary key is
`(tenant_id, car_id, spec_key)` — so emit **one row per spec attribute**:

```json
[
  {"car_id": "PERODUA-MYVI-2024-16AV", "spec_key": "Enjin",     "spec_value": "1.6L VVT-i"},
  {"car_id": "PERODUA-MYVI-2024-16AV", "spec_key": "Kuasa",     "spec_value": "103 hp"},
  {"car_id": "PERODUA-MYVI-2024-16AV", "spec_key": "Tork",      "spec_value": "137 Nm"},
  {"car_id": "PERODUA-MYVI-2024-16AV", "spec_key": "Gearbox",   "spec_value": "4-speed AT"},
  {"car_id": "PERODUA-MYVI-2024-16AV", "spec_key": "Keselamatan","spec_value": "6 airbags, ASA 3.0"}
]
```

| Field        | Type   | Notes                                        |
|--------------|--------|-----------------------------------------------|
| `car_id`     | string | Must match a `cars.car_id`                    |
| `spec_key`   | string | Attribute label, shown to the customer as-is  |
| `spec_value` | string | Free text — units included                    |

Rows without a `spec_key` are silently dropped. `spec_key`/`spec_value` are
rendered verbatim into the prompt, so write them in the language the
customer is served in.

Only fetched when the message contains a spec keyword
(`spec`, `spesifikasi`, `horsepower`, `torque`, `dimension`, `kuasa`).

### 6.3 `rebate` → `rebates` table

Answers: *"Ada rebate tak?"*

```json
{
  "car_id": "PROTON-SAGA-2024-PREMIUM", "amount": 2000,
  "rebate_type": "Trade-in", "description": "Bonus tukar beli",
  "valid_from": "2026-08-01T00:00:00Z", "valid_until": "2026-09-30T00:00:00Z",
  "is_active": true
}
```

| Field         | Type    | Notes                                      |
|---------------|---------|---------------------------------------------|
| `car_id`      | string  | FK to `cars.car_id`                         |
| `amount`      | number  | Required (RM). Summed across rebates        |
| `rebate_type` | string  | Shown grouped, e.g. "Trade-in, Loyalty"     |
| `is_active`   | boolean | Only `true` rows are used                   |

> **Not wired for live pull yet.** `fetch_live_rebates()` exists in
> `core/tenant_api.py` but has no call site — the engine reads the `rebates`
> table directly. Configuring a `rebate` external API today has no effect;
> keep rebates fresh via the bulk push / direct table writes.

### 6.4 `news` → `news_updates` table

Answers: *"Ada berita terkini tak?"*

```json
{"title": "Promosi Merdeka 2026", "body": "Rebat sehingga RM3,000",
 "source_url": "https://...", "published_at": "2026-08-01T00:00:00Z"}
```

`title` is required; rows without it are skipped. Top 5 by `published_at`.
Only fetched on a news keyword (`berita`, `news`, `terkini`, `update`,
`pengumuman`, `announcement`).

### 6.5 The cached tables are the source of truth

Live pull is an **overlay**, not a replacement:

- The engine queries `cars` **first**. If it returns nothing for the tenant,
  it returns an empty context and **no live API is called at all**.
- `stock` and `spec` live rows are joined onto that result by `car_id`.
- So the bulk push (section 3) must keep `cars` populated regardless of
  whether live pull is configured. Live pull only refreshes values on cars
  that already exist.
