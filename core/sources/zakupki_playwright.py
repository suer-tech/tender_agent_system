"""Поиск на zakupki.gov.ru через Playwright.

URL расширенного поиска использует query-параметры:
    searchString=<keyword>
    fz44=on&fz223=on  — законы
    pageNumber=1
"""
from playwright.sync_api import sync_playwright
from urllib.parse import urlencode
import re

BASE = "https://zakupki.gov.ru"
SEARCH_URL = f"{BASE}/epz/order/extendedsearch/results.html"


def _build_url(keyword: str, law_types: list[str]) -> str:
    params = {
        "searchString": keyword,
        "morphology": "on",
        "search-filter": "Дате размещения",
        "sortBy": "UPDATE_DATE",
        "pageNumber": 1,
        "sortDirection": "false",
        "recordsPerPage": "_20",
        "showLotsInfoHidden": "false",
    }
    for law in law_types:
        params[f"fz{law}"] = "on"
    return f"{SEARCH_URL}?{urlencode(params, doseq=True)}"


def search(keyword: str, law_types=("44", "223"), limit: int = 20, headless: bool = True) -> list[dict]:
    results = []
    url = _build_url(keyword, list(law_types))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            locale="ru-RU",
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_selector(".search-registry-entry-block", timeout=20000)
            cards = page.query_selector_all(".search-registry-entry-block")
            for card in cards[:limit]:
                item = _parse_card(card)
                if item:
                    results.append(item)
            # если дедлайн не попал — дотягиваем из детальной страницы;
            # попутно отбрасываем закупки у единственного поставщика (туда не подаёмся).
            detail_page = ctx.new_page()
            to_drop: set[str] = set()
            for item in results:
                if item.get("deadline") or not item.get("url"):
                    continue
                try:
                    detail_page.goto(item["url"], wait_until="domcontentloaded", timeout=45000)
                    detail_page.wait_for_timeout(800)
                    dl = _deadline_from_detail(detail_page)
                    if dl:
                        item["deadline"] = dl
                        continue
                    method = _procurement_method(detail_page)
                    if _is_single_supplier(method):
                        to_drop.add(item["external_id"])
                        print(f"[zakupki] skip {item['external_id']}: {method[:60]}")
                except Exception as e:
                    print(f"[zakupki] detail {item.get('external_id')}: {e}")
            detail_page.close()
            if to_drop:
                results = [r for r in results if r["external_id"] not in to_drop]
        except Exception as e:
            print(f"[zakupki] error for '{keyword}': {e}")
        finally:
            browser.close()
    return results


def _procurement_method(page) -> str:
    """Читает поле «Способ осуществления закупки» с детальной страницы 223-ФЗ."""
    try:
        return page.evaluate("""() => {
            const nodes = document.querySelectorAll('.common-text__title');
            for (const t of nodes) {
                if (t.innerText.trim().toLowerCase().startsWith('способ осуществления закупки')) {
                    const v = t.parentElement && t.parentElement.querySelector('.common-text__value');
                    if (v) return v.innerText.trim();
                    const sib = t.nextElementSibling;
                    if (sib) return sib.innerText.trim();
                }
            }
            return '';
        }""") or ""
    except Exception:
        return ""


def _is_single_supplier(method: str) -> bool:
    """True для «Закупка у единственного поставщика» во всех вариантах
    (включая кириллическую/латинскую подмену «З[aа]купка»)."""
    if not method:
        return False
    m = method.replace("a", "а").lower()  # latin a → cyrillic а
    return "единственн" in m and any(w in m for w in ("поставщик", "подрядчик", "исполнител"))


_DEADLINE_LABELS = (
    "окончание подачи",
    "окончание срока подачи",
    "дата и время окончания срока подачи",
    "дата окончания срока подачи",
    "дата окончания подачи",
)


