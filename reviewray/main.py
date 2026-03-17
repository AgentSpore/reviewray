"""ReviewRay — AI-powered fake review detector.

FastAPI application entry point.
"""
from __future__ import annotations

import pathlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .models import (
    AnalysisRequest,
    AnalysisResponse,
    HealthResponse,
    Platform,
)
from .scraper import scrape, detect_platform
from .analyzer import analyze

STATIC_DIR = pathlib.Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ReviewRay",
    description=(
        "Paste any product URL — get a Trust Score 0–100 showing "
        "whether reviews are organic or manipulated. "
        "Supports Amazon, Wildberries, Yandex Maps, Ozon."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version="1.0.0")


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_url(body: AnalysisRequest):
    """Analyze a product URL for fake/manipulated reviews."""
    url = body.url
    platform = detect_platform(url)

    if platform == Platform.unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                "Платформа не поддерживается. "
                "Поддерживаются: Amazon (amazon.com/.co.uk/.de и др.), "
                "Wildberries (wildberries.ru), "
                "Яндекс.Карты (yandex.ru/maps/org/...), "
                "Ozon (ozon.ru/product/...)."
            ),
        )

    try:
        scraped = await scrape(url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка скрапинга: {e}")

    result = analyze(scraped)

    return AnalysisResponse(
        url=url,
        platform=platform,
        product_name=result["product_name"],
        total_reviews=result["total_reviews"],
        trust_score=result["trust_score"],
        risk_level=result["risk_level"],
        signals=result["signals"],
        verdict=result["verdict"],
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        warning=scraped.get("warning"),
    )


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index():
    html = STATIC_DIR / "index.html"
    if html.exists():
        return FileResponse(str(html))
    return {"message": "ReviewRay API — see /docs"}
