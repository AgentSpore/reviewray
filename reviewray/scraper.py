"""Platform scrapers for ReviewRay.

Supports: Amazon (US/UK/DE/FR/…), Wildberries.
Each scraper returns a raw dict with product_name, total_reviews, reviews[].

Strategy:
  - Amazon: scrape main product page (/dp/) — review pages return captcha.
  - Wildberries: scrape HTML product page — old JSON API (card.wb.ru) is dead.
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
# Dispatch
# ---------------------------------------------------------------------------

def scrape(url: str) -> dict:
    platform = detect_platform(url)
    if platform == Platform.amazon:
        return scrape_amazon(url)
    elif platform == Platform.wildberries:
        return scrape_wildberries(url)
    else:
        raise ValueError(f"Platform not supported yet: {url}")
