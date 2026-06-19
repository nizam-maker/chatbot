# app.py
# ─────────────────────────────────────────────────────────────
#  FastAPI entry point
#  Run with: uvicorn app:app --reload
# ─────────────────────────────────────────────────────────────

import os
import uuid
import importlib
import shutil
import secrets as _secrets

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from core.engine import chat
from core.ingest import ingest_pdf, ingest_text
from core.memory import load_session
from core.scheduler import start_scheduler, stop_scheduler, get_status
from core.auth import require_tenant_access, require_admin

load_dotenv()

# ── Configure OCR paths ───────────────────────────────────────
import platform
if platform.system() == "Linux":
    # Railway runs on Linux — tesseract installed via apt
    os.environ.setdefault("TESSERACT_PATH", "/usr/bin/tesseract")
    os.environ.setdefault("POPPLER_PATH",   "/usr/bin")

# ── Auto-run DB init + seed on startup ───────────────────────
try:
    from tenants.laman_auto.schema import init_db, SessionLocal
    from tenants.laman_auto.seed import seed_cars, seed_rebates, seed_customers
    init_db()
    with SessionLocal() as s:
        seed_cars(s)
        seed_rebates(s)
        seed_customers(s)
        s.commit()
    print("[startup] DB ready ✓")
except Exception as e:
    print(f"[startup] DB seed skipped: {e}")

# ── Auto-ingest PDFs from knowledge/ folder on startup ────────
try:
    import glob
    knowledge_base = glob.glob("knowledge/**/*.pdf", recursive=True)
    for pdf_path in knowledge_base:
        parts = pdf_path.replace("\\", "/").split("/")
        if len(parts) >= 3:
            tenant = parts[1]
            domain = parts[2]
            ingest_pdf(pdf_path, tenant_id=tenant, domain=domain,
                       meta={"auto_ingested": True})
    if knowledge_base:
        print(f"[startup] Auto-ingested {len(knowledge_base)} PDFs ✓")
except Exception as e:
    print(f"[startup] PDF ingest skipped: {e}")

# ── Load tenant config dynamically from .env ─────────────────
TENANT = os.getenv("TENANT", "laman_auto")

try:
    tenant_module = importlib.import_module(f"tenants.{TENANT}.config")
    tenant_cfg = {k: getattr(tenant_module, k) for k in dir(tenant_module)
                  if not k.startswith("_")}
    print(f"[app] Tenant loaded: {TENANT}")
except ModuleNotFoundError:
    raise RuntimeError(f"Tenant '{TENANT}' not found in tenants/ folder.")

# ── FastAPI app with lifespan ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title=tenant_cfg.get("BOT_NAME", "Chatbot"), lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Chat UI ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")


@app.get("/chat", response_class=HTMLResponse)
async def chat_ui():
    html_path = "static/chat.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read(),
                                media_type="text/html; charset=utf-8")
    return HTMLResponse("<h2>Chat UI not found</h2>")


# ── Dashboard pages ───────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_home():
    html_path = "static/dashboard/index.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read(),
                                media_type="text/html; charset=utf-8")
    return HTMLResponse("<h2>Dashboard index.html not found</h2>", status_code=404)


# ── Chat API ──────────────────────────────────────────────────

@app.get("/api/config")
async def api_config():
    return {
        "bot_name":       tenant_cfg.get("BOT_NAME"),
        "welcome_msg":    tenant_cfg.get("WELCOME_MSG"),
        "quick_replies":  tenant_cfg.get("QUICK_REPLIES", []),
        "brand_color":    tenant_cfg.get("BRAND_COLOR", "#333"),
        "brand_initials": tenant_cfg.get("BRAND_INITIALS", "AI"),
        "tenant_id":      TENANT,
        "domains":        tenant_cfg.get("DOMAINS", []),
    }


@app.post("/api/chat")
async def api_chat(req: Request):
    body        = await req.json()
    user_msg    = body.get("message", "").strip()
    session_id  = body.get("session_id") or str(uuid.uuid4())
    customer_id = body.get("customer_id", "guest")
    if not user_msg:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    result = chat(user_msg=user_msg, session_id=session_id,
                  tenant_cfg=tenant_cfg, customer_id=customer_id)
    return result


@app.get("/api/session/{session_id}")
async def api_session(session_id: str):
    return load_session(session_id)


# ── Debug chat (for tester) ───────────────────────────────────

@app.post("/api/chat/debug")
async def api_chat_debug(req: Request):
    body        = await req.json()
    user_msg    = body.get("message", "").strip()
    session_id  = body.get("session_id") or str(uuid.uuid4())
    customer_id = body.get("customer_id", "tester")
    if not user_msg:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    from core.ingest import retrieve
    chunks_raw = retrieve(user_msg, TENANT, tenant_cfg.get("DOMAINS", []), n=4)
    result  = chat(user_msg=user_msg, session_id=session_id,
                   tenant_cfg=tenant_cfg, customer_id=customer_id)
    session = load_session(session_id)
    return {
        **result,
        "chunks": [{"text": c[:300], "score": round(0.95 - i*0.06, 2)}
                   for i, c in enumerate(chunks_raw)],
        "session": {
            "customer_name": session.get("customer_name", ""),
            "car_interest":  session.get("car_interest", ""),
            "last_intent":   session.get("last_intent", ""),
            "msg_count":     len(session.get("messages", [])),
        }
    }


# ── Ingest API ────────────────────────────────────────────────

@app.post("/api/ingest/pdf")
async def api_ingest_pdf(
    file:   UploadFile = File(...),
    domain: str        = Form("car_specs"),
    brand:  str        = Form(""),
    model:  str        = Form(""),
):
    domains = tenant_cfg.get("DOMAINS", [])
    if domain not in domains:
        return JSONResponse({"error": f"Unknown domain: {domain}"}, status_code=400)
    dest = f"uploads/{file.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    count = ingest_pdf(pdf_path=dest, tenant_id=TENANT, domain=domain,
                       meta={"brand": brand, "model": model})
    return {"status": "ok", "file": file.filename, "domain": domain, "chunks": count}


@app.post("/api/ingest/text")
async def api_ingest_text(req: Request):
    body   = await req.json()
    text   = body.get("text", "").strip()
    domain = body.get("domain", "faq_support")
    doc_id = body.get("doc_id") or str(uuid.uuid4())
    domains = tenant_cfg.get("DOMAINS", [])
    if domain not in domains:
        return JSONResponse({"error": "Unknown domain."}, status_code=400)
    count = ingest_text(text=text, doc_id=doc_id, tenant_id=TENANT, domain=domain)
    return {"status": "ok", "doc_id": doc_id, "domain": domain, "chunks": count}


