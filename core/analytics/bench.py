"""Ценовые бенчмарки по срезам ОКПД2 × регион × период."""
from __future__ import annotations

from ..storage import eis_analytics
from ._common import MIN_SAMPLE, percentile, okpd2_prefix_clause, period_cutoff


def bench_by_okpd2_region(okpd2_prefix: str, region_code: str | None = None,
                          months_back: int = 12) -> dict:
    """Распределение НМЦК / финальной цены / скидки по (OKPD2 × регион × период).

    Параметры:
        okpd2_prefix: '62' / '62.01' / '62.01.12'
        region_code: код региона КЛАДР ('77', '78') или None (= вся РФ)
        months_back: сколько месяцев в прошлое (отсчёт от сегодня)

    Возвращает dict с полями:
        sample_size, enough_data, nmck{}, final_price{}, discount_pct{},
        contracts_with_discount, top_customers[], top_suppliers[],
        okpd2_prefix, region_code, months_back
    """
    prefix = (okpd2_prefix or "").strip()
    cutoff = period_cutoff(months_back)

    okpd2_sql, okpd2_params = okpd2_prefix_clause(prefix, "ci.okpd2_code")

    region_sql = ""
    region_params: list = []
    if region_code:
        region_sql = " AND c.customer_region = ?"
        region_params = [region_code]

    # Берём DISTINCT контракты — один контракт может иметь много позиций по
    # разным ОКПД2. Если любая позиция подходит под prefix → контракт учитывается.
    query = f"""
        SELECT DISTINCT c.reg_num, c.contract_price, c.purchase_number,
               c.customer_inn, c.customer_name, c.supplier_inn, c.supplier_name,
               n.max_price
        FROM contracts c
        JOIN contract_items ci ON ci.reg_num = c.reg_num
        LEFT JOIN notices n ON n.reg_number = c.purchase_number
        WHERE {okpd2_sql}
          AND c.sign_date >= ?
          AND c.contract_price IS NOT NULL
          {region_sql}
    """
    params = okpd2_params + [cutoff] + region_params

    with eis_analytics.conn() as conn:
        rows = conn.execute(query, params).fetchall()

    contracts = [dict(r) for r in rows]
    sample = len(contracts)

    nmck = [c["max_price"] for c in contracts if c["max_price"]]
    final = [c["contract_price"] for c in contracts if c["contract_price"]]
    discounts = [
        100.0 * (1 - c["contract_price"] / c["max_price"])
        for c in contracts
        if c["max_price"] and c["contract_price"] and c["max_price"] > 0
    ]

    result = {
        "okpd2_prefix": prefix,
        "region_code": region_code or "",
        "months_back": months_back,
        "sample_size": sample,
        "enough_data": sample >= MIN_SAMPLE,
        "nmck": _stats(nmck),
        "final_price": _stats(final),
        "discount_pct": _stats(discounts),
        "contracts_with_discount": len(discounts),
    }

    # Топ-5 заказчиков и поставщиков по числу контрактов в срезе
    if sample > 0:
        from collections import Counter
        cust = Counter((c["customer_inn"], c["customer_name"]) for c in contracts if c["customer_inn"])
        supp = Counter((c["supplier_inn"], c["supplier_name"]) for c in contracts if c["supplier_inn"])
        result["top_customers"] = [
            {"inn": inn, "name": name, "contracts": n}
            for (inn, name), n in cust.most_common(5)
        ]
        result["top_suppliers"] = [
            {"inn": inn, "name": name, "contracts": n}
            for (inn, name), n in supp.most_common(5)
        ]
    else:
        result["top_customers"] = []
        result["top_suppliers"] = []

    return result


def _stats(values: list[float]) -> dict:
    """p25 / median / p75 / min / max / count + защита от пустого списка."""
    if not values:
        return {"count": 0, "median": None, "p25": None, "p75": None,
                "min": None, "max": None}
    return {
        "count": len(values),
        "median": percentile(values, 50),
        "p25": percentile(values, 25),
        "p75": percentile(values, 75),
        "min": min(values),
        "max": max(values),
    }
