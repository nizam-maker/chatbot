# core/scheduler.py
# ─────────────────────────────────────────────────────────────
#  APScheduler — runs scraper + RSS feed on a schedule
#  Starts automatically when FastAPI starts
#  Scraper: every 7 days
#  News:    every 24 hours
# ─────────────────────────────────────────────────────────────

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger    = logging.getLogger(__name__)
scheduler = BackgroundScheduler()
_status   = {
    "scraper": {"last_run": None, "last_result": None},
    "news":    {"last_run": None, "last_result": None},
}


def _run_scraper():
    """Job: scrape brand websites weekly."""
    from core.scraper import scrape_brand_pages
    from datetime import datetime
    logger.info("[scheduler] Running brand website scraper...")
    try:
        result = scrape_brand_pages()
        _status["scraper"]["last_run"]    = datetime.utcnow().isoformat()
        _status["scraper"]["last_result"] = result
        logger.info(f"[scheduler] Scraper done — {result}")
    except Exception as e:
        logger.error(f"[scheduler] Scraper error: {e}")


def _run_news():
    """Job: fetch RSS news daily."""
    from core.rss_feed import fetch_news
    from datetime import datetime
    logger.info("[scheduler] Running RSS news fetch...")
    try:
        result = fetch_news()
        _status["news"]["last_run"]    = datetime.utcnow().isoformat()
        _status["news"]["last_result"] = result
        logger.info(f"[scheduler] News done — {result}")
    except Exception as e:
        logger.error(f"[scheduler] News error: {e}")


def start_scheduler():
    """Start the background scheduler. Call once on app startup."""
    if scheduler.running:
        return

    # Brand website scraper — every 7 days
    scheduler.add_job(
        _run_scraper,
        trigger  = IntervalTrigger(days=7),
        id       = "brand_scraper",
        name     = "Brand website scraper",
        replace_existing = True,
    )

    # RSS news feed — every 24 hours
    scheduler.add_job(
        _run_news,
        trigger  = IntervalTrigger(hours=24),
        id       = "rss_news",
        name     = "RSS news feed",
        replace_existing = True,
    )

    scheduler.start()
    logger.info("[scheduler] Started — scraper every 7d, news every 24h")

    # Run news immediately on first startup to populate surat_khabar
    import threading
    threading.Thread(target=_run_news,    daemon=True).start()
    threading.Thread(target=_run_scraper, daemon=True).start()


def stop_scheduler():
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[scheduler] Stopped")


def get_status() -> dict:
    """Return last run times and results for both jobs."""
    return {
        "scheduler_running": scheduler.running,
        "jobs": {
            "brand_scraper": {
                **_status["scraper"],
                "next_run": str(scheduler.get_job("brand_scraper").next_run_time)
                            if scheduler.running else None
            },
            "rss_news": {
                **_status["news"],
                "next_run": str(scheduler.get_job("rss_news").next_run_time)
                            if scheduler.running else None
            }
        }
    }