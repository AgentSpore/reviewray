"""Domain models and Pydantic schemas for ReviewRay."""
from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


class Platform(str, Enum):
    amazon = "amazon"
    wildberries = "wildberries"
    yandex_maps = "yandex_maps"
    google_maps = "google_maps"
    unknown = "unknown"


class RiskLevel(str, Enum):
    low = "low"          # 75-100
    medium = "medium"    # 45-74
    high = "high"        # 20-44
    critical = "critical"  # 0-19


class Signal(BaseModel):
    name: str
    description: str
    score: float          # 0.0–1.0, 1.0 = perfectly clean
    weight: float         # importance weight
    details: Optional[str] = None


class AnalysisRequest(BaseModel):
    url: str
    comment: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        return v


class AnalysisResponse(BaseModel):
    url: str
    platform: Platform
    product_name: Optional[str]
    total_reviews: int
    trust_score: int          # 0–100
    risk_level: RiskLevel
    signals: list[Signal]
    verdict: str              # Human-readable summary
    analyzed_at: str
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
