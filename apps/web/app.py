"""FastAPI-сервер: WebSocket-чат с агентом поиска тендеров."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from apps.web.chat_agent import ChatAgent, Session
from apps.web.enrichment import enrich_tender_card
from core import analytics

app = FastAPI(title="TenderAI")

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# In-memory sessions
sessions: dict[str, Session] = {}


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


# ============ АНАЛИТИКА (REST API) ============

@app.get("/api/bench")
async def api_bench(okpd2: str, region: str = "", months: int = 12):
    """Ценовой бенчмарк по срезу. Сначала из кэша, fallback на live-расчёт."""
    from core.analytics.cache import bench_from_cache
    cached = bench_from_cache(okpd2, region, months)
    if cached:
        return {"source": "cache", **cached}
    live = analytics.bench_by_okpd2_region(okpd2, region or None, months)
    return {"source": "live", **live}


@app.get("/api/risk")
async def api_risk(inn: str):
    """Риск-сводка по ИНН (заказчик + поставщик + РНП)."""
    return analytics.risk_by_inn(inn)


@app.get("/api/market/overview")
async def api_market_overview(from_date: str, to_date: str,
                              okpd2: str = "", region: str = ""):
    return analytics.market_overview(okpd2 or None, region or None, from_date, to_date)


@app.get("/api/market/top-sectors")
async def api_top_sectors(from_date: str, to_date: str,
                          region: str = "", limit: int = 20):
    return analytics.top_sectors(region or None, from_date, to_date, limit)


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


# ============ SPA fallback ============
# React Router разруливает /market, /market/* и прочие клиентские роуты.
# Любой GET, не попавший в /api/*, /static/*, /ws/* — возвращаем index.html.

@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_fallback(path: str):
    if path.startswith(("api/", "static/", "ws/")):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not Found")
    return (STATIC / "index.html").read_text(encoding="utf-8")


def _gen_title(session: Session, user_msg: str, websocket: WebSocket, loop):
    """Generate a short session title in background."""
    from core import llm

    def _do():
        prompt = (
            f'Пользователь написал в чат поиска тендеров: "{user_msg}"\n'
            'Придумай ОЧЕНЬ короткое название для этого чата (2-4 слова, суть запроса). '
            'Ответь ТОЛЬКО названием, без кавычек и пояснений. Примеры: '
            '"Внедрение ИИ", "Чат-боты для банков", "Видеоаналитика".'
        )
        try:
            raw = llm.call_text(prompt, timeout=15, max_tokens=50) or ""
            title = raw.strip().strip('"\'')
            if title and len(title) < 50:
                session.title_generated = True
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({"type": "session_title", "title": title}),
                    loop,
                )
        except Exception:
            pass

    import threading
    threading.Thread(target=_do, daemon=True).start()


@app.websocket("/ws/{session_id}")
async def ws_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in sessions:
        sessions[session_id] = Session(session_id)
    session = sessions[session_id]
    agent = ChatAgent(session)

    try:
        while True:
            data = await websocket.receive_json()
            user_msg = data.get("message", "").strip()
            if not user_msg:
                continue

            session.history.append({"role": "user", "content": user_msg})

            # Callback для стриминга прогресса
            async def send_status(text: str):
                await websocket.send_json({"type": "status", "text": text})

            async def send_message(role: str, content: str):
                await websocket.send_json({
                    "type": "message", "role": role, "content": content,
                })

            async def send_tenders(tenders: list[dict]):
                await websocket.send_json({"type": "tenders", "data": tenders})

            # Показываем индикатор "думает"
            await websocket.send_json({"type": "thinking", "active": True})

            try:
                loop = asyncio.get_event_loop()

                # 1. Получаем ответ агента (может содержать команду поиска)
                response = await loop.run_in_executor(None, agent.respond, user_msg)

                await websocket.send_json({"type": "thinking", "active": False})

                # Generate session title after first exchange
                if len(session.history) <= 2 and not session.title_generated:
                    _gen_title(session, user_msg, websocket, asyncio.get_event_loop())

                if response.get("search_command"):
                    # Агент решил запустить поиск
                    if response.get("text"):
                        await send_message("assistant", response["text"])
                        session.history.append({"role": "assistant", "content": response["text"]})

                    params = response["search_command"]
                    kws = params.get("keywords", [])
                    mode = params.get("search_mode", "all")
                    platforms = "все площадки (госзакупки + Bicotender)" if mode == "all" else "Bicotender"

                    # 2. Выполняем поиск по семантической карте
                    await send_status(
                        f"Семантическая карта: {', '.join(kws)}\n"
                        f"Площадки: {platforms}"
                    )

                    def _do_search():
                        return agent.execute_search(params, progress_callback=None)

                    raw_tenders = await loop.run_in_executor(None, _do_search)
                    await send_status(
                        f"Найдено {len(raw_tenders)} тендеров (дедупликация + фильтрация).\n"
                        f"Читаю карточки и документы..."
                    )

                    # 3. Обогащаем тендеры (детали + документы)
                    enriched = await loop.run_in_executor(
                        None, agent.enrich_tenders, raw_tenders,
                    )
                    await send_status(f"Анализирую {len(enriched)} тендеров через ИИ...")

                    # 4. Анализируем через Claude
                    analyzed = await loop.run_in_executor(
                        None, agent.analyze_tenders, enriched, user_msg,
                    )

                    # 5. Отправляем результаты
                    tender_cards = _format_tenders(analyzed)
                    if tender_cards:
                        await send_tenders(tender_cards)

                    # 6. Генерируем сводку
                    await send_status("Готовлю итоговый отчёт...")
                    summary = await loop.run_in_executor(
                        None, agent.generate_summary, analyzed, user_msg,
                    )
                    await send_message("assistant", summary)
                    session.history.append({"role": "assistant", "content": summary})
                    await send_status("")

                else:
                    # Обычное сообщение (вопрос, уточнение)
                    await send_message("assistant", response.get("text", ""))
                    session.history.append({"role": "assistant", "content": response.get("text", "")})

            except Exception as e:
                await websocket.send_json({"type": "thinking", "active": False})
                await send_message("assistant", f"Произошла ошибка: {e}")

    except WebSocketDisconnect:
        pass


def _format_tenders(analyzed: list[dict]) -> list[dict]:
    """Форматирует тендеры для отправки на фронтенд + обогащает аналитикой."""
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
        # обогащаем аналитикой (bench + risk + okpd2)
        try:
            base = enrich_tender_card(base)
        except Exception as e:
            print(f"[enrich] fail for {base.get('id')}: {e}")
        cards.append(base)
    cards.sort(key=lambda c: c.get("score", 0), reverse=True)
    return cards
