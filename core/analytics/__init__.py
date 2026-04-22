"""Аналитический слой над витриной eis_analytics.db.

Все функции возвращают чистые данные (dict / list), без форматирования —
текстовые summary формируются в apps/ уже из этих данных.
"""
from .bench import bench_by_okpd2_region
from .risk import risk_by_inn
from .market import (
    market_overview, top_sectors, top_customers, top_suppliers,
    time_series_by_month,
)
from .okpd2_classifier import guess_okpd2
from .cache import refresh_bench_cache

__all__ = [
    "bench_by_okpd2_region", "risk_by_inn",
    "market_overview", "top_sectors", "top_customers", "top_suppliers",
    "time_series_by_month", "guess_okpd2", "refresh_bench_cache",
]
