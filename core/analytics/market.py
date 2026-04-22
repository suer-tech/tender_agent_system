"""Общерыночные срезы — для страницы /market."""
from __future__ import annotations

from collections import Counter
from ..storage import eis_analytics
from ._common import okpd2_prefix_clause


def _period_clause(from_date: str | None, to_date: str | None, col: str = "c.sign_date"):
    where = []
    params: list = []
    if from_date:
        where.append(f"{col} >= ?"); params.append(from_date)
    if to_date:
        where.append(f"{col} <= ?"); params.append(to_date)
    return (" AND ".join(where) if where else "1=1"), params


def market_overview(okpd2_prefix: str | None, region_code: str | None,
                    from_date: str, to_date: str) -> dict:
    """Обзор сегмента: объём, кол-во контрактов, средняя скидка, HHI."""
    okpd2_sql, okpd2_params = okpd2_prefix_clause(okpd2_prefix or "", "ci.okpd2_code")
    period_sql, period_params = _period_clause(from_date, to_date)
    region_sql = "1=1"
    region_params: list = []
    if region_code:
        region_sql = "c.customer_region = ?"; region_params = [region_code]

    with eis_analytics.conn() as c:
        # Основные метрики
        row = c.execute(f"""
            SELECT COUNT(DISTINCT c.reg_num) AS contracts_count,
                   COALESCE(SUM(DISTINCT c.contract_price), 0) AS total_sum,
                   AVG(DISTINCT c.contract_price) AS avg_price
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {period_sql} AND {region_sql}
        """, okpd2_params + period_params + region_params).fetchone()

        cust_cnt = c.execute(f"""
            SELECT COUNT(DISTINCT c.customer_inn) AS n
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {period_sql} AND {region_sql}
              AND c.customer_inn IS NOT NULL
        """, okpd2_params + period_params + region_params).fetchone()
        supp_cnt = c.execute(f"""
            SELECT COUNT(DISTINCT c.supplier_inn) AS n
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {period_sql} AND {region_sql}
              AND c.supplier_inn IS NOT NULL
        """, okpd2_params + period_params + region_params).fetchone()

        # Медианная скидка (где есть notice-связка)
        disc_rows = c.execute(f"""
            SELECT DISTINCT c.reg_num,
                   100.0 * (1 - c.contract_price * 1.0 / n.max_price) AS disc
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            JOIN notices n ON n.reg_number = c.purchase_number
            WHERE {okpd2_sql} AND {period_sql} AND {region_sql}
              AND n.max_price > 0 AND c.contract_price IS NOT NULL
        """, okpd2_params + period_params + region_params).fetchall()
        discounts = [r["disc"] for r in disc_rows if r["disc"] is not None]

        # HHI — концентрация рынка по доле поставщика
        supp_shares = c.execute(f"""
            SELECT c.supplier_inn, SUM(c.contract_price) AS s
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {period_sql} AND {region_sql}
              AND c.supplier_inn IS NOT NULL AND c.contract_price IS NOT NULL
            GROUP BY c.supplier_inn
        """, okpd2_params + period_params + region_params).fetchall()

    from ._common import percentile
    hhi = None
    if supp_shares:
        total = sum(r["s"] or 0 for r in supp_shares)
        if total > 0:
            hhi = sum(((r["s"] or 0) / total * 100) ** 2 for r in supp_shares)

    return {
        "okpd2_prefix": okpd2_prefix or "",
        "region_code": region_code or "",
        "from_date": from_date,
        "to_date": to_date,
        "contracts_count": row["contracts_count"],
        "total_sum_rub": float(row["total_sum"] or 0),
        "avg_price_rub": float(row["avg_price"] or 0) if row["avg_price"] else None,
        "unique_customers": cust_cnt["n"],
        "unique_suppliers": supp_cnt["n"],
        "discount_pct_median": percentile(discounts, 50),
        "discount_pct_p25": percentile(discounts, 25),
        "discount_pct_p75": percentile(discounts, 75),
        "discounts_sample": len(discounts),
        "hhi": round(hhi, 1) if hhi is not None else None,
    }


