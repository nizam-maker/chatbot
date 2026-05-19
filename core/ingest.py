# core/ingest.py
# ─────────────────────────────────────────────────────────────
#  ETL Extract + Load step
#  Reads PDFs and plain text → splits into chunks →
#  embeds with sentence-transformers → stores in ChromaDB
# ─────────────────────────────────────────────────────────────

import os
import chromadb
from chromadb.utils.embedding_functions import (
    SentenceTransformerEmbeddingFunction,
)
from langchain_community.document_loaders import PDFPlumberLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
CHUNK_SIZE  = 500
CHUNK_OVERLAP = 50

# ── Embedding model (runs locally — no API cost) ─────────────
embed_fn = SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# ── ChromaDB client (persists to disk) ───────────────────────
chroma = chromadb.PersistentClient(path=CHROMA_PATH)

# ── Text splitter ─────────────────────────────────────────────
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
)


def _get_collection(tenant_id: str, domain: str):
    """Get or create a ChromaDB collection for a tenant + domain."""
    name = f"{tenant_id}__{domain}"   # e.g. laman_auto__car_specs
    return chroma.get_or_create_collection(
        name=name,
        embedding_function=embed_fn
    )


def ingest_pdf(
    pdf_path: str,
    tenant_id: str,
    domain: str,
    meta: dict = {}
):
    """
    Extract text from a PDF, split into chunks,
    embed and store into the correct tenant + domain collection.
    """
    print(f"[ingest] Loading {pdf_path} → {tenant_id}/{domain}")

    loader = PDFPlumberLoader(pdf_path)
    docs   = loader.load()
    chunks = splitter.split_documents(docs)

    col = _get_collection(tenant_id, domain)

    for i, chunk in enumerate(chunks):
        chunk_id = f"{os.path.basename(pdf_path)}_chunk{i}"
        col.add(
            ids=[chunk_id],
            documents=[chunk.page_content],
            metadatas=[{
                **chunk.metadata,
                **meta,
                "tenant_id": tenant_id,
                "domain":    domain,
                "source":    pdf_path,
            }]
        )

    print(f"[ingest] Done — {len(chunks)} chunks stored")
    return len(chunks)


def ingest_text(
    text: str,
    doc_id: str,
    tenant_id: str,
    domain: str,
    meta: dict = {}
):
    """
    Ingest a raw text string (FAQ, news snippet, etc.)
    into the correct tenant + domain collection.
    """
    chunks = splitter.split_text(text)
    col    = _get_collection(tenant_id, domain)

    col.add(
        ids=[f"{doc_id}_chunk{i}" for i in range(len(chunks))],
        documents=chunks,
        metadatas=[{
            **meta,
            "tenant_id": tenant_id,
            "domain":    domain,
            "doc_id":    doc_id,
        }] * len(chunks)
    )

    print(f"[ingest] Text ingested — {len(chunks)} chunks → {tenant_id}/{domain}")
    return len(chunks)


def retrieve(
    query: str,
    tenant_id: str,
    domains: list[str],
    n: int = 4
) -> list[str]:
    """
    Search one or more domains for chunks relevant to the query.
    Returns a flat list of text chunks, best match first.
    """
    results = []

    for domain in domains:
        try:
            col = _get_collection(tenant_id, domain)
            res = col.query(query_texts=[query], n_results=min(n, 2))
            results.extend(res["documents"][0])
        except Exception:
            pass  # collection may be empty — skip silently

    return results[:n]