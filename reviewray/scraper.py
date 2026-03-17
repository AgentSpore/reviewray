"""Platform scrapers for ReviewRay.

Supports: Amazon, Wildberries, Yandex Maps, Ozon.
Each scraper returns a raw dict with product_name, total_reviews, reviews[].

Strategy:
  - Amazon: scrape main product page (/dp/) — review pages return captcha.
  - Wildberries: search API + feedbacks API (old card.wb.ru is dead). Rate-limited.
  - Yandex Maps: SSR page with review data embedded in HTML.
  - Ozon: requires Playwright (headless browser) — heavy anti-bot protection.
"""
from __future__ import annotations

import re
import time
import random
import urllib.request
import urllib.parse
import json
from typing import Optional

from .models import Platform


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def detect_platform(url: str) -> Platform:
    url_lower = url.lower()
    if "amazon." in url_lower:
        return Platform.amazon
    if "wildberries.ru" in url_lower or "wb.ru" in url_lower:
        return Platform.wildberries
    if "yandex.ru/maps" in url_lower or "yandex.com/maps" in url_lower:
        return Platform.yandex_maps
    if "ozon.ru" in url_lower:
        return Platform.ozon
    if "google.com/maps" in url_lower or "maps.google" in url_lower or "goo.gl/maps" in url_lower:
        return Platform.google_maps
    return Platform.unknown


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    time.sleep(random.uniform(0.3, 0.8))
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Amazon — scrape /dp/ product page (review page gives captcha)
# ---------------------------------------------------------------------------