# ── Health & ETL ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "tenant": TENANT,
            "domains": tenant_cfg.get("DOMAINS", [])}


@app.get("/api/public-config")
async def public_config():
    """Public config for frontend Supabase client — safe to expose."""
    return {
        "supabase_url":      os.getenv("SUPABASE_URL"),
        "supabase_anon_key": os.getenv("SUPABASE_ANON_KEY"),
    }


@app.get("/api/etl/status")
async def etl_status():
    return get_status()


@app.post("/api/scrape")
async def api_scrape():
    import threading
    from core.scraper import scrape_brand_pages
    threading.Thread(target=scrape_brand_pages, args=(TENANT,), daemon=True).start()
    return {"status": "started", "message": "Brand scraper running in background"}


@app.post("/api/news")
async def api_news():
    import threading
    from core.rss_feed import fetch_news
    threading.Thread(target=fetch_news, args=(TENANT,), daemon=True).start()
    return {"status": "started", "message": "RSS news fetch running in background"}


# ── Dashboard stats API ───────────────────────────────────────

@app.get("/api/dashboard/stats")
async def dashboard_stats():
    from core.supabase_client import sb
    try:
        cars     = len(sb.table("cars").select("car_id").execute().data or [])
        docs     = len(sb.table("documents").select("id").eq("is_enabled", True).execute().data or [])
        urls     = len(sb.table("scraper_urls").select("id").execute().data or [])
        rebates  = len(sb.table("rebates").select("id").eq("is_active", True).execute().data or [])
        sessions = len(sb.table("chat_sessions").select("id").execute().data or [])
        return {"cars": cars, "docs": docs, "urls": urls,
                "rebates": rebates, "sessions": sessions}
    except Exception:
        return {"cars": 0, "docs": 0, "urls": 0, "rebates": 0, "sessions": 0}


@app.get("/api/dashboard/activity")
async def dashboard_activity():
    from core.supabase_client import sb
    try:
        res = sb.table("scraper_urls").select("*")\
            .order("last_scraped", desc=True).limit(10).execute()
        return res.data or []
    except Exception:
        return []


# ── Scraper URL CRUD ──────────────────────────────────────────

@app.get("/api/scraper/urls")
async def get_scraper_urls():
    from core.supabase_client import sb
    res = sb.table("scraper_urls").select("*").order("created_at").execute()
    return res.data or []


@app.post("/api/scraper/urls")
async def add_scraper_url(req: Request):
    from core.supabase_client import sb, get_tenant
    body   = await req.json()
    tenant = get_tenant(TENANT)
    if not tenant:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    data = {
        "tenant_id":    tenant["id"],
        "url":          body.get("url", "").strip(),
        "brand":        body.get("brand", ""),
        "model":        body.get("model", ""),
        "domain":       body.get("domain", "car_specs"),
        "css_selector": body.get("css_selector", "main"),
        "is_enabled":   True,
        "last_status":  "pending",
    }
    res = sb.table("scraper_urls").insert(data).execute()
    return res.data[0] if res.data else JSONResponse({"error": "Insert failed"}, status_code=500)


@app.patch("/api/scraper/urls/{url_id}")
async def update_scraper_url(url_id: str, req: Request):
    from core.supabase_client import sb
    body    = await req.json()
    allowed = ["is_enabled", "url", "brand", "model", "domain", "css_selector"]
    update  = {k: v for k, v in body.items() if k in allowed}
    sb.table("scraper_urls").update(update).eq("id", url_id).execute()
    return {"status": "ok"}


@app.delete("/api/scraper/urls/{url_id}")
async def delete_scraper_url(url_id: str):
    from core.supabase_client import sb
    sb.table("scraper_urls").delete().eq("id", url_id).execute()
    return {"status": "ok"}


@app.post("/api/scraper/urls/{url_id}/run")
async def run_single_url(url_id: str):
    import threading
    from core.supabase_client import sb, maybe_single, update_scraper_status
    from core.scraper import _fetch_page, _extract_text
    row = maybe_single(sb.table("scraper_urls").select("*").eq("id", url_id))
    if not row:
        return JSONResponse({"error": "URL not found"}, status_code=404)
    def run():
        url = row["url"]
        if not url.startswith("http"):
            url = "https://" + url
        html = _fetch_page(url)
        if not html:
            update_scraper_status(url_id, "fail", error="fetch failed")
            return
        text = _extract_text(html, row.get("css_selector", "main"))
        if len(text) < 100:
            update_scraper_status(url_id, "fail", error=f"only {len(text)} chars")
            return
        doc_id = f"web_{row.get('brand','').lower()}_{row.get('model','').lower()}"
        chunks = ingest_text(text=text, doc_id=doc_id, tenant_id=TENANT,
                             domain=row.get("domain", "car_specs"),
                             meta={"brand": row.get("brand"), "source": url})
        update_scraper_status(url_id, "ok", chunk_count=chunks)
    threading.Thread(target=run, daemon=True).start()
    return {"status": "started", "url_id": url_id}


# ── File manager API ──────────────────────────────────────────

@app.get("/api/files")
async def get_files():
    from core.supabase_client import sb, get_tenant
    tenant = get_tenant(TENANT)
    if not tenant:
        return []
    res = sb.table("documents").select("*")\
        .eq("tenant_id", tenant["id"]).order("created_at", desc=True).execute()
    return res.data or []


@app.post("/api/files/upload")
async def upload_file(
    file:   UploadFile = File(...),
    domain: str        = Form("car_specs"),
    brand:  str        = Form(""),
    model:  str        = Form(""),
):
    from core.supabase_client import sb, get_tenant
    import uuid as uuid_mod
    tenant = get_tenant(TENANT)
    if not tenant:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    domains = tenant_cfg.get("DOMAINS", [])
    if domain not in domains:
        return JSONResponse({"error": f"Unknown domain: {domain}"}, status_code=400)
    file_bytes   = await file.read()
    dest         = f"uploads/{file.filename}"
    with open(dest, "wb") as f:
        f.write(file_bytes)
    storage_path = f"{TENANT}/{domain}/{file.filename}"
    try:
        sb.storage.from_("documents").upload(
            storage_path, file_bytes,
            {"content-type": file.content_type or "application/pdf"})
    except Exception as e:
        print(f"[files] Storage upload warning: {e}")
    count  = ingest_pdf(pdf_path=dest, tenant_id=TENANT, domain=domain,
                        meta={"brand": brand, "model": model, "file_name": file.filename})
    doc_id = str(uuid_mod.uuid4())
    sb.table("documents").insert({
        "id": doc_id, "tenant_id": tenant["id"],
        "file_name": file.filename, "storage_path": storage_path,
        "domain": domain, "file_type": "pdf",
        "file_size": len(file_bytes), "chunk_count": count, "is_enabled": True,
    }).execute()
    return {"status": "ok", "file": file.filename,
            "domain": domain, "chunks": count, "id": doc_id}


