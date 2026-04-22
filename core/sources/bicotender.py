"""Глубокий скрапер Bicotender.ru.

Стратегия поиска:
- Используем прямые GET-параметры URL (форма на bicotender — method=GET)
- Рабочий URL: /tender/search/?keywords=...&submit=1
- Результаты — HTML-таблица с <tr> строками (class="mark-link" для ссылок)
- Карточки тендеров: /category/name-tender{ID}.html
- Если есть BICOTENDER_LOGIN/PASSWORD в .env — логинимся для доступа к
  фильтрам и документам
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, BrowserContext
from playwright_stealth import Stealth

ROOT = Path(__file__).parent.parent.parent
load_dotenv(ROOT / ".env")

STATE_DIR = ROOT / "data" / "bicotender_state"
DOWNLOAD_DIR = ROOT / "data" / "bicotender_docs"

BASE = "https://www.bicotender.ru"
SEARCH_URL = f"{BASE}/tender/search/"
LOGIN_URL = f"{BASE}/login/"

BICO_LOGIN = os.getenv("BICOTENDER_LOGIN", "")
BICO_PASSWORD = os.getenv("BICOTENDER_PASSWORD", "")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# --- JS-экстрактор карточек из таблицы результатов ---
_EXTRACT_CARDS = r"""() => {
    const cards = [];
    const rows = document.querySelectorAll('tr');
    for (const tr of rows) {
        const link = tr.querySelector('a.mark-link');
        if (!link) continue;
        const href = link.getAttribute('href') || '';
        const m = href.match(/tender(\d+)\.html/);
        if (!m) continue;

        // Собираем данные из ячеек <td>
        const tds = tr.querySelectorAll('td.sm-row');
        const getText = (idx) => tds[idx] ? (tds[idx].innerText || '').trim() : '';

        // td[0] = название, td[1] = тип, td[2] = цена, td[3] = даты, td[4] = регион, td[5] = отрасль
        cards.push({
            tender_id: m[1],
            href: href,
            title: (link.getAttribute('title') || link.innerText || '').trim(),
            type_text: getText(1),
            price_text: getText(2),
            dates_text: getText(3),
            region_text: getText(4),
            industry_text: getText(5),
        });
    }
    return cards;
}"""

# --- JS-экстрактор полной информации со страницы-карточки тендера ---
_EXTRACT_DETAIL = r"""() => {
    const result = {};
    const body = document.body.innerText || '';
    result.full_text = body.substring(0, 15000);

    // === ДОКУМЕНТЫ ===
    // Bicotender хранит документы в блоке [data-documentation-block]
    // Ссылки имеют href="#" и data-widget="tc/tender/show/FileLimitAlert"
    // Файлы идентифицируются через data-file-id на чекбоксах
    const docs = [];
    const docBlock = document.querySelector('[data-documentation-block]');

    if (docBlock) {
        // Способ 1: чекбоксы с data-file-id (основной на bicotender)
        docBlock.querySelectorAll('input[data-file-id]').forEach(input => {
            const fileId = input.getAttribute('data-file-id');
            const size = input.getAttribute('data-file-size') || '';
            let fileName = '';
            let el = input.parentElement;
            while (el && !el.classList.contains('lineDoc') &&
                   !el.classList.contains('tender-inf__tabl_line')) {
                el = el.parentElement;
            }
            if (el) {
                const nameEl = el.querySelector('.tender-inf__tabl-columDocTxt a') ||
                               el.querySelector('a[data-widget]') || el.querySelector('a');
                fileName = nameEl ? nameEl.innerText.trim() : '';
            }
            if (!fileName) {
                const t = (input.closest('.docFl') || input.closest('div') || {}).innerText || '';
                const m = t.match(/[\w\u0400-\u04FF\-_.]+\.(docx?|pdf|xlsx?|zip|rar|rtf)/i);
                if (m) fileName = m[0];
            }
            if (fileId) {
                docs.push({
                    file_id: fileId,
                    text: fileName,
                    size: size,
                    type: 'bicotender_file_id',
                });
            }
        });

        // Способ 2: кнопка "Скачать всё"
        const downloadAll = docBlock.querySelector('[data-action="downloadAll"]');
        if (downloadAll) {
            result.has_download_all = true;
            result.download_limit_msg = downloadAll.getAttribute('data-description') || '';
        }
    }

    // Способ 3: обычные ссылки на файлы (для других площадок)
    const seen = new Set();
    const fileSel = 'a[href$=".pdf"], a[href$=".doc"], a[href$=".docx"], ' +
        'a[href$=".xlsx"], a[href$=".xls"], a[href$=".zip"], a[href$=".rar"]';
    document.querySelectorAll(fileSel).forEach(a => {
        const href = a.href || a.getAttribute('href') || '';
        if (!href || href === '#' || seen.has(href)) return;
        seen.add(href);
        docs.push({
            href,
            text: (a.innerText || '').trim(),
            type: 'direct_link',
        });
    });

    result.documents = docs;
    result.tender_id = (docBlock || {}).getAttribute
        ? docBlock.getAttribute('data-tender-id') || ''
        : '';

    // Ссылка на первоисточник
    const srcSel = 'a[href*="zakupki.gov"], a[href*="rts-tender"], a[href*="roseltorg"], ' +
                   'a[href*="sberbank-ast"], a[href*="b2b-center"], a[href*="fabrikant"]';
    result.source_links = [];
    for (const a of document.querySelectorAll(srcSel)) {
        result.source_links.push({
            href: a.href || a.getAttribute('href') || '',
            text: (a.innerText || '').trim(),
        });
    }
    return result;
}"""


def _launch_context(pw, headless: bool) -> BrowserContext:
    STATE_DIR.mkdir(exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(STATE_DIR),
        headless=headless,
        user_agent=UA,
        locale="ru-RU",
        viewport={"width": 1400, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
        accept_downloads=True,
    )


def _ensure_logged_in(page: Page) -> bool:
    """Проверяет авторизацию и логинится если нужно. Возвращает True если залогинен."""
    if not BICO_LOGIN or not BICO_PASSWORD:
        return False

    # Проверяем, залогинены ли уже (persistent context хранит куки)
    is_logged = page.evaluate("() => !!window.Bc_isLoggedIn && window.Bc_isLoggedIn !== 0")
    if is_logged:
        print("[bicotender] уже авторизован")
        return True

    print(f"[bicotender] логинюсь как {BICO_LOGIN}...")
    try:
        # Форма логина есть прямо на странице поиска (наверху)
        login_input = page.query_selector("input#login")
        pwd_input = page.query_selector("input#password")

        if login_input and pwd_input and login_input.is_visible():
            login_input.fill(BICO_LOGIN)
            pwd_input.fill(BICO_PASSWORD)
            # Кнопка входа
            submit = page.query_selector("input.lkb[type='submit']")
            if submit:
                submit.click()
            else:
                pwd_input.press("Enter")

            page.wait_for_timeout(3000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            is_logged = page.evaluate(
                "() => !!window.Bc_isLoggedIn && window.Bc_isLoggedIn !== 0"
            )
            if is_logged:
                print("[bicotender] авторизация успешна")
                return True
            else:
                print("[bicotender] авторизация не удалась (проверьте логин/пароль)")
                return False
        else:
            # Форма не видна — идём на страницу логина
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            _wait_ready(page)
            login_input = page.query_selector("input#login, input[name='login']")
            pwd_input = page.query_selector("input#password, input[name='password']")
            if login_input and pwd_input:
                login_input.fill(BICO_LOGIN)
                pwd_input.fill(BICO_PASSWORD)
                pwd_input.press("Enter")
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                print("[bicotender] логин отправлен")
                return True
    except Exception as e:
        print(f"[bicotender] ошибка авторизации: {e}")

    return False


def _build_search_url(
    keyword: str,
    price_from: int | None = None,
    price_to: int | None = None,
    status: str = "active",
    on_page: int = 50,
) -> str:
    """Строит URL поиска через GET-параметры (без авторизации)."""
    params = {
        "keywords": keyword,
        "keywordsStrict": "0",
        "smartSearch": "0",
        "regionPreference": "0",
        "submit": "1",
        "on_page": str(on_page),
    }
    if price_from is not None:
        params["costRub[from]"] = str(price_from)
    if price_to is not None:
        params["costRub[to]"] = str(price_to)
    # Статус: status_id-3 = Активный (приём заявок)
    if status == "active":
        params["status_id[]"] = "3"

    return SEARCH_URL + "?" + urlencode(params, doseq=True)


def search(keyword: str, limit: int = 20, headless: bool = True) -> list[dict]:
    """Поиск тендеров по ключевому слову через прямой URL."""
    return search_with_filters(keyword=keyword, limit=limit, headless=headless)


def search_with_filters(
    keyword: str,
    industry: str | None = None,
    region: str | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    status: str = "active",
    limit: int = 20,
    headless: bool = True,
) -> list[dict]:
    """Поиск с фильтрами через GET-параметры URL."""
    url = _build_search_url(
        keyword=keyword,
        price_from=price_from,
        price_to=price_to,
        status=status,
        on_page=min(limit, 100),
    )
    print(f"[bicotender] URL: {url[:120]}...")

    results: list[dict] = []
    with Stealth().use_sync(sync_playwright()) as p:
        ctx = _launch_context(p, headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            # Автологин (если заданы BICOTENDER_LOGIN/PASSWORD)
            if BICO_LOGIN:
                page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
                _wait_ready(page)
                _ensure_logged_in(page)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            _wait_ready(page)

            raw = page.evaluate(_EXTRACT_CARDS)
            print(f"[bicotender] '{keyword}': карточек {len(raw)}")

            for r in raw[:limit]:
                item = _card_to_item(r)
                if item:
                    results.append(item)
        except Exception as e:
            print(f"[bicotender] search error: {e}")
        finally:
            ctx.close()
    return results


def fetch_detail(url: str, headless: bool = True) -> dict:
    """Открывает карточку тендера и извлекает полную информацию + документы."""
    if not url.startswith("http"):
        url = BASE + url
    detail: dict = {"url": url, "full_text": "", "documents": [], "source_links": []}
    with Stealth().use_sync(sync_playwright()) as p:
        ctx = _launch_context(p, headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            # Логин (persistent context хранит куки, но первый запуск требует)
            if BICO_LOGIN:
                page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
                _wait_ready(page)
                _ensure_logged_in(page)

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            _wait_ready(page)
            time.sleep(1)

            raw = page.evaluate(_EXTRACT_DETAIL)
            detail["full_text"] = raw.get("full_text", "")
            detail["documents"] = raw.get("documents", [])
            detail["source_links"] = raw.get("source_links", [])
        except Exception as e:
            print(f"[bicotender] detail error for {url}: {e}")
        finally:
            ctx.close()
    return detail


def download_documents(
    doc_links: list[dict],
    tender_id: str,
    headless: bool = True,
    max_docs: int = 5,
    tender_url: str = "",
) -> list[Path]:
    """Скачивает документы. Поддерживает два режима:

    1. Bicotender file_id — кликает "Скачать всё" на странице карточки
    2. Прямые ссылки — скачивает по href
    """
    out_dir = DOWNLOAD_DIR / tender_id
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    if not doc_links:
        return downloaded

    # Разделяем по типу
    bico_files = [d for d in doc_links if d.get("type") == "bicotender_file_id"]
    direct_links = [d for d in doc_links if d.get("type") == "direct_link"]

    with Stealth().use_sync(sync_playwright()) as p:
        ctx = _launch_context(p, headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            # Логин
            if BICO_LOGIN:
                page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
                _wait_ready(page)
                _ensure_logged_in(page)

            # === Режим 1: Bicotender file_id — скачиваем через клик на файл ===
            if bico_files and tender_url:
                print(f"[bicotender] {len(bico_files)} файлов на странице, пробую скачать")
                page.goto(tender_url, wait_until="domcontentloaded", timeout=60000)
                _wait_ready(page)

                for doc in bico_files[:max_docs]:
                    file_id = doc.get("file_id", "")
                    fname = doc.get("text", f"doc_{file_id}")
                    if not file_id:
                        continue
                    try:
                        # Ищем ссылку на файл в строке документа
                        link = page.query_selector(
                            f'input[data-file-id="{file_id}"]'
                        )
                        if not link:
                            print(f"[bicotender] file_id={file_id}: checkbox not found")
                            continue

                        # Находим кликабельную ссылку в той же строке
                        file_link = page.evaluate(f"""(fileId) => {{
                            const inp = document.querySelector('input[data-file-id="' + fileId + '"]');
                            if (!inp) return null;
                            let el = inp.parentElement;
                            while (el && !el.classList.contains('lineDoc') &&
                                   !el.classList.contains('tender-inf__tabl_line')) {{
                                el = el.parentElement;
                            }}
                            if (!el) return null;
                            const a = el.querySelector('.tender-inf__tabl-columDocTxt a') ||
                                      el.querySelector('a[data-widget]');
                            return a ? true : false;
                        }}""", file_id)

                        if file_link:
                            # Кликаем по ссылке файла и ловим download
                            js_click = f"""() => {{
                                const inp = document.querySelector('input[data-file-id="{file_id}"]');
                                let el = inp.parentElement;
                                while (el && !el.classList.contains('lineDoc')) el = el.parentElement;
                                const a = el.querySelector('.tender-inf__tabl-columDocTxt a') || el.querySelector('a');
                                if (a) a.click();
                            }}"""
                            try:
                                with page.expect_download(timeout=15000) as dl_info:
                                    page.evaluate(js_click)
                                dl = dl_info.value
                                target = out_dir / (dl.suggested_filename or fname)
                                dl.save_as(str(target))
                                downloaded.append(target)
                                print(f"[bicotender] skachan: {target.name} ({target.stat().st_size}b)")
                            except Exception as click_err:
                                # Модалка "суточный лимит" — закроем и запишем причину
                                _close_modal(page)
                                # Проверяем текст модалки
                                modal_text = page.evaluate("""() => {
                                    const m = document.querySelector('.ui-dialog, .modal-full-screen, .ui-popup-wrapper');
                                    return m ? m.innerText.substring(0, 200) : '';
                                }""") or ""
                                if "лимит" in modal_text.lower() or "ограничен" in modal_text.lower():
                                    print(f"[bicotender] file {file_id}: tariff limit (daily quota exceeded)")
                                    # Записываем причину для диагностики
                                    doc["_error"] = "tariff_limit"
                                    break  # Все файлы будут блокированы
                                else:
                                    err_str = str(click_err)[:80].encode("ascii", "replace").decode()
                                    print(f"[bicotender] file {file_id}: download failed - {err_str}")
                                    doc["_error"] = "download_failed"
                    except Exception as e2:
                        err_str = str(e2)[:120].encode("ascii", "replace").decode()
                        print(f"[bicotender] file {file_id}: {err_str}")

            # === Режим 2: Прямые ссылки ===
            for doc in direct_links[:max_docs]:
                href = doc.get("href", "")
                if not href or href == "#":
                    continue
                if not href.startswith("http"):
                    href = BASE + href
                try:
                    with page.expect_download(timeout=20000) as dl_info:
                        page.goto(href, timeout=20000)
                    download = dl_info.value
                    fname = download.suggested_filename or f"doc_{len(downloaded)}"
                    target = out_dir / fname
                    download.save_as(str(target))
                    downloaded.append(target)
                    print(f"[bicotender] скачан: {fname}")
                except Exception:
                    try:
                        resp = page.goto(href, timeout=20000)
                        if resp and resp.headers.get("content-type", "").startswith(("application/",)):
                            ct = resp.headers.get("content-type", "")
                            ext = _ext_from_ct(ct)
                            fname = f"doc_{len(downloaded)}{ext}"
                            target = out_dir / fname
                            target.write_bytes(resp.body())
                            downloaded.append(target)
                    except Exception as e2:
                        print(f"[bicotender] не удалось скачать {href[:60]}: {e2}")
        finally:
            ctx.close()
    return downloaded


def search_and_collect(
    keyword: str,
    limit: int = 10,
    headless: bool = True,
    max_docs_per_tender: int = 5,
) -> list[dict]:
    """Полный цикл: поиск → карточки → детали → документы."""
    cards = search(keyword, limit=limit, headless=headless)
    enriched: list[dict] = []

    for i, card in enumerate(cards):
        print(f"[bicotender] обработка {i + 1}/{len(cards)}: {card.get('title', '')[:60]}")
        url = card.get("url", "")
        if not url:
            continue

        detail = fetch_detail(url, headless=headless)
        card["detail_text"] = detail.get("full_text", "")
        card["source_links"] = detail.get("source_links", [])

        doc_links = detail.get("documents", [])
        card["doc_files"] = download_documents(
            doc_links,
            tender_id=card.get("external_id", str(i)),
            headless=headless,
            max_docs=max_docs_per_tender,
            tender_url=url,
        )
        enriched.append(card)

    return enriched


# ---------- helpers ----------

def _close_modal(page: Page):
    """Закрывает модальное окно bicotender (лимит тарифа и т.д.)."""
    try:
        # Пробуем кнопки закрытия
        for sel in [
            'button.ui-dialog-titlebar-close',
            '.ui-popup-wrapper .ui-button',
            'button:has-text("OK")',
            'button:has-text("Закрыть")',
            'button:has-text("Close")',
            '.modal-close',
        ]:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(500)
                return
        # Fallback: убираем модалку через JS
        page.evaluate("() => { document.querySelectorAll('.ui-popup-wrapper, .ui-widget-overlay').forEach(e => e.remove()); }")
    except Exception:
        pass


def _wait_ready(page: Page, timeout: int = 15000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(1000)


def _card_to_item(r: dict) -> dict | None:
    tid = r.get("tender_id")
    if not tid:
        return None
    href = r.get("href", "")
    url = href if href.startswith("http") else (BASE + href)

    title = r.get("title", "").strip()
    price = r.get("price_text", "").strip()
    dates_text = r.get("dates_text", "")
    region = r.get("region_text", "").strip()
    industry = r.get("industry_text", "").strip()
    type_text = r.get("type_text", "").strip()

    # Извлекаем даты из dates_text (формат: "10 дней\n17.04.2026\n27.04.2026")
    dates = re.findall(r"(\d{2}\.\d{2}\.\d{4})", dates_text)
    start_date = dates[0] if len(dates) >= 1 else None
    deadline = dates[1] if len(dates) >= 2 else (dates[0] if dates else None)

    # Извлекаем чистую цену
    price_clean = price
    # Убираем "Обеспечение заявки: ..." и прочие доп. строки
    if "\n" in price_clean:
        price_clean = price_clean.split("\n")[0].strip()

    customer = ""  # На странице поиска заказчик не показан, будет из detail

    description_parts = [title]
    if type_text:
        description_parts.append(f"Тип: {type_text}")
    if region:
        description_parts.append(f"Регион: {region}")
    if industry:
        description_parts.append(f"Отрасль: {industry}")
    description = "\n".join(description_parts)

    return {
        "source": "bicotender",
        "external_id": tid,
        "title": title[:500],
        "customer": customer,
        "price": price_clean,
        "deadline": deadline,
        "start_date": start_date,
        "url": url,
        "description": description,
        "region": region,
        "industry": industry,
        "tender_type": type_text,
    }


def _ext_from_ct(content_type: str) -> str:
    ct = content_type.lower()
    if "pdf" in ct:
        return ".pdf"
    if "word" in ct or "docx" in ct:
        return ".docx"
    if "excel" in ct or "spreadsheet" in ct:
        return ".xlsx"
    if "zip" in ct:
        return ".zip"
    if "html" in ct:
        return ".html"
    return ".bin"
