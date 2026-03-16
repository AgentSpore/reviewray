"""Core analysis engine — computes Trust Score from raw scraped data."""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from typing import Optional

from .models import Signal, RiskLevel


# ---------------------------------------------------------------------------
# Individual signal scorers
# ---------------------------------------------------------------------------

def signal_rating_distribution(histogram: dict, total: int) -> Signal:
    """Healthy distribution has reviews across all star levels."""
    if not histogram or total < 5:
        return Signal(
            name="rating_distribution",
            description="Распределение оценок",
            score=0.5,
            weight=0.25,
            details="Недостаточно данных для анализа.",
        )

    pct_5 = histogram.get(5, 0)
    pct_1 = histogram.get(1, 0)
    pct_2 = histogram.get(2, 0)

    # Suspicion: >90% fives + near-zero negatives
    if pct_5 >= 90 and (pct_1 + pct_2) <= 2:
        score = 0.1
        details = f"⚠️ {pct_5}% пятёрок, почти нет негативных отзывов — аномально."
    elif pct_5 >= 80 and (pct_1 + pct_2) <= 5:
        score = 0.35
        details = f"Высокая доля пятёрок ({pct_5}%), мало критики ({pct_1+pct_2}%)."
    elif pct_5 >= 70:
        score = 0.6
        details = f"Слегка завышенная доля пятёрок ({pct_5}%)."
    else:
        score = 0.9
        details = f"Распределение выглядит естественным (5★: {pct_5}%, 1-2★: {pct_1+pct_2}%)."

    return Signal(
        name="rating_distribution",
        description="Распределение оценок",
        score=score,
        weight=0.25,
        details=details,
    )


def signal_review_velocity(reviews: list[dict]) -> Signal:
    """Burst of reviews in a short window is suspicious."""
    dates = []
    for r in reviews:
        d = r.get("date")
        if not d:
            continue
        # Try multiple date formats
        for fmt in ("%B %d, %Y", "%d %B %Y", "%Y-%m-%d", "%d.%m.%Y"):
            try:
                dates.append(datetime.strptime(d.strip(), fmt))
                break
            except ValueError:
                continue

    if len(dates) < 3:
        return Signal(
            name="review_velocity",
            description="Всплески публикаций",
            score=0.6,
            weight=0.20,
            details="Недостаточно дат для анализа скорости.",
        )

    dates.sort()
    # Find max count within any 7-day window
    max_in_window = 1
    for i, d in enumerate(dates):
        window = [x for x in dates if 0 <= (x - d).days <= 7]
        max_in_window = max(max_in_window, len(window))

    ratio = max_in_window / len(dates)

    if ratio >= 0.7:
        score = 0.1
        details = f"⚠️ {max_in_window} из {len(dates)} отзывов вышли в течение 7 дней — подозрительный всплеск."
    elif ratio >= 0.5:
        score = 0.4
        details = f"{max_in_window} из {len(dates)} отзывов за 7 дней — умеренный всплеск."
    else:
        score = 0.85
        details = f"Отзывы распределены равномерно во времени."

    return Signal(
        name="review_velocity",
        description="Всплески публикаций",
        score=score,
        weight=0.20,
        details=details,
    )


def signal_verified_ratio(reviews: list[dict]) -> Signal:
    """Low verified purchase ratio indicates potential fake reviews."""
    if not reviews:
        return Signal(
            name="verified_ratio",
            description="Доля подтверждённых покупок",
            score=0.5,
            weight=0.15,
            details="Нет данных о подтверждённых покупках.",
        )

    verified = sum(1 for r in reviews if r.get("verified"))
    ratio = verified / len(reviews)

    if ratio < 0.3:
        score = 0.15
        details = f"⚠️ Только {round(ratio*100)}% отзывов — от подтверждённых покупателей."
    elif ratio < 0.6:
        score = 0.5
        details = f"{round(ratio*100)}% подтверждённых покупок — ниже среднего."
    else:
        score = 0.9
        details = f"{round(ratio*100)}% отзывов от реальных покупателей — норма."

    return Signal(
        name="verified_ratio",
        description="Доля подтверждённых покупок",
        score=score,
        weight=0.15,
        details=details,
    )


