"""Диалоговый агент для веб-интерфейса поиска тендеров.

Агент ведёт диалог с пользователем:
1. Понимает запрос на естественном языке
2. Уточняет детали при необходимости (отрасль, бюджет, регион)
3. Строит семантическую карту ключевых слов
4. Ищет по ВСЕМ площадкам (bicotender + российские) с авто-VPN
5. Читает документы, анализирует через Claude
6. Выдаёт структурированные результаты
"""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.sources import bicotender
from core.agents.bicotender_agent import parse_document


# --------------- Отрасли Bicotender ---------------

INDUSTRIES = """
Доступные отрасли на Bicotender (выбери наиболее подходящую):
- Автотехника
- Безопасность и охрана
- Бытовая техника и электроника
- Геология, экология, геодезия
- Добыча полезных ископаемых
- IT, компьютеры - Компьютерная техника
- IT, компьютеры - Программное обеспечение
- IT, компьютеры - Связь и телекоммуникации
- IT, компьютеры - Информационные технологии
- Канцтовары, офисная техника
- Лёгкая промышленность
- Лесное хозяйство
- Маркетинг, реклама, PR
- Медицина, фармацевтика
- Металлургия
- Мебель, интерьер
- Наука, образование
- Недвижимость, земельные участки
- Нефтегазовая отрасль
- Оборудование
- Охрана окружающей среды
- Пищевая промышленность
- Сельское хозяйство
- Страхование
- Строительство
- Топливо и энергетика
- Транспорт, логистика
- Туризм, спорт
- Финансы, банки, аудит
- Химическая промышленность
- Юридические услуги, консалтинг
"""


# --------------- System prompt ---------------

SYSTEM_PROMPT = textwrap.dedent("""\
    Ты — универсальный ИИ-агент по поиску тендеров на площадке Bicotender.ru.
    Ты помогаешь пользователям находить релевантные тендеры по ЛЮБОЙ тематике:
    строительство, IT, медицина, поставки, услуги, оборудование — что угодно.

    ТВОЯ ЗАДАЧА:
    1. Понять, что именно ищет пользователь (тема, отрасль, бюджет, регион)
    2. При необходимости задать 1-2 уточняющих вопроса (но не больше!)
    3. Построить СЕМАНТИЧЕСКУЮ КАРТУ поиска — набор ключевых слов,
       покрывающих тему с разных сторон
    4. Запустить поиск

    ВАЖНЫЕ ПРАВИЛА:
    - Если запрос достаточно ясен — сразу приступай к поиску
    - Если пользователь говорит "давай" или "ищи" — немедленно запускай поиск
    - Говори кратко и по делу, на русском языке
    - Ты НЕ ограничен одной отраслью — ищи по любой теме

    КАК СТРОИТЬ СЕМАНТИЧЕСКУЮ КАРТУ КЛЮЧЕВЫХ СЛОВ:
    Для каждого запроса нужно ПОДУМАТЬ и составить набор из 3-6 ключевых
    слов/фраз, которые покрывают тему МАКСИМАЛЬНО ШИРОКО:

    1. ПРЯМЫЕ ТЕРМИНЫ — то, что пользователь назвал напрямую
    2. СИНОНИМЫ И ПЕРЕФОРМУЛИРОВКИ — то же самое другими словами
    3. КОНКРЕТНЫЕ ПОДКАТЕГОРИИ — частные случаи в рамках темы
    4. ПРИКЛАДНЫЕ ЗАДАЧИ — что именно нужно сделать
    5. ТЕНДЕРНАЯ ЛЕКСИКА — как это формулируют заказчики в тендерах
       (часто отличается от бытовой речи)

    Примеры семантических карт:
    - "ИИ для бизнеса" →
      ["искусственный интеллект", "машинное обучение", "нейросеть",
       "чат-бот", "цифровизация", "интеллектуальная система"]
    - "ремонт дорог в Москве" →
      ["ремонт дорог", "содержание дорог", "асфальтирование",
       "дорожное покрытие", "капитальный ремонт автодороги"]
    - "поставка медицинского оборудования" →
      ["медицинское оборудование", "медтехника", "поставка медизделий",
       "диагностическое оборудование", "лабораторное оборудование"]
    - "охрана объектов" →
      ["охранные услуги", "физическая охрана", "пультовая охрана",
       "ЧОП", "обеспечение безопасности объектов"]
    - "клининг" →
      ["уборка помещений", "клининговые услуги", "техническое обслуживание зданий",
       "содержание помещений", "санитарное обслуживание"]

    Цель: не пропустить тендеры, где тема называется по-другому.
    Каждое слово — отдельный запрос на bicotender, результаты объединяются
    и дедуплицируются. Затем ИИ анализирует каждый на релевантность.

    {industries}

    КОГДА ГОТОВ К ПОИСКУ — включи в ответ блок:
    ```search
    {{
        "keywords": ["слово 1", "слово 2", "слово 3", "слово 4"],
        "price_from": null,
        "price_to": null,
        "status": "active",
        "search_mode": "all"
    }}
    ```

    Поля:
    - keywords: семантическая карта из 3-6 фраз (ОБЯЗАТЕЛЬНО)
    - price_from/price_to: бюджет в рублях (или null)
    - status: "active" (по умолчанию)
    - search_mode: "all" (все площадки, вкл. госзакупки) или "bicotender" (только Bicotender).
      По умолчанию "all" — ищем везде.

    Перед блоком search кратко объясни пользователю свою стратегию поиска:
    какие слова выбрал и почему.
""").format(industries=INDUSTRIES)


