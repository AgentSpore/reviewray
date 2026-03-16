"""Platform scrapers for ReviewRay.

Supports: Amazon (US/UK/DE), Wildberries.
Each scraper returns a raw dict with product_name, total_reviews, reviews[].
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
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
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


# ---------------------------------------------------------------------------
# Amazon
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


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    time.sleep(random.uniform(0.5, 1.2))
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def scrape_amazon(url: str) -> dict:
    asin = _extract_asin(url)
    if not asin:
        raise ValueError(f"Cannot extract ASIN from URL: {url}")

    # Determine base domain
    m = re.search(r"amazon(\.[a-z.]+)", url, re.I)
    domain = "amazon.com" if not m else "amazon" + m.group(1)

    reviews_url = f"https://www.{domain}/product-reviews/{asin}?pageNumber=1&sortBy=recent&reviewerType=all_reviews"

    try:
        html = _fetch_html(reviews_url)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Amazon reviews: {e}")

    # Product name
    product_name = None
    m = re.search(r'<a[^>]+id="product-link"[^>]*>([^<]+)</a>', html)
    if not m:
        m = re.search(r'"asin_title"\s*:\s*"([^"]+)"', html)
    if m:
        product_name = m.group(1).strip()

    # Total review count
    total_reviews = 0
    m = re.search(r'([\d,]+)\s+(?:global\s+)?ratings?', html, re.I)
    if m:
        total_reviews = int(m.group(1).replace(",", ""))

    # Rating histogram: 5★ → 1★ percentages
    histogram = {}
    for star in range(1, 6):
        pat = rf'{star}\s+star[^%]*?(\d+)%'
        mm = re.search(pat, html, re.I)
        if mm:
            histogram[star] = int(mm.group(1))

    # Individual reviews
    reviews = []
    # Pattern: review blocks
    review_blocks = re.findall(
        r'data-hook="review-body".*?<span[^>]*>(.*?)</span>',
        html, re.DOTALL
    )
    # Stars for each review
    star_matches = re.findall(
        r'class="a-icon-alt">\s*([\d.]+) out of 5 stars',
        html
    )
    # Verified purchase flags
    verified_matches = re.findall(
        r'data-hook="avp-badge"[^>]*>([^<]*Verified[^<]*)<',
        html, re.I
    )
    # Dates
    date_matches = re.findall(
        r'data-hook="review-date"[^>]*>\s*Reviewed[^o]*on ([^<]+)<',
        html
    )
    # Reviewer names
    name_matches = re.findall(
        r'class="a-profile-name">([^<]+)</span>',
        html
    )

    for i, block in enumerate(review_blocks[:20]):
        text = re.sub(r"<[^>]+>", "", block).strip()
        reviews.append({
            "text": text[:500],
            "stars": float(star_matches[i]) if i < len(star_matches) else None,
            "verified": i < len(verified_matches),
            "date": date_matches[i].strip() if i < len(date_matches) else None,
            "reviewer": name_matches[i].strip() if i < len(name_matches) else None,
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
# Wildberries (public API)
# ---------------------------------------------------------------------------

def _wb_extract_article(url: str) -> Optional[str]:
    # https://www.wildberries.ru/catalog/123456789/detail.aspx
    m = re.search(r"/catalog/(\d+)/", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&](?:nm|id)=(\d+)", url)
    if m:
        return m.group(1)
    # Bare number in path
    m = re.search(r"/(\d{6,10})(?:/|$)", url)
    if m:
        return m.group(1)
    return None


def _wb_vol_host(nm: int) -> str:
    """Wildberries CDN shard logic."""
    vol = nm // 100000
    if vol <= 143:
        return "01"
    elif vol <= 287:
        return "02"
    elif vol <= 431:
        return "03"
    elif vol <= 719:
        return "04"
    elif vol <= 1007:
        return "05"
    elif vol <= 1061:
        return "06"
    elif vol <= 1115:
        return "07"
    elif vol <= 1169:
        return "08"
    elif vol <= 1313:
        return "09"
    elif vol <= 1601:
        return "10"
    else:
        return "11"


def scrape_wildberries(url: str) -> dict:
    article = _wb_extract_article(url)
    if not article:
        raise ValueError(f"Cannot extract article from WB URL: {url}")

    nm = int(article)

    # Fetch product card
    card_url = (
        f"https://card.wb.ru/cards/v1/detail"
        f"?appType=1&curr=rub&dest=-1257786&nm={nm}"
    )
    req = urllib.request.Request(
        card_url,
        headers={"User-Agent": "RedditScoutAgent/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            card_data = json.loads(resp.read())
    except Exception as e:
        raise RuntimeError(f"WB card API failed: {e}")

    products = card_data.get("data", {}).get("products", [])
    if not products:
        raise RuntimeError("WB: product not found")

    product = products[0]
    product_name = product.get("name", f"WB #{nm}")
    total_reviews = product.get("feedbacks", 0)
    rating = product.get("rating", 0)
    imt_id = product.get("id", nm)

    # Fetch reviews
    reviews_url = (
        f"https://feedbacks1.wb.ru/feedbacks/v1/{imt_id}"
        f"?take=30&skip=0&sort=byRating"
    )
    reviews = []
    histogram = {}
    try:
        req2 = urllib.request.Request(
            reviews_url,
            headers={"User-Agent": "RedditScoutAgent/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            fb_data = json.loads(resp2.read())

        feedbacks = fb_data.get("feedbacks", [])
        star_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for fb in feedbacks:
            stars = fb.get("productValuation", 0)
            if 1 <= stars <= 5:
                star_counts[stars] = star_counts.get(stars, 0) + 1
            reviews.append({
                "text": fb.get("text", "")[:500],
                "stars": stars,
                "verified": True,  # WB feedbacks are purchase-verified
                "date": fb.get("createdDate", "")[:10],
                "reviewer": fb.get("wbUserDetails", {}).get("name", ""),
            })

        if feedbacks:
            total = sum(star_counts.values()) or 1
            histogram = {k: round(v * 100 / total) for k, v in star_counts.items()}
    except Exception:
        pass  # Proceed with what we have from card API

    return {
        "platform": "wildberries",
        "product_name": product_name,
        "total_reviews": total_reviews,
        "avg_rating": rating,
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