@app.patch("/api/files/{doc_id}")
async def update_file(doc_id: str, req: Request):
    from core.supabase_client import sb
    body    = await req.json()
    allowed = ["is_enabled", "domain", "file_name"]
    update  = {k: v for k, v in body.items() if k in allowed}
    sb.table("documents").update(update).eq("id", doc_id).execute()
    if "is_enabled" in update and not update["is_enabled"]:
        try:
            from core.ingest import _get_collection
            from core.supabase_client import maybe_single
            row = maybe_single(sb.table("documents").select("file_name, domain").eq("id", doc_id))
            if row:
                col      = _get_collection(TENANT, row["domain"])
                existing = col.get(where={"source": {"$contains": row["file_name"]}})
                if existing and existing["ids"]:
                    col.delete(ids=existing["ids"])
        except Exception as e:
            print(f"[files] ChromaDB delete warning: {e}")
    return {"status": "ok"}


@app.delete("/api/files/{doc_id}")
async def delete_file(doc_id: str):
    from core.supabase_client import sb, maybe_single
    row = maybe_single(sb.table("documents").select("*").eq("id", doc_id))
    if row:
        try:
            sb.storage.from_("documents").remove([row["storage_path"]])
        except Exception as e:
            print(f"[files] Storage delete warning: {e}")
        try:
            from core.ingest import _get_collection
            col      = _get_collection(TENANT, row["domain"])
            existing = col.get(where={"source": {"$contains": row["file_name"]}})
            if existing and existing["ids"]:
                col.delete(ids=existing["ids"])
        except Exception as e:
            print(f"[files] ChromaDB delete warning: {e}")
        sb.table("documents").delete().eq("id", doc_id).execute()
    return {"status": "ok"}


# ── Tenant management API ─────────────────────────────────────

@app.get("/api/tenants")
async def get_tenants():
    from core.supabase_client import sb
    res     = sb.table("tenants").select("*").order("created_at").execute()
    tenants = res.data or []
    for t in tenants:
        if t.get("ai_api_key_enc"):
            from core.crypto import decrypt, mask_key
            try:
                t["ai_api_key_masked"] = mask_key(decrypt(t["ai_api_key_enc"]))
            except Exception:
                t["ai_api_key_masked"] = "••••••••"
        else:
            t["ai_api_key_masked"] = ""
        t.pop("ai_api_key_enc", None)
    return tenants


@app.get("/api/tenants/{slug}")
async def get_tenant(slug: str):
    from core.supabase_client import sb, maybe_single
    # Accept either a tenant UUID or a slug
    t = None
    try:
        uuid.UUID(slug)
        t = maybe_single(sb.table("tenants").select("*").eq("id", slug))
    except ValueError:
        pass
    if not t:
        t = maybe_single(sb.table("tenants").select("*").eq("slug", slug))
    if not t:
        return JSONResponse({"error": "not found"}, status_code=404)
    t.pop("ai_api_key_enc", None)
    return t


@app.post("/api/tenants")
async def create_tenant(req: Request):
    from core.supabase_client import sb, generate_api_key
    body = await req.json()
    slug = body.get("slug", "").strip().lower().replace(" ", "_")
    if not slug:
        return JSONResponse({"error": "slug required"}, status_code=400)
    data = {
        "name":           body.get("name", slug),
        "slug":           slug,
        "brand_color":    body.get("brand_color", "#1a6f4a"),
        "brand_initials": body.get("brand_initials", slug[:2].upper()),
        "bot_name":       body.get("bot_name", f"{body.get('name', slug)} Assistant"),
        "welcome_msg":    body.get("welcome_msg", "Hello! How can I help you today?"),
        "system_prompt":  body.get("system_prompt", "You are a helpful assistant."),
        "industry":       body.get("industry", "Other"),
        "plan":           body.get("plan", "starter"),
        "billing_mode":   "platform",
        "ai_provider":    "anthropic",
        "ai_model":       "claude-sonnet-4-20250514",
        "is_active":      True,
    }
    res = sb.table("tenants").insert(data).execute()
    if res.data:
        tenant_id = res.data[0]["id"]
        generate_api_key(tenant_id, "public")
        generate_api_key(tenant_id, "secret")
        return res.data[0]
    return JSONResponse({"error": "Failed to create tenant"}, status_code=500)


@app.patch("/api/tenants/{slug}")
async def update_tenant(slug: str, req: Request):
    from core.supabase_client import sb
    body    = await req.json()
    allowed = ["name", "bot_name", "brand_color", "brand_initials",
               "tagline", "welcome_msg", "placeholder", "system_prompt",
               "industry", "plan", "is_active", "allowed_domains",
               "billing_mode", "ai_provider", "ai_model"]
    update  = {k: v for k, v in body.items() if k in allowed}
    sb.table("tenants").update(update).eq("slug", slug).execute()
    return {"status": "ok", "updated": list(update.keys())}


@app.post("/api/tenants/{slug}/api-key")
async def save_byok_key(slug: str, req: Request):
    from core.supabase_client import sb
    from core.crypto import encrypt, mask_key
    body    = await req.json()
    raw_key = body.get("api_key", "").strip()
    if not raw_key:
        return JSONResponse({"error": "api_key required"}, status_code=400)
    if not raw_key.startswith("sk-"):
        return JSONResponse({"error": "Invalid key — must start with sk-"}, status_code=400)
    encrypted = encrypt(raw_key)
    sb.table("tenants").update({
        "ai_api_key_enc": encrypted,
        "billing_mode":   "byok",
    }).eq("slug", slug).execute()
    return {"status": "ok", "masked": mask_key(raw_key), "billing_mode": "byok"}