# --------------- Промпт для анализа тендера ---------------

TENDER_ANALYSIS_PROMPT = textwrap.dedent("""\
    Ты — эксперт-аналитик тендеров. Проанализируй тендер ниже.
    У тебя есть описание со страницы тендера и содержимое прикреплённых документов.

    Запрос пользователя: {user_query}

    Оцени, насколько этот тендер соответствует запросу пользователя.
    Учитывай тематику, отрасль, требования и специфику запроса.

    Ответь СТРОГО валидным JSON:
    {{
        "relevant": true|false,
        "score": 0-10,
        "summary": "2-3 предложения — суть закупки",
        "law_type": "44-ФЗ / 223-ФЗ / Коммерческий / Не определено",
        "key_requirements": ["требование 1", "требование 2"],
        "mandatory_conditions": ["обязательное условие 1", "условие 2"],
        "budget": "бюджет",
        "deadline_info": "дата начала — дата окончания приёма заявок",
        "qualification": "требования к участнику",
        "tech_stack": "упомянутые технологии",
        "risks": "риски",
        "recommendation": "рекомендация",
        "reason": "обоснование оценки"
    }}

    mandatory_conditions — это ОБЯЗАТЕЛЬНЫЕ условия заказчика, найденные
    в документах: лицензии, допуски, SLA, гарантийные сроки, штрафы,
    обеспечение заявки/контракта, сроки исполнения и т.д.

    === ТЕНДЕР ===
    Название: {title}
    Заказчик: {customer}
    Цена: {price}
    Дедлайн: {deadline}
    URL: {url}

    === ОПИСАНИЕ ===
    {detail_text}

    === ДОКУМЕНТЫ ===
    {documents_text}
""")


SUMMARY_PROMPT = textwrap.dedent("""\
    Ты — эксперт-аналитик тендеров. Сформируй ИТОГОВЫЙ ОТЧЁТ по найденным тендерам.

    Запрос пользователя: {user_query}

    Данные по каждому тендеру (JSON):
    {data}

    Сформируй краткий отчёт в виде текста (НЕ JSON, НЕ markdown-таблицы):

    1. Краткая сводка: сколько найдено, сколько соответствуют запросу
    2. Главные находки: самые интересные тендеры для пользователя
    3. Общие тренды: что объединяет найденные тендеры
    4. На что обратить внимание: ключевые требования, сроки, риски

    Будь конкретен и лаконичен. Не повторяй детали, которые уже есть в карточках.
    Пиши на русском.
""")


# --------------- Session ---------------

@dataclass
class Session:
    session_id: str
    history: list[dict] = field(default_factory=list)
    search_params: dict | None = None
    state: str = "chatting"  # chatting | searching | analyzing | done
    title_generated: bool = False


# --------------- ChatAgent ---------------

