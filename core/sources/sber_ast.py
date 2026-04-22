"""Поиск на Сбербанк-АСТ (sberbank-ast.ru).

Публичный поиск коммерческих процедур. Часть площадок закрыта
без авторизации ЭЦП — видим только часть карточек.
Селекторы вероятно нужно будет подправить по факту.
"""
from playwright.sync_api import sync_playwright
from urllib.parse import quote
import re

BASE = "https://www.sberbank-ast.ru"
SEARCH_URL = f"{BASE}/Search.aspx"


def search(keyword: str, limit: int = 20, headless: bool = True) -> list[dict]:
    url = f"{SEARCH_URL}?query={quote(keyword)}"
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
            cards = page.query_selector_all("tr.search-result-row, .search-result, [class*='result-item']")
            for card in cards[:limit]:
                item = _parse(card)
                if item:
                    results.append(item)
        except Exception as e:
            print(f"[sber-ast] error for '{keyword}': {e}")
        finally:
            browser.close()
    return results


def _parse(card) -> dict | None:
    try:
        a = card.query_selector("a")
        if not a:
            return None
        title = a.inner_text().strip()
        href = a.get_attribute("href") or ""
        url = href if href.startswith("http") else BASE + ("/" if not href.startswith("/") else "") + href
        text = card.inner_text()
        m_id = re.search(r"№\s*([\w\-/]+)", text) or re.search(r"(\d{7,})", text)
        external_id = m_id.group(1) if m_id else url
        m_price = re.search(r"([\d\s]+[\d])\s*(?:руб|₽)", text)
        m_dl = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
        return {
            "source": "sberbank-ast.ru",
            "external_id": external_id,
            "title": title,
            "customer": "",
            "price": (m_price.group(1).strip() if m_price else ""),
            "deadline": m_dl.group(1) if m_dl else None,
            "url": url,
            "description": title,
        }
    except Exception as e:
        print(f"[sber-ast] parse error: {e}")
        return None
