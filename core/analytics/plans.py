"""Аналитика планов-графиков 44-ФЗ (RPGZ/tenderPlan2020).

Срез «что заказчики СОБИРАЮТСЯ закупить» — параллель к market.py, который
анализирует уже состоявшиеся контракты. Гранулярность времени — год
(publishYear позиции плана).

Все запросы фильтруют по position_canceled=0 (отменённые позиции скрываем).

Матчинг план↔извещение идёт по «каноническому» ИКЗ:
  canonical = SUBSTR(ikz,1,26) || SUBSTR(ikz,30)
Различие в позициях 27-29 — это «номер лота в извещении»; в плане там
всегда 000, в извещении подставляется реальный номер. Поэтому матчить
напрямую `plan.ikz = notice.ikz` нельзя — теряем все совпадения.
"""
from __future__ import annotations

from ..storage import eis_analytics
from ._common import okpd2_prefix_clause
from .market import OKPD2_SECTIONS_2D, okpd2_section_name
from .orgnames import short_org_name


def _filter_clause(plan_year: int | None, region_code: str | None,
                   okpd2_prefix: str | None, col_okpd2: str = "p.okpd2_code"):
    """Общий WHERE-фрагмент для запросов по позициям плана."""
    where = ["p.position_canceled = 0"]
    params: list = []
    if plan_year:
        where.append("p.publish_year = ?")
        params.append(plan_year)
    if region_code:
        where.append("p.customer_region = ?")
        params.append(region_code)
    if okpd2_prefix:
        sql, ps = okpd2_prefix_clause(okpd2_prefix, col_okpd2)
        where.append(sql)
        params.extend(ps)
    return " AND ".join(where), params


def plans_overview(plan_year: int | None, region_code: str | None,
                   okpd2_prefix: str | None) -> dict:
    """KPI режима «Планы»: сколько закупок планируют, на какую сумму,
    сколько заказчиков, и сколько уже превратилось в реальные торги
    (через матчинг ИКЗ с notice_ikz_codes — это и есть метрика
    «дисциплина плана»)."""
    where_sql, params = _filter_clause(plan_year, region_code, okpd2_prefix)

    with eis_analytics.conn() as c:
        row = c.execute(f"""
            SELECT COUNT(*) AS positions,
                   COALESCE(SUM(p.amount_current_year), 0) AS total_current_year,
                   COALESCE(SUM(p.amount_total), 0) AS total_all_years,
                   COUNT(DISTINCT p.customer_inn) AS unique_customers,
                   COUNT(DISTINCT p.okpd2_code) AS unique_okpd2,
                   AVG(p.amount_current_year) AS avg_amount
            FROM tender_plan_positions p
            WHERE {where_sql}
        """, params).fetchone()

        # Запущенные позиции — каноническая форма ИКЗ найдена в извещениях.
        launched = c.execute(f"""
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(p.amount_current_year), 0) AS sum_rub
            FROM tender_plan_positions p
            WHERE {where_sql}
              AND p.ikz IS NOT NULL
              AND (SUBSTR(p.ikz,1,26) || SUBSTR(p.ikz,30)) IN
                  (SELECT SUBSTR(ikz,1,26) || SUBSTR(ikz,30) FROM notice_ikz_codes)
        """, params).fetchone()

        return {
            "positions_count": row["positions"],
            "total_amount_current_year": row["total_current_year"],
            "total_amount_all_years": row["total_all_years"],
            "unique_customers": row["unique_customers"],
            "unique_okpd2": row["unique_okpd2"],
            "avg_position_amount": row["avg_amount"],
            "launched_count": launched["n"],
            "launched_sum": launched["sum_rub"],
            "upcoming_count": row["positions"] - launched["n"],
            "upcoming_sum": (row["total_current_year"] or 0) - (launched["sum_rub"] or 0),
        }


def plans_top_sectors(plan_year: int | None, region_code: str | None,
                      limit: int = 30) -> list[dict]:
    """Топ ОКПД2 (по 2-значному префиксу) по объёму планов."""
    where_sql, params = _filter_clause(plan_year, region_code, None)

    with eis_analytics.conn() as c:
        rows = c.execute(f"""
            SELECT SUBSTR(p.okpd2_code, 1, 2) AS prefix,
                   COUNT(*) AS positions,
                   COALESCE(SUM(p.amount_current_year), 0) AS total_sum
            FROM tender_plan_positions p
            WHERE {where_sql} AND p.okpd2_code IS NOT NULL
            GROUP BY prefix
            ORDER BY total_sum DESC
            LIMIT ?
        """, params + [limit]).fetchall()

        total = sum(r["total_sum"] for r in rows) or 1
        return [{
            "prefix": r["prefix"],
            "name": OKPD2_SECTIONS_2D.get(r["prefix"], ""),
            "contracts": r["positions"],   # named contracts для совместимости с TopEntry
            "total_sum": r["total_sum"],
            "share_pct": round(100.0 * r["total_sum"] / total, 2),
        } for r in rows]


def plans_top_customers(plan_year: int | None, region_code: str | None,
                        okpd2_prefix: str | None, limit: int = 20) -> list[dict]:
    """Топ заказчиков по объёму планов."""
    where_sql, params = _filter_clause(plan_year, region_code, okpd2_prefix)

    with eis_analytics.conn() as c:
        rows = c.execute(f"""
            SELECT p.customer_inn AS inn,
                   tp.customer_name AS name,
                   COUNT(*) AS positions,
                   COALESCE(SUM(p.amount_current_year), 0) AS total_sum
            FROM tender_plan_positions p
            LEFT JOIN tender_plans tp ON tp.plan_number = p.plan_number
            WHERE {where_sql} AND p.customer_inn IS NOT NULL
            GROUP BY p.customer_inn
            ORDER BY total_sum DESC
            LIMIT ?
        """, params + [limit]).fetchall()

        total = sum(r["total_sum"] for r in rows) or 1
        return [{
            "inn": r["inn"],
            "name": r["name"],
            "short_name": short_org_name(r["name"]) if r["name"] else r["inn"],
            "contracts": r["positions"],
            "total_sum": r["total_sum"],
            "share_pct": round(100.0 * r["total_sum"] / total, 2),
        } for r in rows]