@app.delete("/api/tenants/{slug}/api-key")
async def remove_byok_key(slug: str):
    from core.supabase_client import sb
    sb.table("tenants").update({
        "ai_api_key_enc": None,
        "billing_mode":   "platform",
    }).eq("slug", slug).execute()
    return {"status": "ok", "billing_mode": "platform"}


@app.get("/api/tenants/{slug}/keys")
async def get_tenant_keys(slug: str):
    from core.supabase_client import sb, maybe_single
    tenant = maybe_single(sb.table("tenants").select("id").eq("slug", slug))
    if not tenant:
        return []
    res = sb.table("api_keys").select("key_value, key_type, is_active")\
        .eq("tenant_id", tenant["id"]).eq("is_active", True).execute()
    return res.data or []


@app.post("/api/tenants/{slug}/keys")
async def create_tenant_key(slug: str):
    from core.supabase_client import sb, maybe_single, generate_api_key
    tenant = maybe_single(sb.table("tenants").select("id").eq("slug", slug))
    if not tenant:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    key = generate_api_key(tenant["id"], "public")
    return {"key_value": key, "key_type": "public"}


@app.get("/api/tenants/{slug}/embed-script")
async def get_embed_script(slug: str):
    from core.supabase_client import sb
    try:
        tenant = sb.table("tenants").select("id").eq("slug", slug).maybe_single().execute().data
    except Exception:
        tenant = None
    if not tenant:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    try:
        key_row = sb.table("api_keys").select("key_value")\
            .eq("tenant_id", tenant["id"]).eq("key_type", "public")\
            .eq("is_active", True).maybe_single().execute().data
    except Exception:
        key_row = None
    pub_key  = key_row["key_value"] if key_row else "no-key-found"
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    script   = (f'<script\n  src="{base_url}/widget.js"\n'
                f'  data-tenant="{slug}"\n  data-key="{pub_key}"\n  defer>\n</script>')
    return {"script": script, "tenant": slug, "key": pub_key}


# ── Widget & embed ────────────────────────────────────────────

@app.get("/widget.js")
async def widget_js(tenant: str = "", key: str = ""):
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    js = f"""(function(){{
  var t = document.currentScript.dataset.tenant || '{tenant}';
  var k = document.currentScript.dataset.key    || '{key}';
  var b = '{base_url}';

  // Iframe covers the corner but is non-interactive — clicks pass through
  var iframe = document.createElement('iframe');
  iframe.id  = 'chatplatform-widget';
  iframe.allowTransparency = true;
  iframe.setAttribute('allowtransparency', 'true');
  iframe.setAttribute('frameborder', '0');
  iframe.setAttribute('allow', 'microphone');
  iframe.setAttribute('title', 'Chat widget');
  iframe.src = b + '/embed/' + t + '?key=' + k + '&tenant=' + t;
  iframe.style.cssText = [
    'position:fixed',
    'bottom:0',
    'right:0',
    'width:420px',
    'height:600px',
    'border:none',
    'z-index:2147483646',
    'background:transparent',
    'background-color:transparent',
    'pointer-events:none'
  ].join(';');
  document.body.appendChild(iframe);

  // Invisible trigger div sits over the bubble button area
  var trigger = document.createElement('div');
  trigger.id = 'chatplatform-trigger';
  trigger.style.cssText = [
    'position:fixed',
    'bottom:20px',
    'right:20px',
    'width:52px',
    'height:52px',
    'border-radius:50%',
    'z-index:2147483647',
    'cursor:pointer',
    'pointer-events:all',
    'background:transparent'
  ].join(';');
  trigger.addEventListener('click', function(){{
    iframe.style.pointerEvents = 'all';
    iframe.contentWindow.postMessage('toggle', '*');
  }});
  document.body.appendChild(trigger);

  // When the chat closes, hand pointer-events back to the trigger
  window.addEventListener('message', function(e){{
    if (e.data === 'chat:closed') iframe.style.pointerEvents = 'none';
    if (e.data === 'chat:opened') iframe.style.pointerEvents = 'all';
  }});
}})();"""
    return Response(content=js, media_type="application/javascript")


@app.get("/embed/{slug}", response_class=HTMLResponse)
async def embed_chat(slug: str, key: str = ""):
    html_path = "static/embed.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
    return HTMLResponse("<p>Chat unavailable</p>")

# ── Sales contacts API — paste into app.py ───────────────────
# Add these routes AFTER the existing scraper URL CRUD section

@app.get("/api/customers")
async def get_customers():
    from core.supabase_client import sb
    res = sb.table("customers").select("*").order("created_at", desc=True).execute()
    return res.data or []


@app.get("/api/sales-contacts")
async def get_sales_contacts():
    from core.supabase_client import sb
    res = sb.table("sales_contacts").select("*").order("created_at").execute()
    return res.data or []


@app.post("/api/sales-contacts")
async def add_sales_contact(req: Request):
    from core.supabase_client import sb
    body = await req.json()
    email = body.get("email", "").strip()
    name  = body.get("name", "").strip()
    if not email or not name:
        return JSONResponse({"error": "name and email are required"}, status_code=400)
    data = {
        "name":   name,
        "email":  email,
        "phone":  body.get("phone", ""),
        "role":   body.get("role", "Sales"),
        "active": True,
    }
    res = sb.table("sales_contacts").insert(data).execute()
    return res.data[0] if res.data else JSONResponse({"error": "Insert failed"}, status_code=500)


@app.patch("/api/sales-contacts/{contact_id}")
async def update_sales_contact(contact_id: str, req: Request):
    from core.supabase_client import sb
    body    = await req.json()
    allowed = ["name", "email", "phone", "role", "active"]
    update  = {k: v for k, v in body.items() if k in allowed}
    sb.table("sales_contacts").update(update).eq("id", contact_id).execute()
    return {"status": "ok"}


@app.delete("/api/sales-contacts/{contact_id}")
async def delete_sales_contact(contact_id: str):
    from core.supabase_client import sb
    sb.table("sales_contacts").delete().eq("id", contact_id).execute()
    return {"status": "ok"}

# ── Analytics API routes — paste into app.py ─────────────────
# Add these after the existing dashboard stats API section

@app.get("/api/analytics/stats")
async def analytics_stats(days: int = 30):
    from core.analytics import get_stats
    return get_stats(TENANT, days)