class ChatAgent:
    def __init__(self, session: Session):
        self.session = session

    def respond(self, user_msg: str) -> dict:
        """Обрабатывает сообщение пользователя. Возвращает dict с text и/или search_command."""
        # Формируем промпт с историей
        history_text = ""
        # Берём последние 10 сообщений для контекста
        for msg in self.session.history[-10:]:
            role = "Пользователь" if msg["role"] == "user" else "Ассистент"
            history_text += f"{role}: {msg['content']}\n\n"

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"=== ИСТОРИЯ ДИАЛОГА ===\n{history_text}\n"
            f"Ответь на последнее сообщение пользователя."
        )

        raw = _call_claude(prompt, timeout=60)
        if not raw:
            return {"text": "Извините, не удалось получить ответ. Попробуйте ещё раз."}

        # Ищем блок ```search в ответе
        search_match = re.search(
            r"```search\s*\n(.*?)\n```",
            raw,
            re.DOTALL,
        )

        if search_match:
            try:
                search_cmd = json.loads(search_match.group(1))
                # Текст до блока search
                text_before = raw[:search_match.start()].strip()
                self.session.search_params = search_cmd
                self.session.state = "searching"
                return {"text": text_before, "search_command": search_cmd}
            except json.JSONDecodeError:
                pass

        return {"text": raw.strip()}

    def respond_during_search(self, user_msg: str) -> dict:
        """Ответ пользователю пока поиск тендеров идёт в фоне.

        LLM видит контекст: «ты уже запустил поиск по таким-то ключевым словам,
        он идёт в фоне». Не инициирует новый поиск, отвечает коротко по теме
        (статус, вопросы о тендерах, болтовня).
        """
        from core import llm as _llm

        last_search = self.session.search_params or {}
        kws = last_search.get("keywords", [])

        history_text = ""
        for msg in self.session.history[-6:]:
            role = "Пользователь" if msg["role"] == "user" else "Ассистент"
            history_text += f"{role}: {msg['content']}\n\n"

        prompt = (
            "Ты — ИИ-ассистент для поиска тендеров. Прямо сейчас в фоне идёт "
            "поиск тендеров по ключевым словам: "
            f"{', '.join(kws) if kws else '(неизвестно)'}.\n\n"
            "Пользователь задал вопрос пока поиск не закончился. Ответь коротко "
            "и по делу — не запускай новый поиск. Если спрашивает о статусе — "
            "скажи что поиск ещё идёт и результаты скоро будут. На другие "
            "вопросы отвечай обычным образом, но тоже коротко (1-3 предложения).\n\n"
            "НЕ используй блок ```search``` в ответе — он уже работает.\n\n"
            f"=== ИСТОРИЯ ДИАЛОГА ===\n{history_text}\n"
            f"Ответь пользователю кратко."
        )

        raw = _llm.call_text(prompt, timeout=30, max_tokens=300)
        if not raw:
            return {"text": "Подождите, поиск ещё идёт. Результаты появятся через минуту."}
        return {"text": raw.strip()}

    def execute_search(
        self,
        params: dict,
        progress_callback=None,
    ) -> list[dict]:
        """Поиск по всем площадкам с автоматическим переключением VPN.

        Режимы (search_mode):
        - "all": российские площадки + Bicotender (VPN переключается авто)
        - "bicotender": только Bicotender

        Приоритет при дедупликации:
        - Российские площадки (zakupki, rts, b2b...) > Bicotender
        - Если тендер найден и там, и там — оставляем версию с площадки-первоисточника
        - Bicotender добавляет только те, которых нет на других площадках
        """
        from core.utils.vpn import vpn_on, vpn_off, vpn_status

        keywords = params.get("keywords", [])
        if not keywords:
            keywords = ["тендер"]

        search_mode = params.get("search_mode", "all")

        # Собираем в два отдельных списка
        russian_results: list[dict] = []
        bico_results: list[dict] = []

        # --- 1. Российские площадки (VPN OFF) — приоритетный источник ---
        if search_mode == "all":
            print("[chat_agent] === Российские площадки (VPN OFF) ===")
            vpn_off()
            try:
                from core.agents.multi_search import search_russian_platforms
                seen_ru: set[str] = set()
                for kw in keywords[:3]:
                    try:
                        items = search_russian_platforms(kw, limit=10)
                        for r in items:
                            eid = f"{r.get('source', '')}:{r.get('external_id', '')}"
                            if eid not in seen_ru:
                                seen_ru.add(eid)
                                russian_results.append(r)
                    except Exception as e:
                        print(f"[chat_agent] russian search '{kw}': {e}")
            finally:
                vpn_on()
            print(f"[chat_agent] российские площадки: {len(russian_results)}")

        # --- 2. Bicotender (VPN ON) — дополнительный источник ---
        print("[chat_agent] === Bicotender ===")
        seen_bico: set[str] = set()
        for kw in keywords[:4]:
            try:
                items = bicotender.search_with_filters(
                    keyword=kw,
                    price_from=params.get("price_from"),
                    price_to=params.get("price_to"),
                    status=params.get("status", "active"),
                    limit=15,
                    headless=True,
                )
                for r in items:
                    eid = r.get("external_id", "")
                    if eid and eid not in seen_bico:
                        seen_bico.add(eid)
                        bico_results.append(r)
            except Exception as e:
                print(f"[chat_agent] bicotender '{kw}': {e}")
        print(f"[chat_agent] bicotender: {len(bico_results)}")

        # --- 3. Дедупликация: российские площадки = приоритет ---
        # Берём все с российских площадок
        final: list[dict] = list(russian_results)
        # Строим индекс названий для проверки дублей
        ru_titles: set[str] = set()
        for r in russian_results:
            title_key = _normalize_title(r.get("title", ""))
            if title_key:
                ru_titles.add(title_key)

        # Из bicotender добавляем только то, чего нет на российских площадках
        added_from_bico = 0
        skipped_dupes = 0
        for r in bico_results:
            title_key = _normalize_title(r.get("title", ""))
            if title_key and title_key in ru_titles:
                skipped_dupes += 1
                continue
            final.append(r)
            if title_key:
                ru_titles.add(title_key)
            added_from_bico += 1

        print(f"[chat_agent] дедупликация: {len(russian_results)} (площадки) + {added_from_bico} (bicotender, уникальных) = {len(final)}")
        if skipped_dupes:
            print(f"[chat_agent] пропущено дублей с bicotender: {skipped_dupes}")

        if not final:
            return final

        # Убеждаемся что VPN включён для Claude
        if not vpn_status()["connected"]:
            vpn_on()

        # Быстрая фильтрация через Claude
        user_query = self.session.history[-1]["content"] if self.session.history else ""
        filtered = self._pre_filter(final, user_query)
        print(f"[chat_agent] pre-filter: {len(final)} -> {len(filtered)}")
        return filtered

    def _pre_filter(self, tenders: list[dict], user_query: str) -> list[dict]:
        """Быстрая фильтрация: Claude за 1 вызов решает, какие тендеры стоит анализировать."""
        if len(tenders) <= 5:
            return tenders  # мало — анализируем все

        # Формируем короткий список для Claude
        items = []
        for i, t in enumerate(tenders):
            items.append(f"{i}. {t.get('title', '')[:120]} | {t.get('price', '')} | {t.get('industry', '')}")
        items_text = "\n".join(items)

        prompt = textwrap.dedent(f"""\
            Пользователь ищет: {user_query}

            Ниже список тендеров, найденных по ключевым словам.
            Отбери ТОЛЬКО те, которые ПОТЕНЦИАЛЬНО релевантны запросу пользователя.
            Отсей явный мусор (не по теме, другая отрасль, не то).
            В сомнительных случаях — оставляй.

            Ответь СТРОГО JSON-массивом номеров: [0, 2, 5, 7]

            Тендеры:
            {items_text}
        """)

        raw = _call_claude(prompt, timeout=30)
        if not raw:
            return tenders  # ошибка — возвращаем все

        match = re.search(r"\[[\d\s,]*\]", raw)
        if not match:
            return tenders

        try:
            indices = json.loads(match.group(0))
            return [tenders[i] for i in indices if 0 <= i < len(tenders)]
        except (json.JSONDecodeError, IndexError):
            return tenders

    def enrich_tenders(self, tenders: list[dict], max_detail: int = 10) -> list[dict]:
        """Обогащает тендеры: открывает карточки, скачивает документы."""
        enriched: list[dict] = []
        for i, t in enumerate(tenders[:max_detail]):
            url = t.get("url", "")
            doc_diag: list[str] = []  # диагностика для отладки

            if not url:
                t["_doc_diag"] = "нет URL карточки"
                enriched.append(t)
                continue

            try:
                detail = bicotender.fetch_detail(url, headless=True)
                t["detail_text"] = detail.get("full_text", "")
                t["source_links"] = detail.get("source_links", [])

                doc_links = detail.get("documents", [])
                doc_diag.append(f"ссылок на документы на странице: {len(doc_links)}")

                if doc_links:
                    for dl in doc_links[:5]:
                        dtype = dl.get("type", "unknown")
                        doc_diag.append(f"  → [{dtype}] {dl.get('text', '')[:40]} | file_id={dl.get('file_id', '')} href={dl.get('href', '')[:50]}")

                    t["doc_files"] = bicotender.download_documents(
                        doc_links,
                        tender_id=t.get("external_id", str(i)),
                        headless=True,
                        max_docs=3,
                        tender_url=url,
                    )
                    doc_diag.append(f"скачано файлов: {len(t['doc_files'])}")
                    if t["doc_files"]:
                        for fp in t["doc_files"]:
                            p = Path(fp) if not isinstance(fp, Path) else fp
                            doc_diag.append(f"  OK {p.name} ({p.stat().st_size} б)" if p.exists() else f"  FAIL {p.name}")
                    else:
                        # Проверяем причину
                        has_limit = any(d.get("_error") == "tariff_limit" for d in doc_links)
                        if has_limit:
                            doc_diag.append("  ! Лимит тарифа Bicotender исчерпан (суточная квота)")
                        else:
                            doc_diag.append("  ! Не удалось скачать (авторизация или ошибка)")
                else:
                    t["doc_files"] = []
                    doc_diag.append("документов нет (страница не содержит ссылок на файлы)")

            except Exception as e:
                doc_diag.append(f"ошибка: {e}")
                t["detail_text"] = t.get("description", "")
                t["doc_files"] = []

            t["_doc_diag"] = "\n".join(doc_diag)
            print(f"[enrich] #{t.get('external_id', i)}: {t['_doc_diag']}")
            enriched.append(t)
        return enriched

    def analyze_tenders(self, tenders: list[dict], user_query: str) -> list[dict]:
        """Анализирует каждый тендер через Claude."""
        for i, t in enumerate(tenders):
            # Собираем тексты документов + диагностику
            doc_texts: list[str] = []
            doc_errors: list[str] = []

            for doc_path in t.get("doc_files", []):
                p = Path(doc_path) if not isinstance(doc_path, Path) else doc_path
                if not p.exists():
                    doc_errors.append(f"{p.name}: файл не найден на диске")
                    continue
                text = parse_document(p)
                if text.startswith("["):
                    doc_errors.append(f"{p.name}: {text}")
                elif text.strip():
                    doc_texts.append(f"--- {p.name} ---\n{text[:4000]}")
                else:
                    doc_errors.append(f"{p.name}: пустой файл")

            # Формируем блок документов для Claude
            if doc_texts:
                documents_text = "\n\n".join(doc_texts)
            else:
                # Подробная причина отсутствия
                diag = t.get("_doc_diag", "")
                reasons: list[str] = []
                if not t.get("doc_files"):
                    if "ссылок на документы на странице: 0" in diag:
                        reasons.append("на странице тендера нет прикреплённых документов")
                    elif "нет URL" in diag:
                        reasons.append("не удалось открыть страницу тендера")
                    elif "ошибка" in diag:
                        reasons.append(f"ошибка при загрузке страницы: {diag.split('ошибка:')[-1].strip()[:100]}")
                    else:
                        reasons.append("документы не удалось скачать (возможно, требуется авторизация)")
                if doc_errors:
                    reasons.extend(doc_errors)
                documents_text = "(Документы: " + "; ".join(reasons) + ")" if reasons else "(нет документов)"
            detail_text = t.get("detail_text", "") or t.get("description", "")

            prompt = TENDER_ANALYSIS_PROMPT.format(
                user_query=user_query,
                title=t.get("title", ""),
                customer=t.get("customer", ""),
                price=t.get("price", ""),
                deadline=t.get("deadline", ""),
                url=t.get("url", ""),
                detail_text=detail_text[:5000],
                documents_text=documents_text[:6000],
            )

            analysis = _call_claude_json(prompt, timeout=120)
            t["analysis"] = analysis or {"error": "no_response", "score": 0}
        return tenders

    def generate_summary(self, tenders: list[dict], user_query: str) -> str:
        """Генерирует итоговый отчёт."""
        summary_data = []
        for t in tenders:
            a = t.get("analysis", {})
            if a.get("error"):
                continue
            summary_data.append({
                "title": t.get("title", ""),
                "customer": t.get("customer", ""),
                "score": a.get("score", 0),
                "relevant": a.get("relevant", False),
                "summary": a.get("summary", ""),
                "recommendation": a.get("recommendation", ""),
                "law_type": a.get("law_type", ""),
            })

        if not summary_data:
            return "К сожалению, не удалось проанализировать найденные тендеры. Попробуйте изменить запрос."

        data_json = json.dumps(summary_data, ensure_ascii=False, indent=2)[:12000]
        prompt = SUMMARY_PROMPT.format(user_query=user_query, data=data_json)
        return _call_claude(prompt, timeout=120) or "Не удалось сгенерировать отчёт."


# --------------- helpers ---------------

def _normalize_title(title: str) -> str:
    """Нормализация названия для дедупликации.

    Убирает пунктуацию, лишние пробелы, приводит к нижнему регистру.
    Берёт первые 60 символов — этого достаточно для сравнения.
    """
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)  # убираем пунктуацию
    t = re.sub(r"\s+", " ", t).strip()
    return t[:60]


def _call_claude(prompt: str, timeout: int = 120) -> str | None:
    from core import llm
    return llm.call_text(prompt, timeout=timeout)


def _call_claude_json(prompt: str, timeout: int = 120) -> dict | None:
    from core import llm
    return llm.call_json(prompt, timeout=timeout)
