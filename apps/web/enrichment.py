"""Обогащение карточки тендера данными из витрины eis_analytics.

Для каждого тендера:
  1. Пытаемся найти его в витрине по реестровому номеру → получить customer_inn
     и ОКПД2 без угадывания.
  2. Если не нашли — fuzzy match customer_name в contracts для ИНН,
     LLM-classifier для ОКПД2.
  3. Вызов core.analytics.bench/risk → формирование price_context и customer_risk.

Возвращаемые блоки:
  - price_context: {sample_size, discount_median_pct, nmck_median, summary} или None
  - customer_risk: {contracts_count, complaints_count, in_rnp, risk_score, summary} или None
  - okpd2_guess: {code, name, confidence, source: 'exact'|'classified'} или None

Если блок не удалось собрать — ставим None, фронт показывает «данных мало».
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from core.analytics import bench, risk, okpd2_classifier
from core.analytics.cache import bench_from_cache
from core.storage import eis_analytics


# --------------- поиск в витрине ---------------

def _find_in_notices(reg_number: str) -> dict | None:
    """Вернуть данные из notices + первый ОКПД2 из notice_items."""
    if not reg_number:
        return None
    with eis_analytics.conn() as c:
        n = c.execute(
            "SELECT reg_number, customer_inn, customer_name, customer_region "
            "FROM notices WHERE reg_number = ? LIMIT 1",
            (reg_number,),
        ).fetchone()
        if not n:
            return None
        okpd = c.execute(
            "SELECT okpd2_code, okpd2_name FROM notice_items "
            "WHERE reg_number = ? AND okpd2_code IS NOT NULL "
            "ORDER BY index_num LIMIT 1",
            (reg_number,),
        ).fetchone()
    return {
        "reg_number": n["reg_number"],
        "customer_inn": n["customer_inn"],
        "customer_name": n["customer_name"],
        "customer_region": n["customer_region"],
        "okpd2_code": okpd["okpd2_code"] if okpd else None,
        "okpd2_name": okpd["okpd2_name"] if okpd else None,
    }


def _find_customer_inn_by_name(customer_name: str) -> str | None:
    """Простая fuzzy-эвристика: находим заказчика в contracts, чьё имя
    содержит >=3 общих слов с нашим. Если единственный такой — возвращаем.
    Цель — не угадать любой ценой, а иногда подсобить."""
    if not customer_name or len(customer_name) < 5:
        return None
    # Берём 2-3 самых длинных слова как "ключ"
    words = [w for w in customer_name.upper().split() if len(w) >= 4]
    if len(words) < 2:
        return None
    like = "%" + "%".join(words[:3]) + "%"
    with eis_analytics.conn() as c:
        rows = c.execute("""
            SELECT customer_inn, COUNT(*) AS n
            FROM contracts WHERE customer_name LIKE ?
            GROUP BY customer_inn ORDER BY n DESC LIMIT 2
        """, (like,)).fetchall()
    if len(rows) == 1 and rows[0]["customer_inn"]:
        return rows[0]["customer_inn"]
    return None


# --------------- формирование блоков ---------------

MOSCOW_REGIONS_PRIORITY = ["77", "50", "78"]


def _build_price_context(okpd2: str | None, region: str | None) -> dict | None:
    """Компактный блок для карточки. None если данных нет."""
    if not okpd2:
        return None
    b = bench_from_cache(okpd2, region or "", 12)
    if not b or b.get("sample_size", 0) < 10:
        return None

    # короткое summary из цифр
    disc = b.get("discount_pct_median")
    nmck = b.get("nmck_median")
    final = b.get("final_price_median")
    summary_parts = []
    if disc is not None:
        summary_parts.append(f"медианная скидка {disc:.1f}%")
    if final is not None:
        mln = final / 1_000_000
        summary_parts.append(f"медианная цена контракта {mln:.1f} млн ₽")
    summary = (
        f"Выборка {b['sample_size']} контрактов (ОКПД2 {b['okpd2_prefix']}"
        f"{', регион ' + b['region_code'] if b.get('region_code') else ''}, 12 мес). "
        + "; ".join(summary_parts) if summary_parts else ""
    )

    return {
        "okpd2_prefix": b["okpd2_prefix"],
        "region_code": b.get("region_code") or "",
        "sample_size": b["sample_size"],
        "contracts_with_discount": b.get("contracts_with_discount", 0),
        "discount_pct_median": disc,
        "discount_pct_p25": b.get("discount_pct_p25"),
        "discount_pct_p75": b.get("discount_pct_p75"),
        "nmck_median": nmck,
        "final_price_median": final,
        "summary": summary,
    }


def _build_customer_risk(inn: str | None) -> dict | None:
    if not inn:
        return None
    r = risk.risk_by_inn(inn)
    if r.get("error"):
        return None
    if not r.get("enough_data"):
        return None

    cust = r.get("as_customer", {})
    supp = r.get("as_supplier", {})

    # Компактный summary
    parts = []
    if cust.get("contracts_total"):
        summ_mln = cust["contracts_sum_rub"] / 1_000_000
        parts.append(f"как заказчик: {cust['contracts_total']} контрактов на {summ_mln:.1f} млн ₽")
    elif cust.get("notices_count"):
        parts.append(f"{cust['notices_count']} извещений (контрактов в нашей базе нет)")
    if cust.get("complaints_count"):
        parts.append(f"{cust['complaints_count']} жалоб")
    if cust.get("unilateral_refusals_count"):
        parts.append(f"{cust['unilateral_refusals_count']} расторжений")
    if supp.get("in_rnp"):
        parts.append("🚨 В РНП как поставщик")
    summary = "; ".join(parts) if parts else None

    return {
        "inn": r["inn"],
        "name": r.get("name"),
        "contracts_as_customer": cust.get("contracts_total", 0),
        "contracts_sum_as_customer": cust.get("contracts_sum_rub", 0),
        "notices_count": cust.get("notices_count", 0),
        "complaints_count": cust.get("complaints_count", 0),
        "unilateral_refusals_count": cust.get("unilateral_refusals_count", 0),
        "in_rnp": supp.get("in_rnp", False),
        "rnp_records": supp.get("rnp_records", []),
        "risk_flags": r.get("risk_flags", []),
        "risk_score": r.get("risk_score", 0),
        "summary": summary,
    }


def _build_okpd2_guess(title: str, description: str,
                      notice_data: dict | None) -> dict | None:
    """Приоритет: точный match из notice → LLM/heuristic classify."""
    if notice_data and notice_data.get("okpd2_code"):
        return {
            "code": notice_data["okpd2_code"],
            "name": notice_data.get("okpd2_name"),
            "confidence": 1.0,
            "source": "exact",
        }
    # fallback — classifier
    cands = okpd2_classifier.guess_okpd2(title or "", description or "")
    if not cands:
        return None
    top = cands[0]
    return {
        "code": top["code"],
        "name": top["name"],
        "confidence": top["confidence"],
        "source": "classified",
    }


# --------------- главный entry-point ---------------

def enrich_tender_card(tender: dict) -> dict:
    """Добавить блоки price_context, customer_risk, okpd2_guess к карточке.

    Ничего не ломает: если данные не нашли — блок = None.
    """
    reg_number = (tender.get("reestr_number") or tender.get("external_id") or "").strip()
    title = tender.get("title", "")
    description = tender.get("description", "") or tender.get("summary", "")
    customer_name = tender.get("customer", "")
    region = tender.get("region_code", "")  # если есть

    # 1. Пытаемся найти в витрине
    notice = _find_in_notices(reg_number)
    if notice:
        if not region and notice.get("customer_region"):
            region = notice["customer_region"]
        customer_inn = notice.get("customer_inn")
    else:
        customer_inn = _find_customer_inn_by_name(customer_name)

    # 2. ОКПД2 — точный или guessed (0.6+ confidence для classified — иначе
    # показываем кандидат в UI, но bench не считаем).
    okpd2_guess = _build_okpd2_guess(title, description, notice)
    okpd2_code = None
    if okpd2_guess:
        is_exact = okpd2_guess["source"] == "exact"
        if is_exact or okpd2_guess["confidence"] >= 0.6:
            parts = okpd2_guess["code"].split(".")
            if parts:
                okpd2_code = parts[0][:2]

    # 3. Bench и risk
    price_context = _build_price_context(okpd2_code, region)
    customer_risk = _build_customer_risk(customer_inn)

    return {
        **tender,
        "okpd2_guess": okpd2_guess,
        "price_context": price_context,
        "customer_risk": customer_risk,
    }
