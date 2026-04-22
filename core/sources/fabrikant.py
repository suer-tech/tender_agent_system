"""Поиск на Фабриканте (fabrikant.ru).

Особенности:
- SPA на Next.js с React Server Streaming. `page.content()` часто не
  отдаёт реальный DOM — данные есть в innerText живого DOM, но не в
  сериализованном outerHTML. Работаем через `page.evaluate()`.
- URL поиска: `/procedure/search?query=<kw>` (найдено эмпирически,
  форма поиска с главной именно туда ведёт).
- Страница результатов возвращает и 44-ФЗ (ссылки `44.fabrikant.ru/44/...`),
  и коммерческие (`fabrikant.ru/v2/trades/...`). 44-ФЗ дублируют zakupki,
  поэтому берём ТОЛЬКО коммерческие — это и есть уникальная добавка
  Фабриканта (закупки СИБУР, Росатом, РЖД и прочих крупных коммерческих
  заказчиков).
- Ждём networkidle + появления «Дата окончания приёма заявок» в
  innerText — это сигнал, что карточки гидрированы.
"""
from pathlib import Path
from urllib.parse import quote
import re
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

BASE = "https://www.fabrikant.ru"
SEARCH_URL = f"{BASE}/procedure/search"

ROOT = Path(__file__).parent.parent.parent
STATE_DIR = ROOT / "data" / "fabrikant_state"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


_EXTRACT = r"""() => {
    const out = [];
    const seen = new Set();
    // только коммерческие — 44-ФЗ уже покрываются zakupki-парсером
    document.querySelectorAll('a[href*="/v2/trades/procedure/view/"]').forEach(a => {
        const href = a.getAttribute('href') || '';
        if (!href || seen.has(href)) return;
        seen.add(href);
        // идём вверх, пока не найдём контейнер, где уже есть "Дата окончания" —
        // это и будет карточка.
        let el = a;
        while (el && !/Дата окончания/.test(el.innerText || '')) {
            el = el.parentElement;
        }
        if (!el) return;
        out.push({
            href,
            link_text: (a.innerText || '').trim(),
            card_text: (el.innerText || '').trim(),
        });
    });
    return out;
}"""


def search(keyword: str, limit: int = 20, headless: bool = True) -> list[dict]:
    url = f"{SEARCH_URL}?query={quote(keyword)}"
    results: list[dict] = []
    STATE_DIR.mkdir(exist_ok=True)
    with Stealth().use_sync(sync_playwright()) as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(STATE_DIR),
            headless=headless,
            user_agent=UA,
            locale="ru-RU",
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            try:
                page.wait_for_function(
                    "() => /Дата окончания приёма заявок/.test(document.body.innerText)",
                    timeout=20000,
                )
            except Exception:
                print(f"[fabrikant] '{keyword}': карточки не появились")
                return results

            raw = page.evaluate(_EXTRACT)
            print(f"[fabrikant] '{keyword}': коммерческих карточек {len(raw)}")
            for r in raw[:limit]:
                item = _to_item(r)
                if item:
                    results.append(item)
        except Exception as e:
            print(f"[fabrikant] error for '{keyword}': {e}")
        finally:
            ctx.close()
    return results


def _to_item(r: dict) -> dict | None:
    href = r.get("href") or ""
    m = re.search(r"/procedure/view/([\w\-]+)", href)
    if not m:
        return None
    external_id = m.group(1)

    url = href if href.startswith("http") else ("https://fabrikant.ru" + href)

    text = r.get("card_text") or ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    def next_after(label: str) -> str:
        """Возвращает строку, идущую в innerText сразу после строки-метки."""
        for i, l in enumerate(lines):
            if l == label and i + 1 < len(lines):
                return lines[i + 1]
        return ""

    deadline_raw = next_after("Дата окончания приёма заявок")
    m_dl = re.search(r"(\d{2}\.\d{2}\.\d{4})", deadline_raw)
    deadline = m_dl.group(1) if m_dl else None

    customer = next_after("Заказчик")
    organizer = next_after("Организатор")

    # title — это текст ссылки (у Фабриканта — это описание/предмет закупки)
    title = (r.get("link_text") or "").strip()
    # fallback: строка-заголовок «Электронный аукцион№ …» / «Запрос …»
    type_line = ""
    for l in lines:
        if re.match(r"^(Электронный|Запрос|Конкурс|Тендер|Аукцион|Процедура)[^\n]*№", l):
            type_line = l
            break
    if not title:
        title = type_line

    # цена — ищем строку с «RUB» или «₽»
    price = ""
    for l in lines:
        if re.search(r"\d[\d\s]*(?:,\d+)?\s*(RUB|₽)", l):
            price = re.sub(r"\s+", " ", l).strip()
            break

    desc_parts = []
    if type_line:
        desc_parts.append(type_line)
    if title and title != type_line:
        desc_parts.append(title)
    if customer:
        desc_parts.append(f"Заказчик: {customer}")
    if organizer and organizer != customer:
        desc_parts.append(f"Организатор: {organizer}")
    description = "\n".join(desc_parts)

    return {
        "source": "fabrikant.ru",
        "external_id": external_id,
        "title": (title or type_line)[:500],
        "customer": customer,
        "price": price,
        "deadline": deadline,
        "url": url,
        "description": description,
    }
