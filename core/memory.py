# core/memory.py
# ─────────────────────────────────────────────────────────────
#  Session memory — episodic memory per customer
#  Uses SQLite locally (swap to Redis in production)
#  Stores: last 10 messages, customer name, car interest
# ─────────────────────────────────────────────────────────────

import os
import sqlite3
import json
from datetime import datetime

MEM_DB = os.getenv("MEMORY_DB_PATH", "memory.db")


def _conn():
    """Open a SQLite connection to the memory database."""
    return sqlite3.connect(MEM_DB)


def init_memory():
    """Create the sessions table if it does not exist yet."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id    TEXT PRIMARY KEY,
                tenant_id     TEXT,
                customer_id   TEXT,
                customer_name TEXT,
                car_interest  TEXT,
                last_intent   TEXT,
                messages      TEXT,
                summary       TEXT,
                updated_at    TEXT
            )
        """)


def load_session(session_id: str) -> dict:
    """Load an existing session. Returns empty session if not found."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()

    if not row:
        return {
            "session_id":    session_id,
            "tenant_id":     "",
            "customer_id":   "guest",
            "customer_name": "",
            "car_interest":  "",
            "last_intent":   "",
            "messages":      [],
            "summary":       "",
        }

    return {
        "session_id":    row[0],
        "tenant_id":     row[1],
        "customer_id":   row[2],
        "customer_name": row[3],
        "car_interest":  row[4],
        "last_intent":   row[5],
        "messages":      json.loads(row[6] or "[]"),
        "summary":       row[7] or "",
    }


def save_session(session: dict):
    """Save or update a session. Keeps only the last 10 messages."""
    msgs = session.get("messages", [])[-10:]  # episodic: last 10 turns only

    with _conn() as c:
        c.execute("""
            INSERT INTO sessions
                (session_id, tenant_id, customer_id, customer_name,
                 car_interest, last_intent, messages, summary, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
                tenant_id     = excluded.tenant_id,
                customer_name = excluded.customer_name,
                car_interest  = excluded.car_interest,
                last_intent   = excluded.last_intent,
                messages      = excluded.messages,
                summary       = excluded.summary,
                updated_at    = excluded.updated_at
        """, (
            session["session_id"],
            session.get("tenant_id",     ""),
            session.get("customer_id",   "guest"),
            session.get("customer_name", ""),
            session.get("car_interest",  ""),
            session.get("last_intent",   ""),
            json.dumps(msgs),
            session.get("summary",       ""),
            datetime.utcnow().isoformat()
        ))


def add_message(session: dict, role: str, content: str) -> dict:
    """Append a message to the session and return updated session."""
    session["messages"].append({"role": role, "content": content})
    return session


def clear_session(session_id: str):
    """Delete a session entirely — used for testing or reset."""
    with _conn() as c:
        c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


# Initialise the database table on import
init_memory()