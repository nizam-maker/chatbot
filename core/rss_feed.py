# core/rss_feed.py
# ─────────────────────────────────────────────────────────────
#  Automotive RSS news feed ingestion
#  Fetches latest articles daily and ingests into
#  ChromaDB surat_khabar domain
# ─────────────────────────────────────────────────────────────

import feedparser
import httpx
from bs4 import BeautifulSoup
from core.ingest import ingest_text
from datetime import datetime, timedelta
import logging
import hashlib

logger = logging.getLogger(__name__)

# ── RSS feeds to monitor ─────────────────────────────────────
RSS_FEEDS = [
    {
        "name":   "Paul Tan",
        "url":    "https://paultan.org/feed/",
        "lang":   "en"
    },
    {
        "name":   "WapCar",
        "url":    "https://www.wapcar.my/news/rss",
        "lang":   "en"
    },
    {
        "name":   "CarList",
        "url":    "https://www.carlist.my/news/feed/",
        "lang":   "en"
    },
    {
        "name":   "Autoworld",
        "url":    "https://www.autoworld.com.my/feed/",
        "lang":   "en"
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Only fetch articles from the last N days
MAX_AGE_DAYS = 1


def _article_id(url: str) -> str:
    """Generate a stable doc_id from article URL."""
    return "rss_" + hashlib.md5(url.encode()).hexdigest()[:12]


def _fetch_article_text(url: str) -> str:
    """Fetch full article text from a URL."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer",
                          "header", "aside", "iframe"]):
            tag.decompose()

        # Try common article containers
        for selector in ["article", ".post-content", ".entry-content",
                          ".article-body", "main", ".content"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator="\n").strip()
                if len(text) > 200:
                    return text[:6000]

        # Fallback to body
        return soup.get_text(separator="\n").strip()[:6000]

    except Exception as e:
        logger.warning(f"[rss] Failed to fetch article {url}: {e}")
        return ""


def _is_recent(entry) -> bool:
    """Check if an RSS entry was published within MAX_AGE_DAYS."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import time
            pub_time = datetime(*entry.published_parsed[:6])
            return datetime.utcnow() - pub_time < timedelta(days=MAX_AGE_DAYS)
    except Exception:
        pass
    return True  # include if we can't determine age


def _is_automotive_relevant(title: str) -> bool:
    """Basic keyword filter — only ingest automotive content."""
    keywords = [
        "kereta", "car", "suv", "sedan", "hatchback", "mpv",
        "proton", "perodua", "honda", "toyota", "mazda", "bmw",
        "mercedes", "hyundai", "kia", "mitsubishi", "nissan",
        "price", "harga", "launch", "review", "specs", "rebate",
        "loan", "pinjaman", "test drive", "booking", "ev",
        "hybrid", "electric", "fuel", "minyak", "enjin", "engine"
    ]
    title_lower = title.lower()
    return any(kw in title_lower for kw in keywords)


def fetch_news(tenant_id: str = "laman_auto") -> dict:
    """
    Fetch latest automotive news from all RSS feeds
    and ingest into ChromaDB surat_khabar domain.
    Returns a summary of results.
    """
    results = {"ingested": [], "skipped": [], "failed": []}

    for feed_cfg in RSS_FEEDS:
        feed_name = feed_cfg["name"]
        feed_url  = feed_cfg["url"]

        logger.info(f"[rss] Fetching {feed_name} — {feed_url}")

        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            logger.warning(f"[rss] Failed to parse feed {feed_url}: {e}")
            results["failed"].append(feed_name)
            continue

        for entry in feed.entries[:10]:  # max 10 articles per feed
            title = getattr(entry, "title", "")
            url   = getattr(entry, "link",  "")

            if not url:
                continue

            # Skip if not recent
            if not _is_recent(entry):
                results["skipped"].append(title[:50])
                continue

            # Skip if not automotive relevant
            if not _is_automotive_relevant(title):
                results["skipped"].append(title[:50])
                continue

            # Fetch full article
            summary = getattr(entry, "summary", "")
            text    = _fetch_article_text(url)

            if not text and not summary:
                results["skipped"].append(title[:50])
                continue

            # Combine title + summary + full text
            full_content = f"{title}\n\n{summary}\n\n{text}".strip()

            doc_id = _article_id(url)
            try:
                ingest_text(
                    text      = full_content,
                    doc_id    = doc_id,
                    tenant_id = tenant_id,
                    domain    = "surat_khabar",
                    meta      = {
                        "title":  title,
                        "source": url,
                        "feed":   feed_name,
                        "type":   "news_article",
                        "date":   datetime.utcnow().isoformat()
                    }
                )
                results["ingested"].append(title[:60])
                logger.info(f"[rss] ✓ {title[:60]}")

            except Exception as e:
                logger.error(f"[rss] Ingest failed: {e}")
                results["failed"].append(title[:50])

    logger.info(
        f"[rss] Done — "
        f"{len(results['ingested'])} ingested, "
        f"{len(results['skipped'])} skipped, "
        f"{len(results['failed'])} failed"
    )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = fetch_news()
    print(f"\nIngested: {len(r['ingested'])}")
    print(f"Skipped:  {len(r['skipped'])}")
    print(f"Failed:   {len(r['failed'])}")