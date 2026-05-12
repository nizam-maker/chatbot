# app.py
# ─────────────────────────────────────────────────────────────
#  FastAPI entry point
#  Loads the correct tenant based on TENANT in .env
#  Run with: uvicorn app:app --reload
# ─────────────────────────────────────────────────────────────

import os
import uuid
import importlib
import shutil

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from core.engine import chat
from core.ingest import ingest_pdf, ingest_text
from core.memory import load_session

load_dotenv()

# ── Load tenant config dynamically from .env ─────────────────
TENANT = os.getenv("TENANT", "laman_auto")

try:
    tenant_module = importlib.import_module(f"tenants.{TENANT}.config")
    tenant_cfg = {k: getattr(tenant_module, k) for k in dir(tenant_module)
                  if not k.startswith("_")}
    print(f"[app] Tenant loaded: {TENANT}")
except ModuleNotFoundError:
    raise RuntimeError(f"Tenant '{TENANT}' not found in tenants/ folder.")

# ── FastAPI app ───────────────────────────────────────────────
app = FastAPI(title=tenant_cfg.get("BOT_NAME", "Chatbot"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)

# Serve static files (index.html)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Routes ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the chat UI."""
    html_path = "static/index.html"
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            return f.read()
    # Fallback — plain confirmation if UI not yet created
    return HTMLResponse("""
        <h2 style="font-family:sans-serif;padding:40px">
        ✅ Chatbot platform is running!<br>
        <small style="color:#888">Add static/index.html to see the chat UI.</small>
        </h2>
    """)


@app.get("/api/config")
async def api_config():
    """Return public tenant config for the UI."""
    return {
        "bot_name":     tenant_cfg.get("BOT_NAME"),
        "welcome_msg":  tenant_cfg.get("WELCOME_MSG"),
        "quick_replies":tenant_cfg.get("QUICK_REPLIES", []),
        "brand_color":  tenant_cfg.get("BRAND_COLOR", "#333"),
        "brand_initials":tenant_cfg.get("BRAND_INITIALS", "AI"),
        "tenant_id":    TENANT,
    }


@app.post("/api/chat")
async def api_chat(req: Request):
    """Main chat endpoint."""
    body        = await req.json()
    user_msg    = body.get("message", "").strip()
    session_id  = body.get("session_id") or str(uuid.uuid4())
    customer_id = body.get("customer_id", "guest")

    if not user_msg:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    result = chat(
        user_msg    = user_msg,
        session_id  = session_id,
        tenant_cfg  = tenant_cfg,
        customer_id = customer_id,
    )
    return result


@app.get("/api/session/{session_id}")
async def api_session(session_id: str):
    """Return current session memory."""
    return load_session(session_id)


@app.post("/api/ingest/pdf")
async def api_ingest_pdf(
    file:   UploadFile = File(...),
    domain: str        = Form(...),
    brand:  str        = Form(""),
    model:  str        = Form(""),
):
    """Upload a PDF and ingest it into the knowledge base."""
    domains = tenant_cfg.get("DOMAINS", [])
    if domain not in domains:
        return JSONResponse(
            {"error": f"Unknown domain. Choose from: {domains}"},
            status_code=400
        )

    dest = f"uploads/{file.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    count = ingest_pdf(
        pdf_path  = dest,
        tenant_id = TENANT,
        domain    = domain,
        meta      = {"brand": brand, "model": model},
    )
    return {"status": "ok", "file": file.filename,
            "domain": domain, "chunks": count}


@app.post("/api/ingest/text")
async def api_ingest_text(req: Request):
    """Ingest a raw text snippet into the knowledge base."""
    body   = await req.json()
    text   = body.get("text", "").strip()
    domain = body.get("domain", "faq_support")
    doc_id = body.get("doc_id") or str(uuid.uuid4())

    domains = tenant_cfg.get("DOMAINS", [])
    if domain not in domains:
        return JSONResponse({"error": "Unknown domain."}, status_code=400)

    count = ingest_text(
        text      = text,
        doc_id    = doc_id,
        tenant_id = TENANT,
        domain    = domain,
    )
    return {"status": "ok", "doc_id": doc_id,
            "domain": domain, "chunks": count}


@app.get("/api/health")
async def health():
    return {"status": "ok", "tenant": TENANT,
            "domains": tenant_cfg.get("DOMAINS", [])}