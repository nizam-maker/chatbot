# core/analytics.py
# ─────────────────────────────────────────────────────────────
#  Analytics tracking — logs events to Supabase analytics_events
#  Called from engine.py and leads.py
# ─────────────────────────────────────────────────────────────

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def track(
    event_type: str,
    tenant_id:  str,
    session_id: str  = "",
    customer_id: str = "",
    data: dict       = {}
):
    """
    Log an analytics event to Supabase.
    Non-blocking — silently ignores errors so it never breaks chat.

    event_type values:
        chat_start      — new session started
        message_sent    — user sent a message
        lead_captured   — lead was captured
        car_queried     — specific car was asked about
    """
    try:
        from core.supabase_client import sb
        sb.table("analytics_events").insert({
            "tenant_id":   tenant_id,
            "event_type":  event_type,
            "session_id":  session_id,
            "customer_id": customer_id,
            "data":        data,
        }).execute()
    except Exception as e:
        logger.warning(f"[analytics] Track failed (non-critical): {e}")


def get_stats(tenant_id: str, days: int = 30) -> dict:
    """
    Return aggregated analytics stats for the dashboard.
    """
    try:
        from core.supabase_client import sb
        from datetime import timedelta

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        events = sb.table("analytics_events") \
                   .select("*") \
                   .eq("tenant_id", tenant_id) \
                   .gte("created_at", since) \
                   .execute().data or []

        # ── Aggregate ─────────────────────────────────────────
        sessions     = set()
        messages     = []
        leads        = []
        cars_queried = {}
        questions    = []
        daily        = {}

        for e in events:
            et   = e["event_type"]
            data = e.get("data") or {}
            day  = e["created_at"][:10]  # YYYY-MM-DD

            daily.setdefault(day, {"sessions": set(), "messages": 0, "leads": 0})

            if et == "chat_start":
                sessions.add(e["session_id"])
                daily[day]["sessions"].add(e["session_id"])

            elif et == "message_sent":
                messages.append(e)
                daily[day]["messages"] += 1
                if data.get("question"):
                    questions.append(data["question"])

            elif et == "lead_captured":
                leads.append(e)
                daily[day]["leads"] += 1

            elif et == "car_queried":
                key = f"{data.get('brand','')} {data.get('model','')}".strip()
                if key:
                    cars_queried[key] = cars_queried.get(key, 0) + 1

        # Top 8 cars
        top_cars = sorted(cars_queried.items(), key=lambda x: x[1], reverse=True)[:8]

        # Daily chart data — last 14 days
        from datetime import date, timedelta as td
        chart_days = []
        for i in range(13, -1, -1):
            d   = (date.today() - td(days=i)).isoformat()
            day = daily.get(d, {})
            chart_days.append({
                "date":     d,
                "sessions": len(day.get("sessions", set())),
                "messages": day.get("messages", 0),
                "leads":    day.get("leads", 0),
            })

        # Lead conversion rate
        total_sessions = len(sessions)
        total_leads    = len(leads)
        conversion     = round((total_leads / total_sessions * 100), 1) \
                         if total_sessions > 0 else 0

        return {
            "total_sessions":    total_sessions,
            "total_messages":    len(messages),
            "total_leads":       total_leads,
            "conversion_rate":   conversion,
            "top_cars":          [{"name": k, "count": v} for k, v in top_cars],
            "daily_chart":       chart_days,
            "period_days":       days,
        }

    except Exception as e:
        logger.error(f"[analytics] get_stats failed: {e}")
        return {
            "total_sessions":  0,
            "total_messages":  0,
            "total_leads":     0,
            "conversion_rate": 0,
            "top_cars":        [],
            "daily_chart":     [],
            "period_days":     days,
        }