def _extract_asin(url: str) -> Optional[str]:
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"[?&]asin=([A-Z0-9]{10})",
    ]
    for p in patterns:
        m = re.search(p, url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def scrape_amazon(url: str) -> dict:
    asin = _extract_asin(url)
    if not asin:
        raise ValueError(f"Cannot extract ASIN from URL: {url}")

    m = re.search(r"amazon(\.[a-z.]+)", url, re.I)
    domain = "amazon.com" if not m else "amazon" + m.group(1)

    product_url = f"https://www.{domain}/dp/{asin}"

    try:
        html = _fetch_html(product_url)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Amazon product page: {e}")

    # --- Product name ---
    product_name = None
    m = re.search(r'id="productTitle"[^>]*>\s*(.*?)\s*</span>', html, re.DOTALL)
    if m:
        product_name = re.sub(r"\s+", " ", m.group(1)).strip()

    # --- Total ratings ---
    total_reviews = 0
    m = re.search(r'([\d,]+)\s+(?:global\s+)?ratings?', html, re.I)
    if m:
        total_reviews = int(m.group(1).replace(",", ""))

    # --- Histogram: star → percentage via aria-valuenow ---
    histogram = {}
    rows = re.findall(
        r'(\d)\s+star.*?aria-valuenow="(\d+)"',
        html, re.DOTALL | re.I
    )
    for star_str, pct_str in rows:
        star = int(star_str)
        if 1 <= star <= 5:
            histogram[star] = int(pct_str)

    # --- Reviews on product page (top 3-8 reviews) ---
    reviews = []
    review_blocks = re.findall(
        r'<span data-hook="review-body"[^>]*>.*?<span[^>]*>(.*?)</span>',
        html, re.DOTALL
    )
    star_matches = re.findall(
        r'<i data-hook="review-star-rating"[^>]*>.*?<span[^>]*>([\d.]+) out of',
        html, re.DOTALL
    )
    name_matches = re.findall(
        r'<span class="a-profile-name"[^>]*>([^<]+)</span>',
        html
    )
    date_matches = re.findall(
        r'data-hook="review-date"[^>]*>[^<]*on\s+([^<]+)<',
        html, re.I
    )
    verified_matches = re.findall(
        r'data-hook="avp-badge"',
        html
    )

    for i, block in enumerate(review_blocks[:10]):
        text = re.sub(r"<[^>]+>", "", block).strip()
        text = text.replace("&#39;", "'").replace("&amp;", "&").replace("&quot;", '"')
        reviews.append({
            "text": text[:500],
            "stars": float(star_matches[i]) if i < len(star_matches) else None,
            "verified": i < len(verified_matches),
            "date": date_matches[i].strip() if i < len(date_matches) else None,
            "reviewer": name_matches[i + 1].strip() if (i + 1) < len(name_matches) else None,
        })

    return {
        "platform": "amazon",
        "product_name": product_name or f"Amazon ASIN {asin}",
        "total_reviews": total_reviews,
        "histogram": histogram,
        "reviews": reviews,
        "asin": asin,
    }


# ---------------------------------------------------------------------------
# Wildberries — HTML scraping (card.wb.ru JSON API is dead since 2026)
# ---------------------------------------------------------------------------

def _wb_extract_article(url: str) -> Optional[str]:
    m = re.search(r"/catalog/(\d+)/", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&](?:nm|id)=(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{6,10})(?:/|$)", url)
    if m:
        return m.group(1)
    return None


def scrape_wildberries(url: str) -> dict:
    article = _wb_extract_article(url)
    if not article:
        raise ValueError(f"Cannot extract article from WB URL: {url}")

    nm = int(article)

    product_name = f"WB #{nm}"
    total_reviews = 0
    avg_rating = 0.0
    reviews = []
    histogram = {}

    # --- Step 1: Try search API to get product info + real imtId ---
    search_url = (
        f"https://search.wb.ru/exactmatch/ru/common/v7/search"
        f"?appType=1&curr=rub&dest=-1257786&query={nm}&resultset=catalog"
    )
    real_id = nm
    try:
        req = urllib.request.Request(search_url, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "*/*",
            "Origin": "https://www.wildberries.ru",
            "Referer": "https://www.wildberries.ru/",
        })
        time.sleep(random.uniform(0.5, 1.0))
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            try:
                search_data = json.loads(raw)
            except Exception:
                import gzip
                search_data = json.loads(gzip.decompress(raw))

        products = search_data.get("data", {}).get("products", [])
        if products:
            p = products[0]
            product_name = p.get("name", product_name)
            total_reviews = p.get("feedbacks", 0)
            avg_rating = p.get("rating", 0.0)
            real_id = p.get("id", nm)
    except Exception:
        pass  # Will try feedbacks API with nm as fallback

    # --- Step 2: Try feedbacks API (v2 with real_id, then v1 with nm) ---
    for fb_id, ver in [(real_id, "v2"), (nm, "v2"), (real_id, "v1"), (nm, "v1")]:
        if reviews:
            break
        feedbacks_url = f"https://feedbacks1.wb.ru/feedbacks/{ver}/{fb_id}"
        try:
            req = urllib.request.Request(
                feedbacks_url,
                headers={
                    "User-Agent": HEADERS["User-Agent"],
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            time.sleep(random.uniform(0.3, 0.6))
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                try:
                    fb_data = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    import gzip
                    fb_data = json.loads(gzip.decompress(raw))

            feedbacks = fb_data.get("feedbacks") or []
            if not feedbacks:
                continue

            # Update product info from feedbacks response if search failed
            if fb_data.get("valuation"):
                avg_rating = avg_rating or float(fb_data["valuation"])
            if fb_data.get("feedbackCount"):
                total_reviews = total_reviews or fb_data["feedbackCount"]

            # Extract distribution from API if available
            vd = fb_data.get("valuationDistribution") or {}
            if vd:
                total_vd = sum(int(v) for v in vd.values()) or 1
                histogram = {int(k): round(int(v) * 100 / total_vd) for k, v in vd.items()}

            star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for fb in feedbacks:
                stars = fb.get("productValuation", 0)
                if 1 <= stars <= 5:
                    star_counts[stars] += 1
                reviews.append({
                    "text": fb.get("text", "")[:500],
                    "stars": stars,
                    "verified": True,
                    "date": fb.get("createdDate", "")[:10],
                    "reviewer": fb.get("wbUserDetails", {}).get("name", ""),
                })

            if not histogram and feedbacks:
                total_fb = sum(star_counts.values()) or 1
                histogram = {k: round(v * 100 / total_fb) for k, v in star_counts.items()}

        except Exception:
            continue

    return {
        "platform": "wildberries",
        "product_name": product_name or f"WB #{nm}",
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "histogram": histogram,
        "reviews": reviews,
        "article": nm,
    }


# ---------------------------------------------------------------------------
# Yandex Maps — scrape /org/ reviews page (SSR includes review data)
# ---------------------------------------------------------------------------

def _ym_extract_org_id(url: str) -> Optional[str]:
    m = re.search(r'/org/[^/]+/(\d+)', url)
    if m:
        return m.group(1)
    return None


def scrape_yandex_maps(url: str) -> dict:
    org_id = _ym_extract_org_id(url)
    if not org_id:
        raise ValueError(f"Cannot extract org ID from Yandex Maps URL: {url}")

    # Ensure we're hitting the reviews page for maximum data
    base_url = re.sub(r'(/\d+)/.*', r'\1/', url)
    reviews_url = base_url + "reviews/"

    try:
        html = _fetch_html(reviews_url)
    except Exception as e:
        # Fallback: try the org page itself
        try:
            html = _fetch_html(base_url)
        except Exception as e2:
            raise RuntimeError(f"Failed to fetch Yandex Maps page: {e2}")

    # --- Org name ---
    org_name = None
    m = re.search(r'<title>(?:Отзывы о «|)([^<|–"]+)', html)
    if m:
        org_name = m.group(1).replace("»", "").strip()
    if not org_name:
        m = re.search(r'"orgName"\s*:\s*"([^"]+)"', html)
        if m:
            org_name = m.group(1).strip()

    # --- Rating + review count ---
    avg_rating = 0.0
    total_reviews = 0

    m = re.search(r'"rating"\s*:\s*([\d.]+)', html)
    if m:
        avg_rating = float(m.group(1))

    m = re.search(r'"reviewCount"\s*:\s*"?(\d+)"?', html)
    if m:
        total_reviews = int(m.group(1))

    # --- Rating distribution from individual review ratings ---
    all_ratings = re.findall(r'"rating"\s*:\s*(\d)\s*[,}]', html)
    star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in all_ratings:
        s = int(r)
        if 1 <= s <= 5:
            star_counts[s] += 1

    histogram = {}
    total_fb = sum(star_counts.values())
    if total_fb > 0:
        histogram = {k: round(v * 100 / total_fb) for k, v in star_counts.items()}

    # --- Review texts ---
    # Yandex Maps SSR includes review texts as "text":"..." fields
    # Filter out UI/system texts by length and content
    all_texts = re.findall(r'"text"\s*:\s*"([^"]{30,})"', html)
    # Filter out system/UI texts
    review_texts = [
        t for t in all_texts
        if not any(skip in t.lower() for skip in [
            "лента", "alice ai", "created by", "экспериментальный",
            "способ поиска", "облегчить поиск",
        ])
    ]

    # --- Review dates ---
    dates = re.findall(r'"updatedTime"\s*:\s*"([^"]+)"', html)

    # --- Build review objects ---
    reviews = []
    review_ids = re.findall(r'"reviewId"\s*:\s*"([^"]+)"', html)

    for i, text in enumerate(review_texts[:30]):
        # Unescape
        text = (text
                .replace("\\n", " ")
                .replace("\\u003c", "<")
                .replace("\\u003e", ">")
                .replace("\\u0026", "&")
                .replace("\\u0022", '"')
                .replace("\xa0", " "))
        text = re.sub(r"<[^>]+>", "", text).strip()

        reviews.append({
            "text": text[:500],
            "stars": int(all_ratings[i]) if i < len(all_ratings) else None,
            "verified": False,  # Yandex Maps doesn't expose verification
            "date": dates[i][:10] if i < len(dates) else None,
            "reviewer": "",
        })

    return {
        "platform": "yandex_maps",
        "product_name": org_name or f"Yandex Maps Org #{org_id}",
        "total_reviews": total_reviews or total_fb,
        "avg_rating": avg_rating,
        "histogram": histogram,
        "reviews": reviews,
        "org_id": org_id,
    }


# ---------------------------------------------------------------------------
# Ozon — requires Playwright (heavy anti-bot protection)
# ---------------------------------------------------------------------------

def _ozon_extract_product_id(url: str) -> Optional[str]:
    m = re.search(r'/product/[^/]*?(\d{5,15})/?', url)
    if m:
        return m.group(1)
    m = re.search(r'/product/(\d+)', url)
    if m:
        return m.group(1)
    return None


def scrape_ozon(url: str) -> dict:
    product_id = _ozon_extract_product_id(url)
    if not product_id:
        raise ValueError(f"Cannot extract product ID from Ozon URL: {url}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Ozon requires Playwright for scraping. "
            "Install: pip install playwright && playwright install chromium"
        )

    product_name = None
    total_reviews = 0
    avg_rating = 0.0
    histogram = {}
    reviews = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="ru-RU",
        )
        page = ctx.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            html = page.content()

            # --- Product name ---
            m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if m:
                product_name = m.group(1).strip()

            # --- JSON-LD ---
            ld_blocks = re.findall(
                r'type="application/ld\+json">(.*?)</script>', html, re.DOTALL
            )
            for block in ld_blocks:
                try:
                    data = json.loads(block)
                    if data.get("@type") == "Product":
                        product_name = product_name or data.get("name", "")
                        ar = data.get("aggregateRating", {})
                        if ar:
                            avg_rating = float(ar.get("ratingValue", 0))
                            total_reviews = int(ar.get("reviewCount", 0))
                        for rev in data.get("review", [])[:20]:
                            stars = None
                            rr = rev.get("reviewRating", {})
                            if rr:
                                stars = float(rr.get("ratingValue", 0))
                            reviews.append({
                                "text": rev.get("reviewBody", "")[:500],
                                "stars": stars,
                                "verified": True,
                                "date": rev.get("datePublished", ""),
                                "reviewer": rev.get("author", {}).get("name", ""),
                            })
                except (json.JSONDecodeError, KeyError):
                    continue

            # --- Fallback: regex patterns ---
            if not total_reviews:
                m = re.search(r'"reviewCount"\s*:\s*"?(\d+)"?', html)
                if m:
                    total_reviews = int(m.group(1))

            if not avg_rating:
                m = re.search(r'"ratingValue"\s*:\s*"?([\d.]+)"?', html)
                if m:
                    avg_rating = float(m.group(1))

            # --- Histogram from individual review ratings ---
            if reviews:
                star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                for r in reviews:
                    s = r.get("stars")
                    if s and 1 <= int(s) <= 5:
                        star_counts[int(s)] += 1
                total_fb = sum(star_counts.values()) or 1
                histogram = {k: round(v * 100 / total_fb) for k, v in star_counts.items()}

        finally:
            browser.close()

    return {
        "platform": "ozon",
        "product_name": product_name or f"Ozon #{product_id}",
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "histogram": histogram,
        "reviews": reviews,
        "product_id": product_id,
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

# Platform-specific warnings shown to users
PLATFORM_WARNINGS = {
    "wildberries": (
        "⚠️ Wildberries агрессивно ограничивает запросы (rate-limiting). "
        "Результат может быть неполным или недоступным. "
        "При ошибке попробуйте позже."
    ),
    "ozon": (
        "⚠️ Ozon использует тяжёлую anti-bot защиту. "
        "Анализ может занять 10-15 секунд. Требуется Playwright."
    ),
}


def scrape(url: str) -> dict:
    platform = detect_platform(url)
    if platform == Platform.amazon:
        result = scrape_amazon(url)
    elif platform == Platform.wildberries:
        result = scrape_wildberries(url)
    elif platform == Platform.yandex_maps:
        result = scrape_yandex_maps(url)
    elif platform == Platform.ozon:
        result = scrape_ozon(url)
    else:
        raise ValueError(f"Platform not supported yet: {url}")

    # Attach platform warning if applicable
    warning = PLATFORM_WARNINGS.get(result.get("platform"))
    if warning:
        result["warning"] = warning

    return result