def _text_to_shingles(text: str, k: int = 4) -> set[str]:
    """Character k-shingles for similarity."""
    text = re.sub(r"\s+", " ", text.lower().strip())
    return {text[i:i+k] for i in range(len(text) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def signal_text_similarity(reviews: list[dict]) -> Signal:
    """High average pairwise similarity = template / copy-paste reviews."""
    texts = [r["text"] for r in reviews if r.get("text") and len(r["text"]) > 30]
    if len(texts) < 3:
        return Signal(
            name="text_similarity",
            description="Уникальность текстов отзывов",
            score=0.6,
            weight=0.20,
            details="Мало текстов для сравнения.",
        )

    shingles = [_text_to_shingles(t) for t in texts[:15]]
    pairs = []
    for i in range(len(shingles)):
        for j in range(i + 1, len(shingles)):
            pairs.append(_jaccard(shingles[i], shingles[j]))

    avg_sim = sum(pairs) / len(pairs) if pairs else 0

    if avg_sim > 0.4:
        score = 0.1
        details = f"⚠️ Среднее сходство текстов {round(avg_sim*100)}% — возможен шаблон или копипаст."
    elif avg_sim > 0.25:
        score = 0.4
        details = f"Умеренное сходство текстов ({round(avg_sim*100)}%)."
    else:
        score = 0.9
        details = f"Тексты отзывов уникальны (сходство {round(avg_sim*100)}%)."

    return Signal(
        name="text_similarity",
        description="Уникальность текстов отзывов",
        score=score,
        weight=0.20,
        details=details,
    )


def signal_reviewer_diversity(reviews: list[dict]) -> Signal:
    """Repeated reviewer names or very generic names are a red flag."""
    names = [r.get("reviewer", "") for r in reviews if r.get("reviewer")]
    if len(names) < 3:
        return Signal(
            name="reviewer_diversity",
            description="Разнообразие рецензентов",
            score=0.6,
            weight=0.20,
            details="Мало данных о рецензентах.",
        )

    counts = Counter(names)
    duplicates = sum(1 for c in counts.values() if c > 1)
    dup_ratio = duplicates / len(names)

    # Check for suspiciously generic names
    generic = sum(1 for n in names if re.match(
        r"^(customer|amazon customer|user|покупатель|клиент|аноним|аноним\d+)$",
        n.strip().lower()
    ))
    generic_ratio = generic / len(names)

    if dup_ratio > 0.3 or generic_ratio > 0.5:
        score = 0.15
        details = f"⚠️ {round(dup_ratio*100)}% дублирующихся имён, {round(generic_ratio*100)}% анонимов."
    elif dup_ratio > 0.1 or generic_ratio > 0.25:
        score = 0.5
        details = f"Умеренно однообразные имена рецензентов."
    else:
        score = 0.85
        details = f"Рецензенты разнообразны — признак органических отзывов."

    return Signal(
        name="reviewer_diversity",
        description="Разнообразие рецензентов",
        score=score,
        weight=0.20,
        details=details,
    )


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def compute_trust_score(signals: list[Signal]) -> int:
    """Weighted average → 0–100 integer."""
    total_weight = sum(s.weight for s in signals)
    if total_weight == 0:
        return 50
    weighted = sum(s.score * s.weight for s in signals)
    raw = weighted / total_weight          # 0.0–1.0
    # Apply slight non-linear compression: reward high scores less
    compressed = raw ** 0.85
    return max(0, min(100, round(compressed * 100)))


def risk_level(score: int) -> RiskLevel:
    if score >= 75:
        return RiskLevel.low
    elif score >= 45:
        return RiskLevel.medium
    elif score >= 20:
        return RiskLevel.high
    return RiskLevel.critical


def verdict(score: int, level: RiskLevel, product_name: Optional[str]) -> str:
    name = product_name or "Этот товар"
    if level == RiskLevel.low:
        return (
            f'"{name}" — отзывы выглядят органично. '
            f"Trust Score {score}/100: признаки манипуляций не обнаружены."
        )
    elif level == RiskLevel.medium:
        return (
            f'"{name}" — есть отдельные подозрительные сигналы. '
            f"Trust Score {score}/100: рекомендуем изучить отзывы вручную."
        )
    elif level == RiskLevel.high:
        return (
            f'"{name}" — высокая вероятность накрутки. '
            f"Trust Score {score}/100: несколько тревожных сигналов."
        )
    return (
        f'"{name}" — критические признаки накрутки. '
        f"Trust Score {score}/100: не доверяйте рейтингу этого товара."
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze(scraped: dict) -> dict:
    """Run all signals on scraped data, return analysis dict."""
    reviews = scraped.get("reviews", [])
    histogram = scraped.get("histogram", {})
    total = scraped.get("total_reviews", len(reviews))

    signals: list[Signal] = [
        signal_rating_distribution(histogram, total),
        signal_review_velocity(reviews),
        signal_verified_ratio(reviews),
        signal_text_similarity(reviews),
        signal_reviewer_diversity(reviews),
    ]

    score = compute_trust_score(signals)
    level = risk_level(score)
    v = verdict(score, level, scraped.get("product_name"))

    return {
        "product_name": scraped.get("product_name"),
        "total_reviews": total,
        "trust_score": score,
        "risk_level": level,
        "signals": signals,
        "verdict": v,
    }