def top_sectors(region_code: str | None, from_date: str, to_date: str,
                limit: int = 20) -> list[dict]:
    """Топ ОКПД2 (2-значный префикс) по объёму закупок."""
    region_sql = "1=1"; region_params: list = []
    if region_code:
        region_sql = "c.customer_region = ?"; region_params = [region_code]
    period_sql, period_params = _period_clause(from_date, to_date)

    with eis_analytics.conn() as c:
        rows = c.execute(f"""
            SELECT substr(ci.okpd2_code, 1, 2) AS prefix,
                   COUNT(DISTINCT c.reg_num) AS contracts,
                   COALESCE(SUM(DISTINCT c.contract_price), 0) AS total_sum
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {region_sql} AND {period_sql} AND ci.okpd2_code IS NOT NULL
            GROUP BY prefix
            ORDER BY total_sum DESC LIMIT ?
        """, region_params + period_params + [limit]).fetchall()
    return [dict(r) for r in rows]


def top_customers(okpd2_prefix: str | None, region_code: str | None,
                  from_date: str, to_date: str, limit: int = 20) -> list[dict]:
    okpd2_sql, okpd2_params = okpd2_prefix_clause(okpd2_prefix or "", "ci.okpd2_code")
    region_sql = "1=1"; region_params: list = []
    if region_code:
        region_sql = "c.customer_region = ?"; region_params = [region_code]
    period_sql, period_params = _period_clause(from_date, to_date)

    with eis_analytics.conn() as c:
        rows = c.execute(f"""
            SELECT c.customer_inn AS inn, MAX(c.customer_name) AS name,
                   COUNT(DISTINCT c.reg_num) AS contracts,
                   COALESCE(SUM(DISTINCT c.contract_price), 0) AS total_sum
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {region_sql} AND {period_sql}
              AND c.customer_inn IS NOT NULL
            GROUP BY c.customer_inn
            ORDER BY total_sum DESC LIMIT ?
        """, okpd2_params + region_params + period_params + [limit]).fetchall()
    return [dict(r) for r in rows]


def top_suppliers(okpd2_prefix: str | None, region_code: str | None,
                  from_date: str, to_date: str, limit: int = 20) -> list[dict]:
    okpd2_sql, okpd2_params = okpd2_prefix_clause(okpd2_prefix or "", "ci.okpd2_code")
    region_sql = "1=1"; region_params: list = []
    if region_code:
        region_sql = "c.customer_region = ?"; region_params = [region_code]
    period_sql, period_params = _period_clause(from_date, to_date)

    with eis_analytics.conn() as c:
        rows = c.execute(f"""
            SELECT c.supplier_inn AS inn, MAX(c.supplier_name) AS name,
                   COUNT(DISTINCT c.reg_num) AS contracts,
                   COALESCE(SUM(DISTINCT c.contract_price), 0) AS total_sum
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {region_sql} AND {period_sql}
              AND c.supplier_inn IS NOT NULL
            GROUP BY c.supplier_inn
            ORDER BY total_sum DESC LIMIT ?
        """, okpd2_params + region_params + period_params + [limit]).fetchall()
    return [dict(r) for r in rows]


def time_series_by_month(okpd2_prefix: str | None, region_code: str | None,
                         from_date: str, to_date: str) -> list[dict]:
    """Количество контрактов и сумма по месяцам — для графика."""
    okpd2_sql, okpd2_params = okpd2_prefix_clause(okpd2_prefix or "", "ci.okpd2_code")
    region_sql = "1=1"; region_params: list = []
    if region_code:
        region_sql = "c.customer_region = ?"; region_params = [region_code]
    period_sql, period_params = _period_clause(from_date, to_date)

    with eis_analytics.conn() as c:
        rows = c.execute(f"""
            SELECT substr(c.sign_date, 1, 7) AS month,
                   COUNT(DISTINCT c.reg_num) AS contracts,
                   COALESCE(SUM(DISTINCT c.contract_price), 0) AS total_sum
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {region_sql} AND {period_sql}
              AND c.sign_date IS NOT NULL
            GROUP BY month ORDER BY month
        """, okpd2_params + region_params + period_params).fetchall()
    return [dict(r) for r in rows]