@app.post("/api/analytics/event")
async def analytics_event(req: Request):
    """Manual event tracking endpoint (called from frontend if needed)."""
    from core.analytics import track
    body = await req.json()
    track(
        event_type  = body.get("event_type", ""),
        tenant_id   = TENANT,
        session_id  = body.get("session_id", ""),
        customer_id = body.get("customer_id", ""),
        data        = body.get("data", {}),
    )
    return {"status": "ok"}

# ── API Sync Routes — paste into app.py ──────────────────────
# Add these after the existing analytics routes
# Handles two-way communication between tenant website and chatbot




# ── Generate sync key for tenant ──────────────────────────────

@app.post("/api/sync/generate-key")
async def generate_sync_key(req: Request):
    """Admin generates a sync key for a tenant."""
    from core.supabase_client import sb
    body      = await req.json()
    tenant_id = body.get("tenant_id", "").strip()
    webhook   = body.get("webhook_url", "").strip()

    if not tenant_id:
        return JSONResponse({"error": "tenant_id required"}, status_code=400)

    # Generate secure random key
    sync_key = "sk_sync_" + _secrets.token_urlsafe(24)

    # Upsert — one key per tenant
    existing = sb.table("tenant_sync_keys") \
                 .select("id") \
                 .eq("tenant_id", tenant_id) \
                 .execute().data

    if existing:
        sb.table("tenant_sync_keys").update({
            "sync_key":    sync_key,
            "webhook_url": webhook,
            "is_active":   True,
        }).eq("tenant_id", tenant_id).execute()
    else:
        sb.table("tenant_sync_keys").insert({
            "tenant_id":   tenant_id,
            "sync_key":    sync_key,
            "webhook_url": webhook,
            "is_active":   True,
        }).execute()

    return {"sync_key": sync_key, "tenant_id": tenant_id}


@app.get("/api/sync/key/{tenant_id}")
async def get_sync_key(tenant_id: str):
    """Get masked sync key for a tenant (for dashboard display)."""
    from core.supabase_client import sb, maybe_single
    data = maybe_single(sb.table("tenant_sync_keys")
                           .select("sync_key, webhook_url, is_active, last_used_at")
                           .eq("tenant_id", tenant_id))
    if not data:
        return {"sync_key": None, "webhook_url": None}
    key = data["sync_key"]
    # Mask middle of key for display
    masked = key[:12] + "••••••••" + key[-4:] if key else None
    return {
        "sync_key_masked": masked,
        "webhook_url":     data.get("webhook_url"),
        "is_active":       data.get("is_active"),
        "last_used_at":    data.get("last_used_at"),
    }


# ── Stock sync — tenant pushes car data → chatbot ─────────────

@app.post("/api/sync/stock")
async def sync_stock(req: Request):
    """
    Tenant website pushes car stock to ChatPlatform.
    Authenticated with X-Sync-Key header.

    Expected body:
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
    """
    from core.supabase_client import sb, maybe_single

    sync_key = req.headers.get("X-Sync-Key", "")
    if not sync_key:
        return JSONResponse({"error": "X-Sync-Key header required"}, status_code=401)

    # Validate key
    key_row = maybe_single(sb.table("tenant_sync_keys")
                              .select("tenant_id, is_active")
                              .eq("sync_key", sync_key))

    if not key_row or not key_row["is_active"]:
        return JSONResponse({"error": "Invalid or inactive sync key"}, status_code=401)

    # Update last_used_at
    from datetime import datetime, timezone
    sb.table("tenant_sync_keys").update({
        "last_used_at": datetime.now(timezone.utc).isoformat()
    }).eq("sync_key", sync_key).execute()

    body = await req.json()
    cars = body.get("cars", [])

    if not cars:
        return JSONResponse({"error": "No cars provided"}, status_code=400)

    # Upsert all cars
    tenant_id = key_row["tenant_id"]
    for car in cars:
        car["tenant_id"] = str(tenant_id)

    sb.table("cars").upsert(cars, on_conflict="car_id").execute()

    # Track analytics
    try:
        from core.analytics import track
        track("stock_synced", str(tenant_id),
              data={"count": len(cars), "source": "api_push"})
    except Exception:
        pass

    return {"status": "ok", "synced": len(cars)}


# ── Lead webhook — chatbot pushes leads → tenant website ──────

@app.post("/api/sync/leads/push/{tenant_id}")
async def push_lead_to_tenant(tenant_id: str, req: Request):
    """
    Internal endpoint — called by leads.py after capturing a lead.
    Pushes lead to tenant's configured webhook URL.
    """
    from core.supabase_client import sb, maybe_single
    import httpx

    key_row = maybe_single(sb.table("tenant_sync_keys")
                              .select("webhook_url, sync_key")
                              .eq("tenant_id", tenant_id)
                              .eq("is_active", True))

    if not key_row or not key_row.get("webhook_url"):
        return {"status": "skipped", "reason": "no webhook configured"}

    body = await req.json()

    try:
        res = await httpx.AsyncClient().post(
            key_row["webhook_url"],
            json=body,
            headers={
                "Content-Type":  "application/json",
                "X-Sync-Key":    key_row["sync_key"],
                "X-Source":      "chatplatform",
            },
            timeout=8
        )
        return {"status": "ok", "tenant_status": res.status_code}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


# ── Leads pull — tenant polls for new leads ───────────────────

@app.get("/api/sync/leads")
async def pull_leads(req: Request):
    """
    Tenant website polls for new leads.
    Returns unnotified leads for this tenant.
    Authenticated with X-Sync-Key header.
    """
    from core.supabase_client import sb, maybe_single

    sync_key = req.headers.get("X-Sync-Key", "")
    if not sync_key:
        return JSONResponse({"error": "X-Sync-Key header required"}, status_code=401)

    key_row = maybe_single(sb.table("tenant_sync_keys")
                              .select("tenant_id, is_active")
                              .eq("sync_key", sync_key))

    if not key_row or not key_row["is_active"]:
        return JSONResponse({"error": "Invalid or inactive sync key"}, status_code=401)

    leads = sb.table("customers") \
              .select("*") \
              .eq("notified", False) \
              .order("created_at", desc=True) \
              .execute().data or []

    return {"leads": leads, "count": len(leads)}


@app.patch("/api/sync/leads/{lead_id}/notified")
async def mark_lead_notified(lead_id: str, req: Request):
    """Tenant marks a lead as notified after receiving it."""
    from core.supabase_client import sb, maybe_single

    sync_key = req.headers.get("X-Sync-Key", "")
    key_row  = maybe_single(sb.table("tenant_sync_keys")
                               .select("tenant_id")
                               .eq("sync_key", sync_key))

    if not key_row:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    sb.table("customers").update({"notified": True}).eq("id", lead_id).execute()
    return {"status": "ok"}


