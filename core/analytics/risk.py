"""Риск-сводка по ИНН — работает и для заказчика, и для поставщика."""
from __future__ import annotations

from ..storage import eis_analytics


def risk_by_inn(inn: str) -> dict:
    """Сводка по ИНН. Возвращает два блока (as_customer + as_supplier) и
    итоговый risk_score + флаги.

    enough_data=False когда ИНН вообще не встречался в контрактах/жалобах/РНП.
    """
    inn = (inn or "").strip()
    if not inn or not inn.isdigit() or len(inn) not in (10, 12):
        return {"inn": inn, "enough_data": False,
                "error": "invalid_inn", "reason": "ИНН должен содержать 10 или 12 цифр"}

    with eis_analytics.conn() as c:
        # ------ as customer ------
        cust_row = c.execute("""
            SELECT COUNT(*) AS n, COALESCE(SUM(contract_price), 0) AS total_sum,
                   MAX(customer_name) AS name
            FROM contracts WHERE customer_inn = ?
        """, (inn,)).fetchone()
        cust = {
            "contracts_total": cust_row["n"],
            "contracts_sum_rub": float(cust_row["total_sum"] or 0),
            "name": cust_row["name"],
        }
        # Извещения тоже считаем — заказчик может что-то публиковать без
        # заключённых пока контрактов за наш период.
        notices_row = c.execute("""
            SELECT COUNT(*) AS n, MAX(customer_name) AS name
            FROM notices WHERE customer_inn = ?
        """, (inn,)).fetchone()
        cust["notices_count"] = notices_row["n"]
        if not cust["name"]:
            cust["name"] = notices_row["name"]
        cust["complaints_count"] = c.execute(
            "SELECT COUNT(*) FROM complaints WHERE customer_inn = ?", (inn,)
        ).fetchone()[0]
        cust["unilateral_refusals_count"] = c.execute(
            "SELECT COUNT(*) FROM unilateral_refusals WHERE customer_inn = ? AND initiator='customer'",
            (inn,),
        ).fetchone()[0]

        # ------ as supplier ------
        supp_row = c.execute("""
            SELECT COUNT(*) AS n, COALESCE(SUM(contract_price), 0) AS total_sum,
                   MAX(supplier_name) AS name
            FROM contracts WHERE supplier_inn = ?
        """, (inn,)).fetchone()
        supp = {
            "contracts_total": supp_row["n"],
            "contracts_sum_rub": float(supp_row["total_sum"] or 0),
            "name": supp_row["name"],
        }
        # Расторжения — когда инициатор customer, а supplier_inn наш
        supp["unilateral_refusals_against"] = c.execute(
            "SELECT COUNT(*) FROM unilateral_refusals WHERE supplier_inn = ? AND initiator='customer'",
            (inn,),
        ).fetchone()[0]
        # Жалобы где этот ИНН — заявитель (обжалует закупки)
        supp["complaints_as_applicant"] = c.execute(
            "SELECT COUNT(*) FROM complaints WHERE applicant_inn = ?", (inn,)
        ).fetchone()[0]

        # ------ РНП ------
        rnp_rows = c.execute("""
            SELECT reg_number, publish_date, approve_org_name,
                   create_reason, auto_exclude_date
            FROM unfair_suppliers WHERE supplier_inn = ?
            ORDER BY publish_date DESC
        """, (inn,)).fetchall()
        supp["in_rnp"] = len(rnp_rows) > 0
        supp["rnp_records"] = [dict(r) for r in rnp_rows]

    # ------ агрегаты + флаги ------
    flags = []
    if supp["in_rnp"]:
        flags.append("в_РНП")
    if supp["unilateral_refusals_against"] > 0:
        flags.append(f"расторжения_{supp['unilateral_refusals_against']}")
    if cust["complaints_count"] > 0 and cust["contracts_total"] > 0:
        ratio = cust["complaints_count"] / max(cust["contracts_total"], 1)
        if ratio > 0.1:
            flags.append("высокая_доля_жалоб")
    if cust["unilateral_refusals_count"] > 0:
        flags.append(f"разрывает_контракты_{cust['unilateral_refusals_count']}")

    # простая эвристика скора 0..100 (чем выше — тем хуже)
    score = 0
    if supp["in_rnp"]:
        score += 80
    score += min(supp["unilateral_refusals_against"] * 10, 30)
    score += min(cust["complaints_count"] * 3, 20)
    score += min(cust["unilateral_refusals_count"] * 5, 15)
    score = min(score, 100)

    enough = bool(
        cust["contracts_total"] or cust["notices_count"] or
        supp["contracts_total"] or
        cust["complaints_count"] or supp["in_rnp"]
    )

    # объединим имя
    name = cust.get("name") or supp.get("name")

    return {
        "inn": inn,
        "name": name,
        "enough_data": enough,
        "as_customer": cust,
        "as_supplier": supp,
        "risk_flags": flags,
        "risk_score": score,
    }
