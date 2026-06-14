# Claude Code — Full Codebase Review Prompt
# Paste this into Claude Code to review all recent changes

---

You are reviewing a FastAPI + Supabase chatbot platform called ChatPlatform.
The project is a multi-tenant AI chatbot SaaS deployed on Railway.

## Tech Stack
- **Backend**: Python, FastAPI, Supabase (PostgreSQL), ChromaDB, Anthropic Claude API
- **Frontend**: Vanilla HTML/CSS/JS dashboard pages in `static/dashboard/`
- **Auth**: Supabase Auth with custom `profiles` table (role-based: admin/tenant)
- **Deployment**: Railway (Python), Supabase (DB + Auth + Storage)
- **Widget**: `@chatplatform/widget` npm package (iframe-based embed)

---

## Please review the following recent changes and check for:

### 1. CORE FILES — Check these files exist and are correct

```
core/analytics.py          — analytics tracking module
core/leads.py              — lead capture + email via SMTP
core/engine.py             — AI chat engine (Claude API)
core/supabase_client.py    — Supabase client
```

**For `core/analytics.py` verify:**
- [ ] `track()` function exists and accepts: `event_type`, `tenant_id`, `session_id`, `customer_id`, `data`
- [ ] `get_stats()` function exists and accepts: `tenant_id`, `days`
- [ ] All errors are silently caught (analytics must never break chat)
- [ ] Returns correct structure: `total_sessions`, `total_messages`, `total_leads`, `conversion_rate`, `top_cars`, `daily_chart`

**For `core/leads.py` verify:**
- [ ] `get_sales_recipients()` fetches from Supabase `sales_contacts` table (not hardcoded env var)
- [ ] Falls back to `SALES_EMAIL` env var if table is empty
- [ ] `send_lead_email()` sends to ALL active recipients (not just one)
- [ ] `process_lead_from_message()` calls `track()` from analytics after saving lead

**For `core/engine.py` verify:**
- [ ] Imports `from core.analytics import track` at top
- [ ] Tracks `chat_start` when `session.get("messages")` is empty (new session)
- [ ] Tracks `message_sent` with `{"question": user_msg[:200]}`
- [ ] Tracks `car_queried` when a car brand/model is detected in message
- [ ] These 3 tracking calls do not break existing chat logic

---

### 2. APP.PY — Check all routes exist

**Analytics routes:**
- [ ] `GET /api/analytics/stats?days=30` — returns stats dict
- [ ] `POST /api/analytics/event` — manual event tracking

**Sales contacts routes:**
- [ ] `GET /api/sales-contacts`
- [ ] `POST /api/sales-contacts`
- [ ] `PATCH /api/sales-contacts/{contact_id}`
- [ ] `DELETE /api/sales-contacts/{contact_id}`

**Sync routes:**
- [ ] `POST /api/sync/stock` — authenticated with `X-Sync-Key` header
- [ ] `GET /api/sync/leads` — authenticated with `X-Sync-Key` header
- [ ] `PATCH /api/sync/leads/{lead_id}/notified`
- [ ] `POST /api/sync/generate-key`
- [ ] `GET /api/sync/key/{tenant_id}`

**Admin routes:**
- [ ] `GET /api/admin/accounts`
- [ ] `GET /api/admin/pending-accounts`
- [ ] `PATCH /api/admin/accounts/{profile_id}`

**Tenant-scoped routes:**
- [ ] `GET /api/tenant/{tenant_id}/files`
- [ ] `POST /api/tenant/{tenant_id}/files/upload`
- [ ] `PATCH /api/tenant/{tenant_id}/files/{doc_id}`
- [ ] `DELETE /api/tenant/{tenant_id}/files/{doc_id}`
- [ ] `GET /api/tenant/{tenant_id}/scraper/urls`
- [ ] `POST /api/tenant/{tenant_id}/scraper/urls`
- [ ] `PATCH /api/tenant/{tenant_id}/scraper/urls/{url_id}`
- [ ] `DELETE /api/tenant/{tenant_id}/scraper/urls/{url_id}`
- [ ] `POST /api/tenant/{tenant_id}/scraper/urls/{url_id}/run`
- [ ] `POST /api/tenant/{tenant_id}/scraper/run-all`
- [ ] `GET /api/tenant/{tenant_id}/analytics`
- [ ] `GET /api/tenant/{tenant_id}/leads`
- [ ] `GET /api/tenant/{tenant_id}/sync-key`
- [ ] `POST /api/tenant/{tenant_id}/sync-key/generate`

**Dashboard page routes:**
- [ ] `GET /dashboard/register`
- [ ] `GET /dashboard/tenant`
- [ ] `GET /dashboard/tenant/files`
- [ ] `GET /dashboard/tenant/scraper`
- [ ] `GET /dashboard/tenant/api`
- [ ] `GET /dashboard/accounts`
- [ ] `GET /api/tenants/{tenant_id}` — lookup by UUID OR slug

---

### 3. STATIC FILES — Check these HTML files exist

```
static/dashboard/login.html          — role-based redirect (admin→/dashboard, tenant→/dashboard/tenant)
static/dashboard/register.html       — tenant self-registration with pending approval screen
static/dashboard/auth.js             — role-based guard with data-roles attribute support
static/dashboard/analytics.html      — charts: activity over time, top cars, funnel, daily leads
static/dashboard/leads.html          — sales contacts CRUD with toggle active/inactive
static/dashboard/tenant.html         — tenant overview dashboard
static/dashboard/tenant_files.html   — tenant-scoped file manager
static/dashboard/tenant_scraper.html — tenant-scoped scraper manager
static/dashboard/tenant_api.html     — sync key + webhook + code examples
static/dashboard/accounts.html       — admin: approve/reject pending accounts
static/embed.html                    — transparent background widget
```

