"""Поиск на РТС-тендер (rts-tender.ru).

Особенности сайта:
- Anti-DDoS защита (заставка «Проверяем ваш браузер»). Обходится парой
  playwright-stealth + persistent context (куки/кэш копятся в ./rts_state/).
  Первый раз рекомендуется прогнать probe_rts.py в headful-режиме, чтобы
  сессия прогрелась и куки сохранились; после этого этот парсер работает
  headless.
- Прямой URL `/poisk/zakupki?searchString=...` при чистом заходе отдаёт 404
  (сайт проверяет сессию/referrer). Поэтому заходим на главную, находим
  поле «Введите ключевое слово или номер извещения», вбиваем ключ и жмём
  Enter — сайт сам строит правильный URL результатов.
- В превью карточки `.card-item` дата окончания подачи лежит в
  `.card-item__info-end-date time[itemprop=availabilityEnds]` — атрибут
  `datetime="22.04.2026 09:00:00 +03:00"`. На детальную ходить не нужно.
"""
from pathlib import Path
from urllib.parse import quote
import re
import time
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

BASE = "https://www.rts-tender.ru"
# /poisk/zakupki при ЧИСТОМ заходе даёт 404 (проверка referrer/сессии).
# Заходим на главную и уже там ищем через сайтовую форму — тогда сайт сам
# построит корректный URL результатов (/poisk/zakupki?searchString=... или
# /poisk/search?id=<guid>) и покажет карточки.
START_PAGE = BASE

ROOT = Path(__file__).parent.parent.parent
STATE_DIR = ROOT / "data" / "rts_state"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_SEARCH_INPUT = "input[placeholder*='Введите ключевое']"
_CARD = ".card-item"


def search(keyword: str, limit: int = 20, headless: bool = True) -> list[dict]:
    """Ищет тендеры на rts-tender по ключу. Первый раз требует headful-прогрева
    через probe_rts.py (куки Anti-DDoS сохраняются в rts_state/)."""
    STATE_DIR.mkdir(exist_ok=True)
    results: list[dict] = []
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
            page.goto(START_PAGE, wait_until="domcontentloaded", timeout=90000)
            _wait_antiddos(page, timeout_sec=30)
            page.wait_for_timeout(1200)

            if not _submit_search(page, keyword):
                print(f"[rts] '{keyword}': не удалось отправить поиск — нет поля ввода")
                return results

            try:
                page.wait_for_selector(_CARD, timeout=20000)
            except Exception:
                print(f"[rts] '{keyword}': карточек на странице нет (URL: {page.url})")
                return results

            cards_data = page.evaluate(_CARD_EXTRACTOR)
            print(f"[rts] '{keyword}': найдено карточек {len(cards_data)}")

            for cd in cards_data[:limit]:
                item = _to_item(cd)
                if item:
                    results.append(item)
        except Exception as e:
            print(f"[rts] error for '{keyword}': {e}")
        finally:
            ctx.close()
    return results


def _submit_search(page, keyword: str) -> bool:
    """Находим поле поиска на странице, заполняем ключом и жмём Enter.
    Поле может быть:
      - сразу видимым input с placeholder «Введите ключевое слово...»
      - скрытым до клика по иконке «лупа» (.search-icon, [class*=search])
    Возвращает True если форма отправилась (ждём навигацию)."""
    inp = page.query_selector(_SEARCH_INPUT)
    if not inp:
        # пробуем открыть поиск по кликам на явные триггеры
        for sel in (
            "header [class*='search'][class*='button']",
            "header [class*='search-toggle']",
            "header [class*='icon-search']",
            "header a[href*='poisk']",
            "[class*='magnifier']",
        ):
            try:
                trig = page.query_selector(sel)
            except Exception:
                trig = None
            if trig:
                try:
                    trig.click(timeout=2000)
                    page.wait_for_timeout(800)
                except Exception:
                    continue
                inp = page.query_selector(_SEARCH_INPUT)
                if inp:
                    break
    if not inp:
        return False
    try:
        inp.click()
        inp.fill(keyword)
        inp.press("Enter")
    except Exception as e:
        print(f"[rts] submit error: {e}")
        return False
    try:
        page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(2500)
    return True


def _wait_antiddos(page, timeout_sec: int = 30):
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
        except Exception:
            body = ""
        if "Anti-DDoS" not in body and "Проверяем ваш браузер" not in body:
            return
        page.wait_for_timeout(1500)