def _deadline_from_detail(page) -> str | None:
    # 1) строгий парсинг по label→value парам (работает для 44-ФЗ)
    pairs = page.evaluate("""() => {
        const r = [];
        document.querySelectorAll('.cardMainInfo__section').forEach(s => {
            const t = s.querySelector('.cardMainInfo__title');
            const v = s.querySelector('.cardMainInfo__content');
            if (t && v) r.push([t.innerText.trim(), v.innerText.trim()]);
        });
        const ts = document.querySelectorAll('.data-block__title');
        const vs = document.querySelectorAll('.data-block__value');
        for (let i = 0; i < Math.min(ts.length, vs.length); i++) {
            r.push([ts[i].innerText.trim(), vs[i].innerText.trim()]);
        }
        // 223-ФЗ: таблицы с th/td
        document.querySelectorAll('tr').forEach(tr => {
            const cells = tr.querySelectorAll('th, td');
            if (cells.length >= 2) {
                r.push([cells[0].innerText.trim(), cells[cells.length - 1].innerText.trim()]);
            }
        });
        return r;
    }""")
    for label, val in pairs:
        low = label.lower()
        if any(lbl in low for lbl in _DEADLINE_LABELS):
            m = re.search(r"\d{2}\.\d{2}\.\d{4}", val)
            if m:
                return m.group(0)

    # 2) fallback — поиск по всему innerText (223-ФЗ и прочая нестандартная разметка).
    # Ищем дату в пределах 200 символов после метки, чтобы не зацепить дату публикации.
    try:
        body = page.inner_text("body")
    except Exception:
        return None
    for lbl in _DEADLINE_LABELS:
        pat = re.escape(lbl) + r"[\s\S]{0,200}?(\d{2}\.\d{2}\.\d{4})"
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _collect_pairs(card) -> dict:
    """Собирает пары label→value из карточки.

    На странице результатов все .data-block__title и .data-block__value
    лежат сиблингами — соединяем по индексу. Дополнительно собираем
    cardMainInfo__section (на случай старой/иной разметки).
    """
    pairs = {}
    titles = card.query_selector_all(".data-block__title")
    values = card.query_selector_all(".data-block__value")
    for t, v in zip(titles, values):
        key = (t.inner_text() or "").strip().lower()
        val = (v.inner_text() or "").strip()
        if key and val:
            pairs[key] = val
    for s in card.query_selector_all(".cardMainInfo__section"):
        t = s.query_selector(".cardMainInfo__title")
        v = s.query_selector(".cardMainInfo__content")
        if t and v:
            key = (t.inner_text() or "").strip().lower()
            val = (v.inner_text() or "").strip()
            if key and val:
                pairs.setdefault(key, val)
    return pairs


def _by_substr(pairs: dict, *substrs: str) -> str | None:
    for key, val in pairs.items():
        for s in substrs:
            if s.lower() in key:
                return val
    return None


def _parse_card(card) -> dict | None:
    try:
        num_el = (
            card.query_selector(".registry-entry__header-mid__number a")
            or card.query_selector(".cardMainInfo__purchaseLink a")
        )
        external_id = ""
        href = None
        if num_el:
            external_id = (num_el.inner_text() or "").lstrip("№ ").strip()
            href = num_el.get_attribute("href")

        if not href or href == "#":
            print_link = card.query_selector("a[href*='regNumber=']")
            if print_link:
                h = print_link.get_attribute("href") or ""
                m = re.search(r"regNumber=(\d+)", h)
                if m:
                    external_id = external_id or m.group(1)
                    href = f"/epz/order/notice/printForm/view.html?regNumber={m.group(1)}"

        url = (BASE + href) if href and href.startswith("/") else href

        # заголовок (объект закупки)
        title_el = card.query_selector(".registry-entry__body-value")
        title = title_el.inner_text().strip() if title_el else ""

        # заказчик
        cust_el = card.query_selector(".registry-entry__body-href a")
        customer = cust_el.inner_text().strip() if cust_el else ""

        # цена
        price_el = card.query_selector(".price-block__value")
        price_val = price_el.inner_text().strip() if price_el else ""

        # пары label→value для дедлайна
        pairs = _collect_pairs(card)
        deadline_raw = _by_substr(pairs, "окончание подачи", "окончание срока подачи")
        deadline = None
        if deadline_raw:
            m = re.search(r"\d{2}\.\d{2}\.\d{4}", deadline_raw)
            deadline = m.group(0) if m else None

        if not external_id:
            return None
        return {
            "source": "zakupki.gov.ru",
            "external_id": external_id,
            "title": title,
            "customer": customer,
            "price": price_val,
            "deadline": deadline,
            "url": url,
            "description": title,
        }
    except Exception as e:
        print(f"[zakupki] parse error: {e}")
        return None
