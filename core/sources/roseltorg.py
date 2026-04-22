"""Поиск на Росэлторг (roseltorg.ru).

Важно: полнотекстовый поиск идёт через параметр ?query_field=<...>, а не
?q= (параметр q сайт игнорирует — возвращает случайные последние процедуры).
"""
from playwright.sync_api import sync_playwright
from urllib.parse import quote
import re

BASE = "https://www.roseltorg.ru"
SEARCH_URL = f"{BASE}/procedures/search"


def search(keyword: str, limit: int = 20, headless: bool = True) -> list[dict]:
    url = f"{SEARCH_URL}?query_field={quote(keyword)}"
    results = []
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
            page.wait_for_timeout(3000)
            items = page.query_selector_all(".search-results__item")
            for it in items[:limit]:
                card = _parse(it)
                if card:
                    results.append(card)
        except Exception as e:
            print(f"[roseltorg] error for '{keyword}': {e}")
        finally:
            browser.close()
    return results


def _parse(item) -> dict | None:
    try:
        title_el = item.query_selector("a.search-results__link--description")
        if not title_el:
            return None
        title = title_el.inner_text().strip()
        href = title_el.get_attribute("href") or ""
        url = href if href.startswith("http") else BASE + href

        m_id = re.search(r"/procedure/([\w\-]+)", href)
        external_id = m_id.group(1) if m_id else url

        # заказчик — имя ссылки <a> внутри .search-results__customer
        # (иначе захватываем заголовок «Организатор» + мусорные теги)
        cust_link = item.query_selector(".search-results__customer a")
        customer = cust_link.inner_text().strip() if cust_link else ""
        region_el = item.query_selector(".search-results__region")
        region = region_el.inner_text().strip() if region_el else ""

        # дедлайн — конкретный элемент .search-results__time внутри .search-results__timing
        # (иначе регулярка цеплялась за первую дату в тексте — могла быть дата обновления)
        dl_el = item.query_selector(".search-results__timing .search-results__time")
        dl_text = dl_el.inner_text().strip() if dl_el else ""
        m_dl = re.search(r"(\d{2}\.\d{2}\.\d{4})", dl_text or item.inner_text())
        deadline = m_dl.group(1) if m_dl else None

        sum_el = item.query_selector(".search-results__sum")
        sum_text = sum_el.inner_text().replace("\n", " ") if sum_el else ""
        # берём всё до ₽ и чистим множественные пробелы (вид «109 816 ,00 ₽»)
        if "₽" in sum_text:
            price = sum_text.split("₽")[0].strip() + " ₽"
            price = re.sub(r"\s+", " ", price)
        else:
            price = sum_text.strip()

        # описание для LLM — title + заказчик + регион + сумма (сутевой контекст)
        desc_parts = [title]
        if customer:
            desc_parts.append(f"Заказчик: {customer}")
        if region:
            desc_parts.append(f"Регион: {region}")
        if price:
            desc_parts.append(f"Начальная цена: {price}")
        description = "\n".join(desc_parts)

        return {
            "source": "roseltorg.ru",
            "external_id": external_id,
            "title": title,
            "customer": customer,
            "price": price,
            "deadline": deadline,
            "url": url,
            "description": description,
        }
    except Exception as e:
        print(f"[roseltorg] parse error: {e}")
        return None
