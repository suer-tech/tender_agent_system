"""Общерыночные срезы — для страницы /market."""
from __future__ import annotations

from collections import Counter
from ..storage import eis_analytics
from ._common import okpd2_prefix_clause


# Короткие названия 2-значных разделов ОКПД2 (ОК 034-2014).
# Используются на UI вместо голых цифр на оси и в легендах.
OKPD2_SECTIONS_2D: dict[str, str] = {
    "01": "Сельское хозяйство", "02": "Лесоводство", "03": "Рыболовство",
    "05": "Уголь", "06": "Нефть и газ", "07": "Металлические руды",
    "08": "Прочие полезные ископаемые", "09": "Услуги в добыче",
    "10": "Пищевые продукты", "11": "Напитки", "12": "Табак",
    "13": "Текстиль", "14": "Одежда", "15": "Кожа и обувь",
    "16": "Древесина", "17": "Бумага", "18": "Полиграфия",
    "19": "Кокс и нефтепродукты", "20": "Химия", "21": "Фармацевтика",
    "22": "Резина и пластмассы", "23": "Прочие неметаллические изделия",
    "24": "Металлургия", "25": "Готовые металлоизделия",
    "26": "Электроника и оптика", "27": "Электрооборудование",
    "28": "Машины и оборудование", "29": "Автотранспорт",
    "30": "Прочие транспортные средства", "31": "Мебель",
    "32": "Прочие готовые изделия", "33": "Ремонт и монтаж оборудования",
    "35": "Электроэнергия и тепло", "36": "Водоснабжение",
    "37": "Сточные воды", "38": "Сбор и обработка отходов",
    "39": "Рекультивация",
    "41": "Здания и строительство", "42": "Инженерные сооружения",
    "43": "Спецстройработы",
    "45": "Торговля автотранспортом", "46": "Оптовая торговля",
    "47": "Розничная торговля",
    "49": "Сухопутный транспорт", "50": "Водный транспорт",
    "51": "Воздушный транспорт", "52": "Складирование и логистика",
    "53": "Почта и курьеры",
    "55": "Гостиницы", "56": "Общепит",
    "58": "Издательская деятельность", "59": "Кино и звукозапись",
    "60": "Радио и ТВ", "61": "Телекоммуникации",
    "62": "ИТ и ПО", "63": "Информационные услуги",
    "64": "Финансовые услуги", "65": "Страхование",
    "66": "Вспомогательные финуслуги",
    "68": "Недвижимость", "69": "Юридические и бухгалтерия",
    "70": "Консалтинг и управление", "71": "Архитектура и инжиниринг",
    "72": "НИОКР", "73": "Реклама и маркетинг",
    "74": "Прочая профдеятельность", "75": "Ветеринария",
    "77": "Аренда и лизинг", "78": "Подбор персонала", "79": "Туризм",
    "80": "Охрана и безопасность", "81": "Обслуживание зданий",
    "82": "Административные услуги",
    "84": "Госуправление", "85": "Образование", "86": "Здравоохранение",
    "87": "Уход с проживанием", "88": "Социальные услуги",
    "90": "Творчество и искусство", "91": "Библиотеки и музеи",
    "93": "Спорт и отдых", "94": "Общественные организации",
    "95": "Ремонт оборудования", "96": "Прочие персональные услуги",
}


def okpd2_section_name(prefix: str | None) -> str:
    if not prefix:
        return ""
    return OKPD2_SECTIONS_2D.get(prefix[:2], "")


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
    """Топ ОКПД2 (2-значный префикс) по объёму закупок.

    Возвращает полный рынок (без фильтра по отрасли) — UI подсвечивает
    выбранную отрасль на фоне общей картины. Каждая строка содержит
    `name` (короткое название раздела) и `share_pct` (доля от общего
    объёма в пределах region×period).
    """
    region_sql = "1=1"; region_params: list = []
    if region_code:
        region_sql = "c.customer_region = ?"; region_params = [region_code]
    period_sql, period_params = _period_clause(from_date, to_date)

    with eis_analytics.conn() as c:
        # Общий объём в пределах period × region — нужен как база для долей.
        total_row = c.execute(f"""
            SELECT COALESCE(SUM(DISTINCT c.contract_price), 0) AS total
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {region_sql} AND {period_sql} AND ci.okpd2_code IS NOT NULL
        """, region_params + period_params).fetchone()
        grand_total = float(total_row["total"] or 0)

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

    out: list[dict] = []
    for r in rows:
        d = dict(r)
        prefix = d.get("prefix") or ""
        d["name"] = OKPD2_SECTIONS_2D.get(prefix, "")
        d["share_pct"] = round(d["total_sum"] / grand_total * 100, 2) if grand_total else 0.0
        out.append(d)
    return out


def top_items_in_sector(okpd2_prefix: str, region_code: str | None,
                        from_date: str, to_date: str, limit: int = 15) -> list[dict]:
    """Топ позиций (товаров/услуг) внутри выбранной отрасли по сумме позиций.

    Группируем по полному ОКПД2-коду (4–9 знаков), название берём из
    `okpd2_name` справочника. Метрика — SUM(`sum_amount`) позиций, а не
    `contract_price` контракта: один контракт может содержать позиции
    из разных подразделов одной отрасли, и мы хотим разнести их по
    реальным товарам.

    `share_pct` — доля позиции в общем объёме позиций *этой отрасли*
    (не всего рынка), чтобы видеть концентрацию внутри.
    """
    if not okpd2_prefix:
        return []

    region_sql = "1=1"; region_params: list = []
    if region_code:
        region_sql = "c.customer_region = ?"; region_params = [region_code]
    period_sql, period_params = _period_clause(from_date, to_date)
    okpd2_sql, okpd2_params = okpd2_prefix_clause(okpd2_prefix, "ci.okpd2_code")

    with eis_analytics.conn() as c:
        # Сумма всех позиций внутри отрасли — база для долей.
        total_row = c.execute(f"""
            SELECT COALESCE(SUM(ci.sum_amount), 0) AS total
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {region_sql} AND {period_sql}
              AND ci.sum_amount IS NOT NULL AND ci.sum_amount > 0
        """, okpd2_params + region_params + period_params).fetchone()
        sector_total = float(total_row["total"] or 0)

        rows = c.execute(f"""
            SELECT ci.okpd2_code AS code,
                   MAX(ci.okpd2_name) AS name,
                   COUNT(DISTINCT c.reg_num) AS contracts,
                   COALESCE(SUM(ci.sum_amount), 0) AS total_sum
            FROM contracts c
            JOIN contract_items ci ON ci.reg_num = c.reg_num
            WHERE {okpd2_sql} AND {region_sql} AND {period_sql}
              AND ci.okpd2_code IS NOT NULL
              AND ci.sum_amount IS NOT NULL AND ci.sum_amount > 0
            GROUP BY ci.okpd2_code
            ORDER BY total_sum DESC LIMIT ?
        """, okpd2_params + region_params + period_params + [limit]).fetchall()

    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["share_pct"] = round(d["total_sum"] / sector_total * 100, 2) if sector_total else 0.0
        out.append(d)
    return out


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
