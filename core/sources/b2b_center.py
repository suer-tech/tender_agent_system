"""Поиск на B2B-Center (b2b-center.ru).

Важно: полнотекстовый поиск идёт через параметр ?f_keyword=<...>, а не
?search= (при отправке ?search сайт просто возвращает последние лоты без
фильтрации). Колонки страницы результатов:
  [0] Название процедуры (категория + № + описание в .search-results-title-desc)
  [1] Организатор
  [2] Опубликовано  (дата публикации)
  [3] Актуально до (дата окончания подачи заявок — её и сохраняем)
"""
from playwright.sync_api import sync_playwright
from urllib.parse import quote
import re

BASE = "https://www.b2b-center.ru"
SEARCH_URL = f"{BASE}/market/"


_ROW_EXTRACTOR = """() => {
    const out = [];
    document.querySelectorAll('a.search-results-title').forEach(link => {
        const tr = link.closest('tr');
        if (!tr) return;
        const cells = Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || '').trim());
        const descEl = link.querySelector('.search-results-title-desc');
        const linkText = (link.innerText || '').trim();
        out.push({
            type_num_line: linkText.split('\\n')[0].trim(),
            description: descEl ? descEl.innerText.trim() : '',
            category: (cells[0] || '').split('\\n')[0].trim(),
            customer: cells[1] || '',
            published: cells[2] || '',
            deadline_raw: cells[3] || '',
            href: link.getAttribute('href') || '',
        });
    });
    return out;
}"""


def search(keyword: str, limit: int = 20, headless: bool = True) -> list[dict]:
    url = f"{SEARCH_URL}?f_keyword={quote(keyword)}"
    results: list[dict] = []
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
            try:
                page.wait_for_selector("a.search-results-title", timeout=15000)
            except Exception:
                print(f"[b2b] '{keyword}': карточек на странице нет")
                return results
            rows = page.evaluate(_ROW_EXTRACTOR)
            for r in rows[:limit]:
                item = _to_item(r)
                if item:
                    results.append(item)
        except Exception as e:
            print(f"[b2b] error for '{keyword}': {e}")
        finally:
            browser.close()
    return results


def _to_item(r: dict) -> dict | None:
    try:
        href = r.get("href") or ""
        url = href if href.startswith("http") else BASE + href
        m_id = (re.search(r"tender-(\d+)", href)
                or re.search(r"№\s*(\d+)", r.get("type_num_line") or ""))
        if not m_id:
            return None
        external_id = m_id.group(1)

        m_dl = re.search(r"(\d{2}\.\d{2}\.\d{4})", r.get("deadline_raw") or "")
        deadline = m_dl.group(1) if m_dl else None

        description = (r.get("description") or "").strip()
        type_num = (r.get("type_num_line") or "").strip()
        # В Telegram заголовком показываем суть (описание), а тип+номер дописываем
        # префиксом только если описание пустое. Длину ограничиваем, чтобы
        # карточка в телеге не была простыней.
        full_title = description or type_num
        if len(full_title) > 300:
            full_title = full_title[:297] + "..."

        # В description для LLM кладём категорию + описание + тип — максимум контекста.
        parts = []
        if r.get("category"):
            parts.append(f"Категория: {r['category']}")
        if type_num:
            parts.append(type_num)
        if description:
            parts.append(description)
        full_description = "\n".join(parts)

        return {
            "source": "b2b-center.ru",
            "external_id": external_id,
            "title": full_title,
            "customer": (r.get("customer") or "").strip(),
            "price": "",
            "deadline": deadline,
            "url": url,
            "description": full_description,
        }
    except Exception as e:
        print(f"[b2b] parse error: {e}")
        return None
