# core/ingest.py
# ─────────────────────────────────────────────────────────────
#  ETL Extract + Load step
#  Smart PDF ingestion — text extraction with OCR fallback
#  Splits into chunks → embeds → stores in ChromaDB
# ─────────────────────────────────────────────────────────────

import os
import chromadb
from chromadb.utils.embedding_functions import (
    SentenceTransformerEmbeddingFunction,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH   = os.getenv("CHROMA_PATH", "./chroma_db")
CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50

# ── Embedding model (runs locally — no API cost) ─────────────
embed_fn = SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# ── ChromaDB client (persists to disk) ───────────────────────
chroma = chromadb.PersistentClient(path=CHROMA_PATH)

# ── Text splitter ─────────────────────────────────────────────
splitter = RecursiveCharacterTextSplitter(
    chunk_size    = CHUNK_SIZE,
    chunk_overlap = CHUNK_OVERLAP,
)


def _get_collection(tenant_id: str, domain: str):
    """Get or create a ChromaDB collection for a tenant + domain."""
    name = f"{tenant_id}__{domain}"
    return chroma.get_or_create_collection(
        name             = name,
        embedding_function = embed_fn
    )


def ingest_pdf(
    pdf_path:  str,
    tenant_id: str,
    domain:    str,
    meta:      dict = {}
):
    """
    Smart PDF ingestion — auto-detects image-based PDFs and uses OCR.
    Splits into chunks, embeds and stores into ChromaDB.
    Returns number of chunks stored.
    """
    from core.ocr import extract_text_smart, is_image_based_pdf

    print(f"[ingest] Loading {pdf_path} → {tenant_id}/{domain}")

    # Smart extraction — text or OCR automatically
    is_image = is_image_based_pdf(pdf_path)
    text     = extract_text_smart(pdf_path)

    if not text or len(text.strip()) < 50:
        print(f"[ingest] Warning — very little text extracted from {pdf_path}")

    # Split into chunks
    chunks = splitter.split_text(text) if text else []

    if not chunks:
        print(f"[ingest] No chunks — skipping {pdf_path}")
        return 0

    col = _get_collection(tenant_id, domain)

    for i, chunk in enumerate(chunks):
        chunk_id = f"{os.path.basename(pdf_path)}_chunk{i}"
        col.add(
            ids       = [chunk_id],
            documents = [chunk],
            metadatas = [{
                **meta,
                "tenant_id": tenant_id,
                "domain":    domain,
                "source":    pdf_path,
                "ocr_used":  str(is_image),
            }]
        )

    method = "OCR" if is_image else "text"
    print(f"[ingest] Done — {len(chunks)} chunks stored ({method})")
    return len(chunks)


def ingest_text(
    text:      str,
    doc_id:    str,
    tenant_id: str,
    domain:    str,
    meta:      dict = {}
):
    """
    Ingest a raw text string (FAQ, news snippet, etc.)
    into the correct tenant + domain collection.
    """
    chunks = splitter.split_text(text)
    col    = _get_collection(tenant_id, domain)

    col.add(
        ids       = [f"{doc_id}_chunk{i}" for i in range(len(chunks))],
        documents = chunks,
        metadatas = [{
            **meta,
            "tenant_id": tenant_id,
            "domain":    domain,
            "doc_id":    doc_id,
        }] * len(chunks)
    )

    print(f"[ingest] Text ingested — {len(chunks)} chunks → {tenant_id}/{domain}")
    return len(chunks)


def retrieve(
    query:     str,
    tenant_id: str,
    domains:   list,
    n:         int = 4
) -> list[str]:
    """
    Semantic search across one or more domains.
    Returns flat list of text chunks, best match first.
    """
    results = []

    for domain in domains:
        try:
            col = _get_collection(tenant_id, domain)
            res = col.query(query_texts=[query], n_results=min(n, 2))
            results.extend(res["documents"][0])
        except Exception:
            pass  # empty collection — skip silently

    return results[:n]