def plans_calendar(plan_year: int | None, region_code: str | None,
                   okpd2_prefix: str | None, top_n_sectors: int = 8) -> dict:
    """Календарь возможностей: по годам × топ-отраслям.

    Time-axis — publish_year (когда планируется выйти на торги).
    Категории — топ-отрасли по объёму. Возвращаем структуру под heatmap/bubble:
    {years: [...], sectors: [{prefix, name}, ...], cells: [{year, prefix, sum, count}]}.

    Если plan_year задан — в календаре всё равно показываем все publish_year
    из планов этого года (которые покрывают plan_year, plan_year+1, +2).
    """
    # Календарь — только будущее и только «не запущенные» позиции:
    # — publish_year >= текущего года (отсекаем хвосты прошлого);
    # — ИКЗ позиции отсутствует в notice_ikz_codes (= извещение ещё не опубликовано).
    # Это и есть «возможности»: то, что заказчики ОБЕЩАЛИ купить, но пока не вышли.
    from datetime import date
    current_year = date.today().year
    where = [
        "p.position_canceled = 0",
        "p.publish_year IS NOT NULL",
        "p.publish_year >= ?",
        # canonical match — см. модуль-docstring
        "(p.ikz IS NULL OR (SUBSTR(p.ikz,1,26) || SUBSTR(p.ikz,30)) NOT IN "
        "(SELECT SUBSTR(ikz,1,26) || SUBSTR(ikz,30) FROM notice_ikz_codes))",
    ]
    params: list = [current_year]
    if plan_year:
        where.append("p.plan_year = ?")
        params.append(plan_year)
    if region_code:
        where.append("p.customer_region = ?")
        params.append(region_code)
    if okpd2_prefix:
        sql, ps = okpd2_prefix_clause(okpd2_prefix, "p.okpd2_code")
        where.append(sql)
        params.extend(ps)
    where_sql = " AND ".join(where)

    with eis_analytics.conn() as c:
        # Топ-отрасли по объёму за всё окно планирования
        top_sectors = c.execute(f"""
            SELECT SUBSTR(p.okpd2_code, 1, 2) AS prefix,
                   COALESCE(SUM(p.amount_current_year + COALESCE(p.amount_first_year,0)
                                + COALESCE(p.amount_second_year,0)), 0) AS total_sum
            FROM tender_plan_positions p
            WHERE {where_sql} AND p.okpd2_code IS NOT NULL
            GROUP BY prefix
            ORDER BY total_sum DESC
            LIMIT ?
        """, params + [top_n_sectors]).fetchall()
        sector_prefixes = [r["prefix"] for r in top_sectors]

        if not sector_prefixes:
            return {"years": [], "sectors": [], "cells": []}

        # Все годы, которые встречаются в данных
        years = [r[0] for r in c.execute(f"""
            SELECT DISTINCT p.publish_year FROM tender_plan_positions p
            WHERE {where_sql}
            ORDER BY p.publish_year
        """, params).fetchall()]

        # Ячейки (year × prefix). publish_year даёт год, в который планируется
        # выйти на торги; берём currentYear если publish_year == plan_year,
        # firstYear если +1, secondYear если +2 — иначе amount_total.
        ph = ",".join("?" * len(sector_prefixes))
        cells = c.execute(f"""
            SELECT p.publish_year AS year,
                   SUBSTR(p.okpd2_code, 1, 2) AS prefix,
                   COUNT(*) AS positions,
                   COALESCE(SUM(p.amount_current_year), 0) AS sum_rub
            FROM tender_plan_positions p
            WHERE {where_sql}
              AND SUBSTR(p.okpd2_code, 1, 2) IN ({ph})
            GROUP BY year, prefix
        """, params + sector_prefixes).fetchall()

        return {
            "years": years,
            "sectors": [{
                "prefix": r["prefix"],
                "name": OKPD2_SECTIONS_2D.get(r["prefix"], r["prefix"]),
                "total_sum": r["total_sum"],
            } for r in top_sectors],
            "cells": [{
                "year": r["year"],
                "prefix": r["prefix"],
                "positions": r["positions"],
                "total_sum": r["sum_rub"],
            } for r in cells],
        }


def plans_available_years() -> list[int]:
    """Годы для селектора «Горизонт планирования» — когда заказчики собираются
    выйти на торги. Берём publish_year позиций (а не plan_year плана), потому
    что один план-2026 покрывает закупки 2026/2027/2028 — горизонт это про
    «когда», не про «когда опубликовали план».

    Отбрасываем прошлое (publish_year < текущего года) — там это уже не план,
    а исторические планы; они анализируются в режиме «Факт».
    """
    from datetime import date
    current = date.today().year
    with eis_analytics.conn() as c:
        return [r[0] for r in c.execute(
            """SELECT DISTINCT publish_year FROM tender_plan_positions
               WHERE publish_year IS NOT NULL AND publish_year >= ?
                 AND position_canceled = 0
               ORDER BY publish_year ASC""",
            (current,)
        ).fetchall()]
