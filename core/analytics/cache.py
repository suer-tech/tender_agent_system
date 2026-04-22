"""Предрасчёт bench_cache для быстрой работы в карточке тендера.

Идея: для каждой комбинации (OKPD2_prefix × region × period_months) считаем
агрегаты заранее. В рантайме `apps/web/chat_agent.py` делает один SELECT
вместо тяжёлого JOIN+агрегации.

Пересчитывать после каждой дозаливки данных — `refresh_bench_cache()` удаляет
старые строки и пересчитывает с нуля (быстрее, чем инкрементально).

Гранулярность:
  - okpd2_prefix: 2-значный (62, 35, 80, ...) и 4-значный (62.01, 80.10, ...)
  - region_code: все 10 регионов из TOP10 + '' (вся выборка)
  - period_months: 3, 6, 12
"""
from __future__ import annotations

from datetime import date, timedelta

from ..storage import eis_analytics
from ._common import percentile


def refresh_bench_cache(period_months_set=(3, 6, 12)) -> dict:
    """Пересчитать всю таблицу bench_cache. Возвращает счётчики."""
    stats = {"rows_written": 0, "combos_checked": 0}

    with eis_analytics.conn() as c:
        # Чищу кэш
        c.execute("DELETE FROM bench_cache")

        # Собираем уникальные (okpd2_prefix_2, okpd2_prefix_4) из contract_items
        prefixes: set[str] = set()
        for (code,) in c.execute(
            "SELECT DISTINCT okpd2_code FROM contract_items WHERE okpd2_code IS NOT NULL"
        ):
            if not code:
                continue
            parts = code.split(".")
            if len(parts) >= 1 and len(parts[0]) >= 2:
                prefixes.add(parts[0][:2])
            if len(parts) >= 2:
                prefixes.add(".".join(parts[:2]))

        # Регионы: все те, что у нас встречаются в contracts.customer_region
        regions = [""] + [r["customer_region"] for r in c.execute(
            "SELECT DISTINCT customer_region FROM contracts WHERE customer_region IS NOT NULL"
        ).fetchall()]

        today = date.today()

        for months in period_months_set:
            cutoff = (today - timedelta(days=months * 30)).isoformat()
            for prefix in sorted(prefixes):
                like = prefix + "%"
                for region in regions:
                    stats["combos_checked"] += 1

                    region_sql = "1=1"
                    region_params: list = []
                    if region:
                        region_sql = "c.customer_region = ?"
                        region_params = [region]

                    rows = c.execute(f"""
                        SELECT DISTINCT c.reg_num, c.contract_price, n.max_price
                        FROM contracts c
                        JOIN contract_items ci ON ci.reg_num = c.reg_num
                        LEFT JOIN notices n ON n.reg_number = c.purchase_number
                        WHERE ci.okpd2_code LIKE ?
                          AND c.sign_date >= ?
                          AND c.contract_price IS NOT NULL
                          AND {region_sql}
                    """, [like, cutoff] + region_params).fetchall()

                    if not rows:
                        continue

                    nmck = [r["max_price"] for r in rows if r["max_price"]]
                    final = [r["contract_price"] for r in rows if r["contract_price"]]
                    discounts = [
                        100.0 * (1 - r["contract_price"] / r["max_price"])
                        for r in rows
                        if r["max_price"] and r["contract_price"] and r["max_price"] > 0
                    ]

                    c.execute("""
                        INSERT INTO bench_cache
                        (okpd2_prefix, region_code, period_months, sample_size,
                         nmck_median, nmck_p25, nmck_p75,
                         final_price_median, final_price_p25, final_price_p75,
                         discount_pct_median, discount_pct_p25, discount_pct_p75,
                         contracts_with_discount)
                        VALUES (?,?,?,?, ?,?,?, ?,?,?, ?,?,?, ?)
                    """, (
                        prefix, region, months, len(rows),
                        percentile(nmck, 50), percentile(nmck, 25), percentile(nmck, 75),
                        percentile(final, 50), percentile(final, 25), percentile(final, 75),
                        percentile(discounts, 50), percentile(discounts, 25), percentile(discounts, 75),
                        len(discounts),
                    ))
                    stats["rows_written"] += 1

    return stats


def bench_from_cache(okpd2_prefix: str, region_code: str = "",
                     period_months: int = 12) -> dict | None:
    """Быстрая выборка из bench_cache. None если нет записи."""
    if not okpd2_prefix:
        return None
    # Пробуем сначала точный префикс, потом сокращённый (2 символа)
    with eis_analytics.conn() as c:
        for prefix in (okpd2_prefix, okpd2_prefix[:2]):
            row = c.execute("""
                SELECT * FROM bench_cache
                WHERE okpd2_prefix = ? AND region_code = ? AND period_months = ?
            """, (prefix, region_code or "", period_months)).fetchone()
            if row:
                return dict(row)
    return None
