# core/scraper.py
# ─────────────────────────────────────────────────────────────
#  Brand website scraper
#  Extracts latest car info from official brand websites
#  and ingests into ChromaDB car_specs domain
# ─────────────────────────────────────────────────────────────

import httpx
from bs4 import BeautifulSoup
from core.ingest import ingest_text
import logging

logger = logging.getLogger(__name__)

# ── Brand pages to scrape ────────────────────────────────────
# Each entry: (brand, model, url, css_selector_for_content)
BRAND_PAGES = [

    # Perodua — updated URL structure
    ("Perodua", "Axia",  "https://www.perodua.com.my/our-models/hatchback/axia.html",  "main"),
    ("Perodua", "Myvi",  "https://www.perodua.com.my/our-models/hatchback/myvi.html",  "main"),
    ("Perodua", "Bezza", "https://www.perodua.com.my/our-models/sedan/bezza.html",     "main"),
    ("Perodua", "Ativa", "https://www.perodua.com.my/our-models/suv/ativa.html",       "main"),
    ("Perodua", "Alza",  "https://www.perodua.com.my/our-models/mpv/alza.html",        "main"),

    # Proton
    ("Proton", "Saga", "https://www.proton.com/en-my/models/saga",  "article"),
    ("Proton", "X50",  "https://www.proton.com/en-my/models/x50",   "article"),
    ("Proton", "X70",  "https://www.proton.com/en-my/models/x70",   "article"),
    ("Proton", "S70",  "https://www.proton.com/en-my/models/s70",   "article"),

    # Honda
    ("Honda", "City",  "https://www.honda.com.my/city",  ".vehicle-details"),
    ("Honda", "HR-V",  "https://www.honda.com.my/hr-v",  ".vehicle-details"),
    ("Honda", "Civic", "https://www.honda.com.my/civic", ".vehicle-details"),

    # Toyota
    ("Toyota", "Vios",  "https://www.toyota.com.my/models/vios",  ".model-content"),
    ("Toyota", "Yaris", "https://www.toyota.com.my/models/yaris", ".model-content"),
    ("Toyota", "Veloz", "https://www.toyota.com.my/models/veloz", ".model-content"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _fetch_page(url: str) -> str | None:
    """Fetch a webpage and return raw HTML. Returns None on failure."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        logger.warning(f"[scraper] {url} returned {resp.status_code}")
        return None
    except Exception as e:
        logger.warning(f"[scraper] Failed to fetch {url}: {e}")
        return None


def _extract_text(html: str, selector: str) -> str:
    """Extract clean text from HTML using a CSS selector."""
    soup = BeautifulSoup(html, "html.parser")

    # Try the specific selector first
    content = soup.select_one(selector)
    if not content:
        # Fallback to body
        content = soup.find("body")
    if not content:
        return ""

    # Remove script, style, nav, footer noise
    for tag in content(["script", "style", "nav", "footer",
                         "header", "iframe", "noscript"]):
        tag.decompose()

    # Get clean text
    lines = [line.strip() for line in content.get_text(separator="\n").splitlines()]
    clean = "\n".join(line for line in lines if len(line) > 20)
    return clean[:8000]  # cap at 8000 chars per page


def scrape_brand_pages(tenant_id: str = "laman_auto") -> dict:
    """
    Scrape all brand pages and ingest into ChromaDB.
    Returns a summary of results.
    """
    results = {"success": [], "failed": []}

    for brand, model, url, selector in BRAND_PAGES:
        logger.info(f"[scraper] Scraping {brand} {model} — {url}")

        html = _fetch_page(url)
        if not html:
            results["failed"].append(f"{brand} {model}")
            continue

        text = _extract_text(html, selector)
        if len(text) < 100:
            logger.warning(f"[scraper] Too little text extracted from {url}")
            results["failed"].append(f"{brand} {model}")
            continue

        doc_id = f"web_{brand.lower()}_{model.lower().replace('-','')}"
        try:
            ingest_text(
                text      = text,
                doc_id    = doc_id,
                tenant_id = tenant_id,
                domain    = "car_specs",
                meta      = {
                    "brand":  brand,
                    "model":  model,
                    "source": url,
                    "type":   "web_scrape"
                }
            )
            results["success"].append(f"{brand} {model}")
            logger.info(f"[scraper] ✓ {brand} {model} ingested")
        except Exception as e:
            logger.error(f"[scraper] Ingest failed for {brand} {model}: {e}")
            results["failed"].append(f"{brand} {model}")

    logger.info(
        f"[scraper] Done — "
        f"{len(results['success'])} success, "
        f"{len(results['failed'])} failed"
    )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = scrape_brand_pages()
    print("Success:", r["success"])
    print("Failed: ", r["failed"])