_CARD_EXTRACTOR = r"""() => {
    const out = [];
    document.querySelectorAll('.card-item').forEach(c => {
        const title_el = c.querySelector('.card-item__title');
        const title_link = c.querySelector('.card-item__title a, a.card-item__title');
        // ссылка ПОДРОБНЕЕ — внутренний стабильный путь /poisk/id/l<N>-...
        let detail_href = '';
        c.querySelectorAll('a[href]').forEach(a => {
            const h = a.getAttribute('href') || '';
            if (/\/poisk\/id\//.test(h) && !detail_href) detail_href = h;
        });
        const org_main = c.querySelector('.card-item__organization-main');
        // external_id: из detail_href /poisk/id/l4415698-... → 4415698,
        // либо из текста ссылки «Закупка №…».
        let ext = '';
        const m = detail_href.match(/\/poisk\/id\/l(\d+)/);
        if (m) ext = m[1];
        if (!ext) {
            const lbl = Array.from(c.querySelectorAll('a'))
                .map(a => (a.innerText || '').trim())
                .find(t => /Закупка\s*№/.test(t));
            if (lbl) {
                const m2 = lbl.match(/№\s*(\d+)/);
                if (m2) ext = m2[1];
            }
        }
        const props = {};
        c.querySelectorAll('.card-item__properties-cell').forEach(cell => {
            const name = cell.querySelector('.card-item__properties-name');
            const desc = cell.querySelector('.card-item__properties-desc');
            if (name && desc) {
                props[(name.innerText || '').trim().toLowerCase()] =
                    (desc.innerText || '').trim().replace(/\s+/g, ' ');
            }
        });
        // дедлайн — из превью: time[itemprop=availabilityEnds] внутри .card-item__info-end-date
        // формат datetime-атрибута: "22.04.2026 09:00:00 +03:00"
        let deadline_raw = '';
        const end_time = c.querySelector('.card-item__info-end-date time[itemprop="availabilityEnds"]');
        if (end_time) {
            deadline_raw = end_time.getAttribute('datetime') || (end_time.innerText || '').trim();
        }
        out.push({
            title: title_el ? (title_el.innerText || '').trim() : '',
            title_href: title_link ? title_link.getAttribute('href') : '',
            detail_href,
            external_id: ext,
            organization_main: org_main ? (org_main.innerText || '').trim() : '',
            price: props['начальная цена'] || '',
            status: props['статус'] || '',
            deadline_raw,
        });
    });
    return out;
}"""


def _to_item(cd: dict) -> dict | None:
    external_id = cd.get("external_id") or ""
    if not external_id:
        return None
    title = (cd.get("title") or "").strip()
    # organization_main содержит имя + "ИНН ... КПП ..." через перенос строк.
    # Берём первую непустую строку как имя заказчика, чистим «(все закупки)».
    org_raw = cd.get("organization_main") or ""
    customer_line = next(
        (l.strip() for l in org_raw.splitlines() if l.strip()),
        ""
    )
    customer = re.sub(r"\s*\(все закупки\)\s*$", "", customer_line)

    # url — стабильный внутренний путь /poisk/id/l<N>-... (detail_href).
    # title_href часто ведёт на внешние порталы-дочки rts-tender; менее стабилен.
    detail_href = cd.get("detail_href") or ""
    url = detail_href if detail_href.startswith("http") else (BASE + detail_href)
    if not detail_href:
        url = cd.get("title_href") or ""
        if url and url.startswith("/"):
            url = BASE + url

    # deadline: из атрибута datetime="22.04.2026 09:00:00 +03:00" → "22.04.2026"
    deadline = None
    dl_raw = cd.get("deadline_raw") or ""
    m_dl = re.search(r"(\d{2}\.\d{2}\.\d{4})", dl_raw)
    if m_dl:
        deadline = m_dl.group(1)

    desc_parts = [title]
    if cd.get("status"):
        desc_parts.append(f"Статус: {cd['status']}")
    if customer:
        desc_parts.append(f"Заказчик: {customer}")
    description = "\n".join([p for p in desc_parts if p])

    return {
        "source": "rts-tender.ru",
        "external_id": external_id,
        "title": title,
        "customer": customer,
        "price": cd.get("price") or "",
        "deadline": deadline,
        "url": url,
        "description": description,
    }