# ── Admin — manage tenant accounts ────────────────────────────

@app.get("/api/admin/pending-accounts")
async def get_pending_accounts(_profile: dict = Depends(require_admin)):
    """Admin gets list of pending tenant registrations."""
    from core.supabase_client import sb
    res = sb.table("profiles") \
            .select("*, tenants(name, slug)") \
            .eq("is_approved", False) \
            .order("created_at", desc=True) \
            .execute()
    return res.data or []


@app.patch("/api/admin/accounts/{profile_id}")
async def update_account(profile_id: str, req: Request,
                          _profile: dict = Depends(require_admin)):
    """Admin approves/rejects account or assigns tenant."""
    from core.supabase_client import sb
    body    = await req.json()
    allowed = ["is_approved", "role", "tenant_id", "full_name"]
    update  = {k: v for k, v in body.items() if k in allowed}
    sb.table("profiles").update(update).eq("id", profile_id).execute()
    return {"status": "ok", "updated": list(update.keys())}


@app.get("/api/admin/accounts")
async def get_all_accounts(_profile: dict = Depends(require_admin)):
    """Admin gets all user accounts."""
    from core.supabase_client import sb
    res = sb.table("profiles") \
            .select("*, tenants(name, slug, brand_color)") \
            .order("created_at", desc=True) \
            .execute()
    return res.data or []

# ── Per-Tenant Scoped API Routes — paste into app.py ─────────
# These replace/supplement existing routes with tenant scoping
# Admin can access any tenant by passing tenant_id
# Tenant users can only access their own data


# ── Tenant-scoped file manager ────────────────────────────────

@app.get("/api/tenant/{tenant_id}/files")
async def get_tenant_files(tenant_id: str, _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    res = sb.table("documents").select("*") \
            .eq("tenant_id", tenant_id) \
            .order("created_at", desc=True).execute()
    return res.data or []


@app.post("/api/tenant/{tenant_id}/files/upload")
async def upload_tenant_file(
    tenant_id: str,
    file:      UploadFile = File(...),
    domain:    str        = Form("car_specs"),
    brand:     str        = Form(""),
    model:     str        = Form(""),
    _profile:  dict       = Depends(require_tenant_access),
):
    from core.supabase_client import sb, maybe_single
    import uuid as uuid_mod

    # Get tenant config
    tenant_row = maybe_single(sb.table("tenants").select("*").eq("id", tenant_id))
    if not tenant_row:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)

    tenant_slug = tenant_row["slug"]
    file_bytes  = await file.read()
    dest        = f"uploads/{file.filename}"

    with open(dest, "wb") as f:
        f.write(file_bytes)

    # Upload to Supabase storage
    storage_path = f"{tenant_slug}/{domain}/{file.filename}"
    try:
        sb.storage.from_("documents").upload(
            storage_path, file_bytes,
            {"content-type": file.content_type or "application/pdf"})
    except Exception as e:
        print(f"[files] Storage upload warning: {e}")

    # Ingest into ChromaDB under tenant's collection
    count  = ingest_pdf(pdf_path=dest, tenant_id=tenant_slug, domain=domain,
                        meta={"brand": brand, "model": model,
                              "file_name": file.filename})
    doc_id = str(uuid_mod.uuid4())
    sb.table("documents").insert({
        "id":           doc_id,
        "tenant_id":    tenant_id,
        "file_name":    file.filename,
        "storage_path": storage_path,
        "domain":       domain,
        "file_type":    "pdf",
        "file_size":    len(file_bytes),
        "chunk_count":  count,
        "is_enabled":   True,
    }).execute()

    return {"status": "ok", "file": file.filename,
            "domain": domain, "chunks": count, "id": doc_id}


