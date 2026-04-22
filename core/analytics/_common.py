"""Общие SQL-хелперы для аналитических запросов."""
from __future__ import annotations

from datetime import date, timedelta


MIN_SAMPLE = 10  # минимум контрактов для "enough_data=True"


def period_cutoff(months_back: int) -> str:
    """ISO-дата, раньше которой контракты не учитываем."""
    today = date.today()
    days = months_back * 30
    return (today - timedelta(days=days)).isoformat()


def percentile(values: list[float], p: float) -> float | None:
    """Простой расчёт перцентиля на отсортированном списке."""
    if not values:
        return None
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(vals) else f
    if f == c:
        return vals[f]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def okpd2_prefix_clause(prefix: str, col: str = "ci.okpd2_code") -> tuple[str, list]:
    """
    Вернуть SQL-фрагмент для `WHERE <col> LIKE ?` и параметры.
    prefix '62' → '62%', '62.01' → '62.01%', '62.01.12' → '62.01.12%'.
    """
    p = (prefix or "").strip()
    if not p:
        return "1=1", []
    return f"{col} LIKE ?", [p + "%"]
