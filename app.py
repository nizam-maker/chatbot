# app.py
# ─────────────────────────────────────────────────────────────
#  FastAPI entry point
#  Run with: uvicorn app:app --reload
# ─────────────────────────────────────────────────────────────

import os
import uuid
import importlib
import shutil

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from core.engine import chat
from core.ingest import ingest_pdf, ingest_text
from core.memory import load_session
from core.scheduler import start_scheduler, stop_scheduler, get_status

load_dotenv()

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
    html_path = "static/index.html"
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


@app.get("/dashboard/{page}", response_class=HTMLResponse)
async def dashboard_page(page: str):
    html_path = f"static/dashboard/{page}.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read(),
                                media_type="text/html; charset=utf-8")
    return HTMLResponse(f"<h2>Page not found: {page}.html</h2>", status_code=404)


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
    from core.supabase_client import sb, update_scraper_status
    from core.scraper import _fetch_page, _extract_text
    row = sb.table("scraper_urls").select("*").eq("id", url_id).single().execute().data
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
            row = sb.table("documents").select("file_name, domain")\
                .eq("id", doc_id).single().execute().data
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
    from core.supabase_client import sb
    row = sb.table("documents").select("*").eq("id", doc_id).single().execute().data
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
    from core.supabase_client import sb
    tenant = sb.table("tenants").select("id").eq("slug", slug).single().execute().data
    if not tenant:
        return []
    res = sb.table("api_keys").select("key_value, key_type, is_active")\
        .eq("tenant_id", tenant["id"]).eq("is_active", True).execute()
    return res.data or []


@app.post("/api/tenants/{slug}/keys")
async def create_tenant_key(slug: str):
    from core.supabase_client import sb, generate_api_key
    tenant = sb.table("tenants").select("id").eq("slug", slug).single().execute().data
    if not tenant:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    key = generate_api_key(tenant["id"], "public")
    return {"key_value": key, "key_type": "public"}


@app.get("/api/tenants/{slug}/embed-script")
async def get_embed_script(slug: str):
    from core.supabase_client import sb
    tenant = sb.table("tenants").select("id").eq("slug", slug).single().execute().data
    if not tenant:
        return JSONResponse({"error": "Tenant not found"}, status_code=404)
    key_row = sb.table("api_keys").select("key_value")\
        .eq("tenant_id", tenant["id"]).eq("key_type", "public")\
        .eq("is_active", True).single().execute().data
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
  var t=document.currentScript.dataset.tenant||'{tenant}';
  var k=document.currentScript.dataset.key||'{key}';
  var i=document.createElement('iframe');
  i.src='{base_url}/embed/'+t+'?key='+k;
  i.style.cssText='position:fixed;bottom:20px;right:20px;width:370px;height:580px;border:none;z-index:99999;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.15)';
  document.body.appendChild(i);
}})();"""
    return Response(content=js, media_type="application/javascript")


@app.get("/embed/{slug}", response_class=HTMLResponse)
async def embed_chat(slug: str, key: str = ""):
    html_path = "static/index.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), media_type="text/html; charset=utf-8")
    return HTMLResponse("<p>Chat unavailable</p>")