---

### 4. SUPABASE TABLES — Check these tables exist

Run in Supabase SQL Editor to verify:
```sql
select table_name from information_schema.tables
where table_schema = 'public'
order by table_name;
```

Expected tables:
- [ ] `analytics_events` — columns: id, tenant_id, event_type, session_id, customer_id, data, created_at
- [ ] `sales_contacts` — columns: id, name, email, phone, role, active, created_at
- [ ] `profiles` — columns: id, email, role, tenant_id, full_name, is_approved, created_at
- [ ] `tenant_sync_keys` — columns: id, tenant_id, sync_key, webhook_url, is_active, last_used_at, created_at
- [ ] `customers` — columns: id, name, phone, interest, source, session_id, notified, created_at
- [ ] `tenants` — existing table
- [ ] `cars` — existing table
- [ ] `documents` — existing table with tenant_id column
- [ ] `scraper_urls` — existing table with tenant_id column

**Check RLS is enabled:**
```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by tablename;
```
All tables should show `rowsecurity = true`.

---

### 5. AUTH FLOW — Check logic is correct

**In `static/dashboard/auth.js` verify:**
- [ ] Loads Supabase JS SDK dynamically
- [ ] Gets session via `sb.auth.getSession()`
- [ ] Fetches `profiles` table for role + is_approved + tenant_id
- [ ] Redirects unapproved users back to login
- [ ] Checks `document.body.dataset.roles` for page access control
- [ ] Admin → `/dashboard`, Tenant → `/dashboard/tenant`
- [ ] Sets `window._profile`, `window.isAdmin()`, `window.isTenant()`, `window.myTenantId()`

**In `static/dashboard/login.html` verify:**
- [ ] Calls `redirectByRole()` after successful login
- [ ] Admin redirects to `/dashboard`
- [ ] Tenant redirects to `/dashboard/tenant`
- [ ] Unapproved accounts show warning and sign out

---

### 6. WIDGET TRANSPARENCY — Check embed.html

**In `static/embed.html` verify:**
- [ ] `<html>` tag has `style="background:transparent;background-color:transparent"`
- [ ] `html` CSS has `background:transparent !important`
- [ ] `body` CSS has single merged rule (no duplicate body rules)
- [ ] `body` has `background:transparent !important` and `background-color:transparent !important`
- [ ] `#chat-window` has `background:transparent`
- [ ] Bot bubbles use `rgba(255,255,255,0.12)` with `backdrop-filter:blur`
- [ ] Input bar uses `rgba(0,0,0,0.2)` background
- [ ] All text colors are white (`#fff` or `rgba(255,255,255,x)`)

---

### 7. NPM WIDGET — Check widget-npm/

**In `widget-npm/index.js` verify:**
- [ ] `iframe.allowTransparency = true` is set BEFORE `iframe.src`
- [ ] `iframe.setAttribute('allowtransparency', 'true')` is present
- [ ] `iframe.setAttribute('frameborder', '0')` is present
- [ ] `background:transparent` and `background-color:transparent` in cssText

**In `widget-npm/package.json` verify:**
- [ ] `"name": "@chatplatform/widget"`
- [ ] `"peerDependencies"` includes `"react": ">=17"`
- [ ] `"files"` includes `index.js`, `index.esm.js`, `README.md`

---

### 8. POTENTIAL ISSUES TO FLAG

Check for and report any of these problems:

**Import errors:**
- [ ] `from core.analytics import track` is present in `engine.py` and `leads.py`
- [ ] No circular imports between core modules

**Duplicate routes:**
- [ ] `/api/tenants/{tenant_id}` — make sure this doesn't conflict with existing `/api/tenants` (list) or `/api/tenants/{slug}` routes
- [ ] `/dashboard/{page}` catch-all doesn't intercept `/dashboard/tenant`, `/dashboard/accounts` etc.

**Missing error handling:**
- [ ] All Supabase calls in sync routes are wrapped in try/except
- [ ] `X-Sync-Key` validation returns 401 (not 500) on failure
- [ ] File upload route handles missing tenant gracefully

**Auth bypass risks:**
- [ ] Tenant-scoped routes `/api/tenant/{tenant_id}/*` — currently no auth check on these routes. Flag if tenant_id in URL doesn't match the logged-in user's tenant_id (any logged-in user could access any tenant's data by guessing UUID)

**ChromaDB tenant isolation:**
- [ ] `ingest_pdf()` and `ingest_text()` use `tenant_slug` (not `tenant_id` UUID) as the collection prefix
- [ ] Tenant-scoped upload route correctly resolves UUID → slug before calling ingest

---

### 9. QUICK FIXES NEEDED

If you find the following, fix them immediately:

1. **Duplicate `body` CSS rules in `embed.html`** — merge into one rule
2. **`iframe.allowTransparency` set after `iframe.src`** — move before src assignment
3. **Missing `from core.analytics import track` in `engine.py`** — add import
4. **`/dashboard/{page}` route catching `/dashboard/tenant`** — add explicit routes before the catch-all
5. **Tenant-scoped API routes missing tenant ownership check** — add profile lookup to verify tenant_id matches

---

### 10. SUMMARY REPORT

After checking everything, provide:

```
✅ WORKING:
- List items that are correctly implemented

⚠️ MISSING:
- List files/routes/tables that don't exist yet

🐛 BUGS FOUND:
- List any bugs or logic errors

🔒 SECURITY ISSUES:
- List any auth/access control problems

📋 TODO BEFORE DEPLOY:
- Ordered list of what needs to be done
```
