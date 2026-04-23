"""FastAPI-сервер: WebSocket-чат с агентом поиска тендеров + REST аналитики."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from apps.web.chat_agent import ChatAgent, Session
from apps.web.enrichment import enrich_tender_card
from core import analytics
from core.storage import chat as chat_store

app = FastAPI(title="TenderAI")
chat_store.init()

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# ============ In-memory state ============
# WS-сессии (история диалога) — живут в памяти процесса. БД — как persistent
# слепок, подтягивается при старте нового WS-коннекта.
sessions: dict[str, Session] = {}
# Активные фоновые задачи поиска (session_id → asyncio.Task).
active_searches: dict[str, asyncio.Task] = {}


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


# ============ АНАЛИТИКА (REST API) ============

@app.get("/api/bench")
async def api_bench(okpd2: str, region: str = "", months: int = 12):
    from core.analytics.cache import bench_from_cache
    cached = bench_from_cache(okpd2, region, months)
    if cached:
        return {"source": "cache", **cached}
    live = analytics.bench_by_okpd2_region(okpd2, region or None, months)
    return {"source": "live", **live}


@app.get("/api/risk")
async def api_risk(inn: str):
    return analytics.risk_by_inn(inn)


@app.get("/api/market/overview")
async def api_market_overview(from_date: str, to_date: str,
                              okpd2: str = "", region: str = ""):
    return analytics.market_overview(okpd2 or None, region or None, from_date, to_date)


@app.get("/api/market/top-sectors")
async def api_top_sectors(from_date: str, to_date: str,
                          region: str = "", limit: int = 20):
    return analytics.top_sectors(region or None, from_date, to_date, limit)


@app.get("/api/market/top-items-in-sector")
async def api_top_items_in_sector(from_date: str, to_date: str, okpd2: str,
                                  region: str = "", limit: int = 15):
    return analytics.top_items_in_sector(okpd2, region or None, from_date, to_date, limit)


@app.get("/api/market/item-details")
async def api_item_details(from_date: str, to_date: str, okpd2_code: str,
                           region: str = "", contracts_limit: int = 20,
                           contracts_offset: int = 0,
                           sort_by: str = "date", sort_dir: str = "desc"):
    """Drill-down: детали одной позиции ОКПД2 — динамика, скидки, контракты с пагинацией.

    sort_by: 'date' | 'price'; sort_dir: 'asc' | 'desc'.
    """
    return analytics.item_details(okpd2_code, region or None,
                                  from_date, to_date,
                                  contracts_limit, contracts_offset,
                                  sort_by, sort_dir)


@app.get("/api/market/top-customers")
async def api_top_customers(from_date: str, to_date: str,
                            okpd2: str = "", region: str = "", limit: int = 20):
    return analytics.top_customers(okpd2 or None, region or None, from_date, to_date, limit)


@app.get("/api/market/top-suppliers")
async def api_top_suppliers(from_date: str, to_date: str,
                            okpd2: str = "", region: str = "", limit: int = 20):
    return analytics.top_suppliers(okpd2 or None, region or None, from_date, to_date, limit)


@app.get("/api/market/timeseries")
async def api_timeseries(from_date: str, to_date: str,
                         okpd2: str = "", region: str = ""):
    return analytics.time_series_by_month(okpd2 or None, region or None, from_date, to_date)


@app.post("/api/classify-okpd2")
async def api_classify_okpd2(payload: dict):
    title = (payload or {}).get("title", "")
    description = (payload or {}).get("description", "")
    return {"candidates": analytics.guess_okpd2(title, description)}


# ============ ЧАТ-СЕССИИ (REST API) ============

@app.get("/api/sessions")
async def api_list_sessions(limit: int = 50):
    """Список всех сессий (сводка для sidebar)."""
    return chat_store.list_sessions(limit=limit)


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    """Полная сессия — сообщения + тендеры."""
    s = chat_store.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    return s


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    """Удалить сессию (на сервере и в in-memory). Активный поиск отменяется."""
    if session_id in active_searches:
        active_searches[session_id].cancel()
        active_searches.pop(session_id, None)
    sessions.pop(session_id, None)
    ok = chat_store.delete_session(session_id)
    return {"deleted": ok}


# ============ SPA fallback ============

@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_fallback(path: str):
    if path.startswith(("api/", "static/", "ws/")):
        raise HTTPException(status_code=404, detail="Not Found")
    return (STATIC / "index.html").read_text(encoding="utf-8")


# ============ TITLE GENERATOR (фоновый) ============

def _gen_title(session: Session, session_id: str, user_msg: str,
               websocket: WebSocket, loop):
    """Короткое название для сессии через LLM. Пишет в БД + шлёт клиенту."""
    from core import llm

    def _do():
        prompt = (
            f'Пользователь написал в чат поиска тендеров: "{user_msg}"\n'
            'Придумай ОЧЕНЬ короткое название для этого чата (2-4 слова). '
            'Ответь ТОЛЬКО названием, без кавычек. Примеры: "Внедрение ИИ", "Видеоаналитика".'
        )
        try:
            raw = llm.call_text(prompt, timeout=15, max_tokens=50) or ""
            title = raw.strip().strip('"\'')
            if title and len(title) < 50:
                session.title_generated = True
                chat_store.upsert_session(session_id, title=title)
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({"type": "session_title", "title": title}),
                    loop,
                )
        except Exception:
            pass

    import threading
    threading.Thread(target=_do, daemon=True).start()


# ============ Background search ============

async def _run_search(session_id: str, session: Session, agent: ChatAgent,
                      websocket: WebSocket, params: dict, user_msg: str):
    """Весь цикл поиск → обогащение → анализ в фоне. Шлёт progress через WS.
    Вызывается через asyncio.create_task, не блокирует receive-loop."""
    loop = asyncio.get_event_loop()

    async def send_status(text: str):
        try: await websocket.send_json({"type": "status", "text": text})
        except Exception: pass

    async def send_message(role: str, content: str):
        try: await websocket.send_json({"type": "message", "role": role, "content": content})
        except Exception: pass
        chat_store.add_message(session_id, role, content)
        session.history.append({"role": "assistant" if role == "assistant" else role,
                                "content": content})

    try:
        kws = params.get("keywords", [])
        mode = params.get("search_mode", "all")
        platforms = "все площадки (госзакупки + Bicotender)" if mode == "all" else "Bicotender"
        await send_status(f"Семантическая карта: {', '.join(kws)}\nПлощадки: {platforms}")

        raw_tenders = await loop.run_in_executor(
            None, lambda: agent.execute_search(params, progress_callback=None)
        )
        await send_status(f"Найдено {len(raw_tenders)} тендеров. Читаю карточки и документы...")

        enriched = await loop.run_in_executor(None, agent.enrich_tenders, raw_tenders)
        await send_status(f"Анализирую {len(enriched)} тендеров через ИИ...")

        analyzed = await loop.run_in_executor(None, agent.analyze_tenders, enriched, user_msg)

        tender_cards = _format_tenders(analyzed)
        if tender_cards:
            try:
                await websocket.send_json({"type": "tenders", "data": tender_cards})
            except Exception:
                pass
            # persist: тендеры — в сессию
            chat_store.upsert_session(session_id, tenders=tender_cards)

        await send_status("Готовлю итоговый отчёт...")
        summary = await loop.run_in_executor(None, agent.generate_summary, analyzed, user_msg)
        await send_message("assistant", summary)
        await send_status("")
    except asyncio.CancelledError:
        # поиск отменён (например, пользователь удалил сессию или начал новый)
        await send_status("")
        raise
    except Exception as e:
        await send_status("")
        await send_message("assistant", f"Произошла ошибка в процессе поиска: {e}")
    finally:
        active_searches.pop(session_id, None)


# ============ WS chat ============

@app.websocket("/ws/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Восстанавливаем сессию из БД (если была) при новом подключении
    if session_id not in sessions:
        session = Session(session_id)
        persisted = chat_store.get_session(session_id)
        if persisted:
            for m in persisted["messages"]:
                session.history.append({"role": m["role"], "content": m["content"]})
            session.title_generated = bool(persisted.get("title") and persisted["title"] != "Новый поиск")
        sessions[session_id] = session
    else:
        session = sessions[session_id]
    agent = ChatAgent(session)

    async def send_message(role: str, content: str, persist: bool = True):
        try: await websocket.send_json({"type": "message", "role": role, "content": content})
        except Exception: pass
        if persist:
            chat_store.add_message(session_id, role, content)

    try:
        while True:
            data = await websocket.receive_json()
            user_msg = data.get("message", "").strip()
            if not user_msg:
                continue

            # persist пользовательское сообщение
            chat_store.add_message(session_id, "user", user_msg)
            session.history.append({"role": "user", "content": user_msg})

            loop = asyncio.get_event_loop()

            # ===== если сейчас активен фоновый поиск =====
            is_searching = session_id in active_searches and not active_searches[session_id].done()
            if is_searching:
                # LLM отвечает коротко, с учётом контекста «ищу сейчас»
                def _reply_while_searching():
                    return agent.respond_during_search(user_msg)
                response = await loop.run_in_executor(None, _reply_while_searching)
                text = response.get("text") if isinstance(response, dict) else str(response)
                if text:
                    await send_message("assistant", text)
                continue

            # ===== обычный путь: спрашиваем агента что делать =====
            await websocket.send_json({"type": "thinking", "active": True})
            try:
                response = await loop.run_in_executor(None, agent.respond, user_msg)
            finally:
                await websocket.send_json({"type": "thinking", "active": False})

            # Автогенерация заголовка после первого сообщения
            if len(session.history) <= 2 and not session.title_generated:
                _gen_title(session, session_id, user_msg, websocket, asyncio.get_event_loop())

            if response.get("search_command"):
                # Если агент хочет что-то сказать перед стартом поиска — отсылаем
                if response.get("text"):
                    await send_message("assistant", response["text"])
                # Запускаем поиск в фоне (не await!)
                params = response["search_command"]
                task = asyncio.create_task(
                    _run_search(session_id, session, agent, websocket, params, user_msg)
                )
                active_searches[session_id] = task
            else:
                # Обычное текстовое сообщение
                text = response.get("text", "") or ""
                await send_message("assistant", text)

    except WebSocketDisconnect:
        # Клиент отключился — поиск может продолжать выполняться в фоне.
        # Он запишет результаты в БД, и при следующем подключении фронт подтянет их.
        pass


# ============ Форматирование карточек тендеров ============

def _format_tenders(analyzed: list[dict]) -> list[dict]:
    """Форматирует тендеры для фронта + обогащает аналитикой из eis_analytics."""
    cards = []
    for t in analyzed:
        analysis = t.get("analysis", {})
        if analysis.get("error"):
            continue
        base = {
            "id": t.get("external_id", ""),
            "reestr_number": t.get("reestr_number", "") or t.get("external_id", ""),
            "title": t.get("title", "Без названия"),
            "customer": t.get("customer", ""),
            "price": analysis.get("budget") or t.get("price", ""),
            "deadline": t.get("deadline", ""),
            "deadline_info": analysis.get("deadline_info", ""),
            "url": t.get("url", ""),
            "law_type": analysis.get("law_type", ""),
            "score": analysis.get("score", 0),
            "relevant": analysis.get("relevant", False),
            "summary": analysis.get("summary", ""),
            "key_requirements": analysis.get("key_requirements", []),
            "mandatory_conditions": analysis.get("mandatory_conditions", []),
            "tech_stack": analysis.get("tech_stack", ""),
            "qualification": analysis.get("qualification", ""),
            "risks": analysis.get("risks", ""),
            "recommendation": analysis.get("recommendation", ""),
            "reason": analysis.get("reason", ""),
            "doc_status": t.get("_doc_diag", ""),
            "doc_count": len(t.get("doc_files", [])),
            "description": analysis.get("summary", "") or t.get("description", ""),
        }
        try:
            base = enrich_tender_card(base)
        except Exception as e:
            print(f"[enrich] fail for {base.get('id')}: {e}")
        cards.append(base)
    cards.sort(key=lambda c: c.get("score", 0), reverse=True)
    return cards