@app.patch("/api/tenant/{tenant_id}/files/{doc_id}")
async def update_tenant_file(tenant_id: str, doc_id: str, req: Request,
                              _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    body    = await req.json()
    allowed = ["is_enabled", "domain", "file_name"]
    update  = {k: v for k, v in body.items() if k in allowed}
    sb.table("documents").update(update) \
      .eq("id", doc_id).eq("tenant_id", tenant_id).execute()
    return {"status": "ok"}


@app.delete("/api/tenant/{tenant_id}/files/{doc_id}")
async def delete_tenant_file(tenant_id: str, doc_id: str,
                              _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb, maybe_single
    row = maybe_single(sb.table("documents").select("*")
                          .eq("id", doc_id).eq("tenant_id", tenant_id))
    if row:
        try:
            sb.storage.from_("documents").remove([row["storage_path"]])
        except Exception as e:
            print(f"[files] Storage delete warning: {e}")
        try:
            from core.ingest import _get_collection
            tenant_row  = maybe_single(sb.table("tenants").select("slug").eq("id", tenant_id))
            tenant_slug = tenant_row["slug"] if tenant_row else tenant_id
            col         = _get_collection(tenant_slug, row["domain"])
            existing    = col.get(where={"source": {"$contains": row["file_name"]}})
            if existing and existing["ids"]:
                col.delete(ids=existing["ids"])
        except Exception as e:
            print(f"[files] ChromaDB delete warning: {e}")
        sb.table("documents").delete().eq("id", doc_id).execute()
    return {"status": "ok"}


# ── Tenant-scoped scraper manager ─────────────────────────────

@app.get("/api/tenant/{tenant_id}/scraper/urls")
async def get_tenant_scraper_urls(tenant_id: str, _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    res = sb.table("scraper_urls").select("*") \
            .eq("tenant_id", tenant_id) \
            .order("created_at").execute()
    return res.data or []


@app.post("/api/tenant/{tenant_id}/scraper/urls")
async def add_tenant_scraper_url(tenant_id: str, req: Request,
                                  _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    body = await req.json()
    data = {
        "tenant_id":    tenant_id,
        "url":          body.get("url", "").strip(),
        "brand":        body.get("brand", ""),
        "model":        body.get("model", ""),
        "domain":       body.get("domain", "car_specs"),
        "css_selector": body.get("css_selector", "main"),
        "is_enabled":   True,
        "last_status":  "pending",
    }
    res = sb.table("scraper_urls").insert(data).execute()
    return res.data[0] if res.data else JSONResponse(
        {"error": "Insert failed"}, status_code=500)


@app.patch("/api/tenant/{tenant_id}/scraper/urls/{url_id}")
async def update_tenant_scraper_url(
        tenant_id: str, url_id: str, req: Request,
        _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    body    = await req.json()
    allowed = ["is_enabled", "url", "brand", "model",
               "domain", "css_selector"]
    update  = {k: v for k, v in body.items() if k in allowed}
    sb.table("scraper_urls").update(update) \
      .eq("id", url_id).eq("tenant_id", tenant_id).execute()
    return {"status": "ok"}


@app.delete("/api/tenant/{tenant_id}/scraper/urls/{url_id}")
async def delete_tenant_scraper_url(tenant_id: str, url_id: str,
                                     _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    sb.table("scraper_urls").delete() \
      .eq("id", url_id).eq("tenant_id", tenant_id).execute()
    return {"status": "ok"}


@app.post("/api/tenant/{tenant_id}/scraper/urls/{url_id}/run")
async def run_tenant_scraper_url(tenant_id: str, url_id: str,
                                  _profile: dict = Depends(require_tenant_access)):
    import threading
    from core.supabase_client import sb, maybe_single, update_scraper_status
    from core.scraper import _fetch_page, _extract_text

    row = maybe_single(sb.table("scraper_urls").select("*")
                          .eq("id", url_id).eq("tenant_id", tenant_id))
    if not row:
        return JSONResponse({"error": "URL not found"}, status_code=404)

    # Get tenant slug for ChromaDB collection
    tenant_row  = maybe_single(sb.table("tenants").select("slug").eq("id", tenant_id))
    tenant_slug = tenant_row["slug"] if tenant_row else str(tenant_id)

    def run():
        url = row["url"]
        if not url.startswith("http"):
            url = "https://" + url
        html = _fetch_page(url)
        if not html:
            update_scraper_status(url_id, "fail", error="fetch failed")
            return
        text = _extract_text(html, row.get("css_selector", "main"))
        if len(text) < 100:
            update_scraper_status(url_id, "fail",
                                  error=f"only {len(text)} chars")
            return
        doc_id = f"web_{row.get('brand','').lower()}_{row.get('model','').lower()}"
        chunks = ingest_text(text=text, doc_id=doc_id,
                             tenant_id=tenant_slug,
                             domain=row.get("domain", "car_specs"),
                             meta={"brand": row.get("brand"),
                                   "source": url})
        update_scraper_status(url_id, "ok", chunk_count=chunks)

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started", "url_id": url_id}


@app.post("/api/tenant/{tenant_id}/scraper/run-all")
async def run_all_tenant_scrapers(tenant_id: str,
                                   _profile: dict = Depends(require_tenant_access)):
    import threading
    from core.supabase_client import sb, maybe_single

    tenant_row  = maybe_single(sb.table("tenants").select("slug").eq("id", tenant_id))
    tenant_slug = tenant_row["slug"] if tenant_row else str(tenant_id)

    def run():
        from core.scraper import scrape_brand_pages
        scrape_brand_pages(tenant_slug)

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started", "tenant_id": tenant_id}


# ── Tenant-scoped analytics ───────────────────────────────────

@app.get("/api/tenant/{tenant_id}/analytics")
async def get_tenant_analytics(tenant_id: str, days: int = 30,
                                _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb, maybe_single
    from core.analytics import get_stats

    tenant_row  = maybe_single(sb.table("tenants").select("slug").eq("id", tenant_id))
    tenant_slug = tenant_row["slug"] if tenant_row else str(tenant_id)
    return get_stats(tenant_slug, days)


# ── Tenant-scoped leads ───────────────────────────────────────

@app.get("/api/tenant/{tenant_id}/leads")
async def get_tenant_leads(tenant_id: str, _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    res = sb.table("customers").select("*") \
            .eq("tenant_id", tenant_id) \
            .order("created_at", desc=True).execute()
    return res.data or []


# ── Tenant-scoped inventory (cars / products / etc.) ──────────

CAR_EDITABLE_FIELDS = [
    "brand", "model", "variant", "year", "body_type", "segment",
    "price_otr", "price_basic", "sst_exempt", "engine_cc", "transmission",
    "fuel_type", "power_hp", "torque_nm", "fuel_cons", "stock", "colour",
    "condition", "status", "spec_pdf_url",
]


@app.get("/api/tenant/{tenant_id}/inventory")
async def get_tenant_inventory(tenant_id: str, _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    res = sb.table("cars").select("*") \
            .eq("tenant_id", tenant_id) \
            .order("updated_at", desc=True).execute()
    return res.data or []


@app.post("/api/tenant/{tenant_id}/inventory")
async def create_tenant_inventory_item(tenant_id: str, req: Request,
                                        _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    from datetime import datetime, timezone

    body   = await req.json()
    car_id = (body.get("car_id") or "").strip()
    if not car_id:
        return JSONResponse({"error": "car_id is required"}, status_code=400)

    item = {k: v for k, v in body.items() if k in CAR_EDITABLE_FIELDS}
    item["car_id"]     = car_id
    item["tenant_id"]  = tenant_id
    item["updated_at"] = datetime.now(timezone.utc).isoformat()

    sb.table("cars").upsert(item, on_conflict="car_id").execute()
    return {"status": "ok"}


@app.put("/api/tenant/{tenant_id}/inventory/{car_id}")
async def update_tenant_inventory_item(tenant_id: str, car_id: str, req: Request,
                                        _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    from datetime import datetime, timezone

    body   = await req.json()
    update = {k: v for k, v in body.items() if k in CAR_EDITABLE_FIELDS}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()

    sb.table("cars").update(update) \
      .eq("car_id", car_id).eq("tenant_id", tenant_id).execute()
    return {"status": "ok"}


@app.delete("/api/tenant/{tenant_id}/inventory/{car_id}")
async def delete_tenant_inventory_item(tenant_id: str, car_id: str,
                                        _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    sb.table("cars").delete() \
      .eq("car_id", car_id).eq("tenant_id", tenant_id).execute()
    return {"status": "ok"}


@app.post("/api/tenant/{tenant_id}/inventory/sync")
async def sync_inventory_from_api(tenant_id: str,
                                   _profile: dict = Depends(require_tenant_access)):
    """Pull live cars from the tenant's configured external API and upsert into cars table."""
    from core.supabase_client import sb
    from core.tenant_api import fetch_live_cars
    from datetime import datetime, timezone

    cars = fetch_live_cars(tenant_id)
    if cars is None:
        return JSONResponse({"error": "No external API configured"}, status_code=400)
    if not cars:
        return JSONResponse({"error": "External API returned no cars"}, status_code=502)

    now = datetime.now(timezone.utc).isoformat()
    for car in cars:
        car["tenant_id"] = str(tenant_id)
        car["updated_at"] = now

    sb.table("cars").upsert(cars, on_conflict="car_id").execute()
    return {"status": "ok", "synced": len(cars)}


# ── Tenant sync key management ────────────────────────────────

@app.get("/api/tenant/{tenant_id}/sync-key")
async def get_tenant_sync_key_full(tenant_id: str,
                                    _profile: dict = Depends(require_tenant_access)):
    """Returns full sync key — used by tenant dashboard."""
    from core.supabase_client import sb, maybe_single
    data = maybe_single(sb.table("tenant_sync_keys").select("*").eq("tenant_id", tenant_id))
    if not data:
        return {"sync_key": None, "webhook_url": None, "is_active": False}
    return data


@app.post("/api/tenant/{tenant_id}/sync-key/generate")
async def generate_tenant_sync_key(tenant_id: str, req: Request,
                                    _profile: dict = Depends(require_tenant_access)):
    import secrets as _sec
    from core.supabase_client import sb
    body        = await req.json()
    webhook_url = body.get("webhook_url", "")
    sync_key    = "sk_sync_" + _sec.token_urlsafe(24)

    existing = sb.table("tenant_sync_keys").select("id") \
                 .eq("tenant_id", tenant_id).execute().data

    if existing:
        sb.table("tenant_sync_keys").update({
            "sync_key":    sync_key,
            "webhook_url": webhook_url,
            "is_active":   True,
        }).eq("tenant_id", tenant_id).execute()
    else:
        sb.table("tenant_sync_keys").insert({
            "tenant_id":   tenant_id,
            "sync_key":    sync_key,
            "webhook_url": webhook_url,
            "is_active":   True,
        }).execute()

    return {"status": "ok", "sync_key": sync_key}


# ── Tenant external car API (live price/stock pull) ──────────

@app.get("/api/tenant/{tenant_id}/external-api")
async def get_external_api_config(tenant_id: str,
                                   _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb, maybe_single
    data = maybe_single(sb.table("tenant_sync_keys").select("external_api").eq("tenant_id", tenant_id))
    config = (data or {}).get("external_api") or {}
    if config.get("auth_value"):
        config = {**config, "auth_value": "••••••••"}
    return config


@app.put("/api/tenant/{tenant_id}/external-api")
async def set_external_api_config(tenant_id: str, req: Request,
                                   _profile: dict = Depends(require_tenant_access)):
    from core.supabase_client import sb
    body = await req.json()

    allowed = ["base_url", "list_path", "detail_path",
               "auth_header", "auth_value", "field_map"]
    config  = {k: body[k] for k in allowed if k in body}

    existing = sb.table("tenant_sync_keys").select("id, external_api") \
                 .eq("tenant_id", tenant_id).execute().data

    # Don't overwrite a real auth_value with the masked placeholder.
    if config.get("auth_value") == "••••••••" and existing:
        config.pop("auth_value")
        old = (existing[0].get("external_api") or {}).get("auth_value")
        if old:
            config["auth_value"] = old

    if not existing:
        return JSONResponse(
            {"error": "Generate a sync key first (Sync Key card) before configuring the external API"},
            status_code=400)

    merged = {**(existing[0].get("external_api") or {}), **config}
    sb.table("tenant_sync_keys").update({"external_api": merged}) \
      .eq("tenant_id", tenant_id).execute()

    return {"status": "ok"}


@app.post("/api/tenant/{tenant_id}/external-api/test")
async def test_external_api_config(tenant_id: str,
                                    _profile: dict = Depends(require_tenant_access)):
    from core.tenant_api import fetch_live_cars, get_external_api_config

    if not get_external_api_config(tenant_id):
        return JSONResponse({"error": "No external API configured"}, status_code=400)

    cars = fetch_live_cars(tenant_id)
    if cars is None:
        return JSONResponse({"error": "Request failed — check base URL, path, and auth"}, status_code=502)
    return {"status": "ok", "count": len(cars), "sample": cars[:3]}


# ── New dashboard page routes — paste into app.py ────────────
# Add these after the existing dashboard routes section

@app.get("/dashboard/register", response_class=HTMLResponse)
async def register_page():
    html_path = "static/dashboard/register.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Register page not found</h2>", status_code=404)


@app.get("/dashboard/tenant", response_class=HTMLResponse)
async def tenant_dashboard():
    html_path = "static/dashboard/tenant.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Tenant dashboard not found</h2>", status_code=404)


@app.get("/dashboard/tenant/files", response_class=HTMLResponse)
async def tenant_files_page():
    html_path = "static/dashboard/tenant_files.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Page not found</h2>", status_code=404)


@app.get("/dashboard/tenant/scraper", response_class=HTMLResponse)
async def tenant_scraper_page():
    html_path = "static/dashboard/tenant_scraper.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Page not found</h2>", status_code=404)


@app.get("/dashboard/tenant/api", response_class=HTMLResponse)
async def tenant_api_page():
    html_path = "static/dashboard/tenant_api.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Page not found</h2>", status_code=404)


@app.get("/dashboard/tenant/leads", response_class=HTMLResponse)
async def tenant_leads_page():
    html_path = "static/dashboard/tenant_leads.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Page not found</h2>", status_code=404)


@app.get("/dashboard/tenant/inventory", response_class=HTMLResponse)
async def tenant_inventory_page():
    html_path = "static/dashboard/tenant_inventory.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Page not found</h2>", status_code=404)


@app.get("/dashboard/accounts", response_class=HTMLResponse)
async def accounts_page():
    html_path = "static/dashboard/account.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h2>Accounts page not found</h2>", status_code=404)


# Catch-all for any other /dashboard/<page> — must stay after the
# explicit routes above, since /dashboard/accounts maps to account.html
@app.get("/dashboard/{page}", response_class=HTMLResponse)
async def dashboard_page(page: str):
    html_path = f"static/dashboard/{page}.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read(),
                                media_type="text/html; charset=utf-8")
    return HTMLResponse(f"<h2>Page not found: {page}.html</h2>", status_code=404)