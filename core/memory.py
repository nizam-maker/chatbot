# core/memory.py
# ─────────────────────────────────────────────────────────────
#  Session memory — episodic memory per customer
#  Uses SQLite locally (swap to Redis in production)
#  Stores: last 10 messages, customer name, car interest
# ─────────────────────────────────────────────────────────────

import sqlite3
import json
import os
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
                contact_asked INTEGER DEFAULT 0,
                lead_captured INTEGER DEFAULT 0,
                updated_at    TEXT
            )
        """)
        # Add columns if upgrading from older schema
        try:
            c.execute("ALTER TABLE sessions ADD COLUMN contact_asked INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE sessions ADD COLUMN lead_captured INTEGER DEFAULT 0")
        except Exception:
            pass


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
            "contact_asked": False,
            "lead_captured": False,
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
        "contact_asked": bool(row[8]) if len(row) > 8 else False,
        "lead_captured": bool(row[9]) if len(row) > 9 else False,
    }


def save_session(session: dict):
    """Save or update a session. Keeps only the last 10 messages."""
    msgs = session.get("messages", [])[-10:]  # episodic: last 10 turns only

    with _conn() as c:
        c.execute("""
            INSERT INTO sessions
                (session_id, tenant_id, customer_id, customer_name,
                 car_interest, last_intent, messages, summary,
                 contact_asked, lead_captured, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET
                tenant_id     = excluded.tenant_id,
                customer_name = excluded.customer_name,
                car_interest  = excluded.car_interest,
                last_intent   = excluded.last_intent,
                messages      = excluded.messages,
                summary       = excluded.summary,
                contact_asked = excluded.contact_asked,
                lead_captured = excluded.lead_captured,
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
            int(bool(session.get("contact_asked", False))),
            int(bool(session.get("lead_captured", False))),
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