import os
import asyncio
import yaml
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters,
)

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.sources import zakupki_playwright
from core.sources.common import is_active
from core import llm
from core.storage import db
from core.agents import bicotender_agent

load_dotenv(ROOT / ".env")
TOKEN = os.getenv("TG_TOKEN")
ALLOWED_CHAT = os.getenv("TG_ALLOWED_CHAT_ID")

with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)


def _allowed(update: Update) -> bool:
    if not ALLOWED_CHAT:
        return True
    return str(update.effective_chat.id) == str(ALLOWED_CHAT)


MAIN_KB = ReplyKeyboardMarkup(
    [["🧠 Оценить pending"],
     ["🔍 Глубокий поиск Bicotender"],
     ["📊 Статус", "⚙️ Ключевые слова"]],
    resize_keyboard=True,
)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    inline = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Оценить pending", callback_data="evaluate")],
        [InlineKeyboardButton("🔍 Глубокий поиск", callback_data="deep_search")],
        [InlineKeyboardButton("📊 Статус", callback_data="status"),
         InlineKeyboardButton("⚙️ Ключевые слова", callback_data="show_kw")],
    ])
    await update.message.reply_text(
        f"Привет! chat_id: <code>{update.effective_chat.id}</code>\n\n"
        "Пайплайн (VPN мешает Telegram и Claude, поэтому сбор — снаружи):\n"
        "1️⃣ VPN ВКЛ → в консоли <code>python collect.py</code>\n"
        "2️⃣ VPN ВЫКЛ → здесь жми «🧠 Оценить pending»\n\n"
        "Или запусти «🔍 Глубокий поиск» — агент Bicotender найдёт тендеры,\n"
        "прочитает документацию и даст развёрнутый анализ.",
        parse_mode="HTML",
        reply_markup=inline,
    )
    await update.message.reply_text("Быстрые действия:", reply_markup=MAIN_KB)


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/search — поиск по всем ключевикам из config.yaml\n"
        "/search <текст> — поиск по своей фразе\n"
        "/deep_search — глубокий поиск через Bicotender (с анализом документов)\n"
        "/deep_search <текст> — глубокий поиск по своей фразе\n"
        "/keywords — показать текущие ключевые слова",
        reply_markup=MAIN_KB,
    )


async def keywords_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kws = "\n".join(f"• {k}" for k in CFG["keywords"])
    await update.message.reply_text(f"Ключевые слова:\n{kws}", reply_markup=MAIN_KB)


async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    text = update.message.text
    if text.startswith("🧠"):
        await run_evaluate(update, ctx)
    elif text.startswith("🔍"):
        await run_deep_search(update, ctx)
    elif text.startswith("📊"):
        await status_cmd(update, ctx)
    elif text.startswith("⚙️"):
        await keywords_cmd(update, ctx)


async def collect_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    query = " ".join(ctx.args).strip()
    keywords = [query] if query else CFG["keywords"]
    await run_collect(update, ctx, keywords=keywords)


async def evaluate_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    await run_evaluate(update, ctx)


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = db.stats()
    text = (
        "📊 Статус БД:\n"
        f"• pending (ждут оценки): {s.get('pending', 0)}\n"
        f"• relevant: {s.get('relevant', 0)}\n"
        f"• irrelevant: {s.get('irrelevant', 0)}"
    )
    await update.message.reply_text(text)


async def run_collect(update: Update, ctx: ContextTypes.DEFAULT_TYPE, keywords: list[str]):
    msg = await update.message.reply_text(
        f"📥 Фаза 1 / Сбор. Запросов: {len(keywords)}. Нужен VPN с российским IP."
    )
    law_types = CFG["search"]["law_types"]
    limit = CFG["search"]["max_results_per_keyword"]

    found = 0
    new = 0
    errors = []
    loop = asyncio.get_event_loop()
    for i, kw in enumerate(keywords, 1):
        try:
            items = await loop.run_in_executor(
                None, zakupki_playwright.search, kw, law_types, limit, True
            )
            for it in items:
                found += 1
                before = db.stats().get("pending", 0)
                db.save_pending(it)
            try:
                await msg.edit_text(
                    f"📥 [{i}/{len(keywords)}] «{kw}» — {len(items)} карточек. Всего найдено: {found}"
                )
            except Exception:
                pass
        except Exception as e:
            errors.append(f"«{kw}»: {str(e)[:100]}")

    s = db.stats()
    text = (
        f"✅ Сбор завершён.\n"
        f"Всего карточек за прогон: {found}\n"
        f"В очереди на оценку (pending): {s.get('pending', 0)}\n\n"
        f"➡️ Выключай VPN и жми «🧠 Оценить»."
    )
    if errors:
        text += "\n\n⚠️ Ошибки:\n" + "\n".join(errors[:5])
    await msg.edit_text(text)


async def deep_search_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    query = " ".join(ctx.args).strip() if ctx.args else ""
    await run_deep_search(update, ctx, query=query)


async def run_deep_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE, query: str = ""):
    """Глубокий поиск: Bicotender → карточки → документы → Claude анализ → отчёт."""
    user_query = query or "Внедрение искусственного интеллекта, ML, автоматизация бизнес-процессов"

    bicotender_cfg = CFG.get("bicotender", {})
    keywords = bicotender_cfg.get("keywords", CFG.get("keywords", []))[:5]
    limit = bicotender_cfg.get("max_results", 5)
    max_docs = bicotender_cfg.get("max_docs_per_tender", 3)

    msg = await update.message.reply_text(
        f"🔍 <b>Глубокий поиск Bicotender</b>\n\n"
        f"Запрос: {_esc(user_query)}\n"
        f"Ключевых слов: {len(keywords)}\n"
        f"Лимит: {limit} тендеров/ключ\n\n"
        f"Этот процесс займёт время:\n"
        f"1. Поиск на bicotender.ru\n"
        f"2. Чтение карточек тендеров\n"
        f"3. Скачивание документации\n"
        f"4. Анализ через Claude\n"
        f"5. Генерация отчёта\n\n"
        f"⏳ Работаю...",
        parse_mode="HTML",
    )

    loop = asyncio.get_event_loop()
    progress_msgs: list[str] = []

    def on_progress(text: str):
        progress_msgs.append(text)

    try:
        result = await loop.run_in_executor(
            None,
            lambda: bicotender_agent.run(
                user_query=user_query,
                keywords=keywords,
                limit=limit,
                headless=True,
                max_docs=max_docs,
                progress_callback=on_progress,
            ),
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка глубокого поиска: {_esc(str(e))}", parse_mode="HTML")
        return

    # Обновляем статус
    try:
        await msg.edit_text(
            f"✅ <b>Глубокий поиск завершён</b>\n\n"
            f"Найдено: {result['total_found']}\n"
            f"Проанализировано: {result['analyzed']}\n"
            f"Релевантных: {result['relevant_count']}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Отправляем отчёт
    report = result.get("report", "")
    if report:
        # Telegram ограничивает сообщения 4096 символами — разбиваем
        chunks = _split_message(report, 4000)
        for chunk in chunks:
            await update.message.reply_text(chunk, disable_web_page_preview=True)
    else:
        await update.message.reply_text("Отчёт не был сгенерирован.")

    # Отправляем карточки релевантных тендеров
    for tender in result.get("results", []):
        analysis = tender.get("analysis", {})
        if analysis.get("error") or not analysis.get("relevant"):
            continue
        await send_deep_tender(update, tender, analysis)


async def send_deep_tender(update: Update, tender: dict, analysis: dict):
    """Отправка карточки тендера с глубоким анализом."""
    reqs = analysis.get("key_requirements", [])
    reqs_text = "\n".join(f"  • {_esc(r)}" for r in reqs[:5]) if reqs else "—"

    text = (
        f"<b>{_esc(tender.get('title', '')[:200])}</b>\n\n"
        f"🏢 {_esc(tender.get('customer', '—'))}\n"
        f"💰 {_esc(analysis.get('budget', '') or tender.get('price', '—'))}\n"
        f"⏰ {_esc(analysis.get('deadline_info', '') or tender.get('deadline', '—'))}\n"
        f"📊 Релевантность: {analysis.get('score', 0)}/10\n\n"
        f"💡 {_esc(analysis.get('summary', ''))}\n\n"
        f"<b>Требования:</b>\n{reqs_text}\n\n"
        f"🛠 Технологии: {_esc(analysis.get('tech_stack', '—'))}\n"
        f"⚠️ Риски: {_esc(analysis.get('risks', '—'))}\n\n"
        f"<i>{_esc(analysis.get('recommendation', ''))}</i>"
    )

    # Обрезаем если слишком длинный
    if len(text) > 4000:
        text = text[:3950] + "...</i>"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 Открыть", url=tender.get("url", BASE)),
    ]])
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True,
    )


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Разбивает длинный текст на куски для Telegram."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Ищем ближайший перенос строки для красивого разбиения
        cut = text.rfind("\n", 0, max_len)
        if cut < max_len // 2:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


BASE = "https://www.bicotender.ru"


async def run_evaluate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pending = db.list_pending()
    threshold = CFG["llm"]["relevance_threshold"]
    msg = await update.message.reply_text(
        f"🧠 В очереди на оценку: {len(pending)}. Проверю также недоставленные релевантные."
    )

    loop = asyncio.get_event_loop()
    evaluated = 0
    relevant = 0
    errors = 0
    for i, item in enumerate(pending, 1):
        verdict = await loop.run_in_executor(None, llm.evaluate, item)
        if not verdict or verdict.get("error"):
            errors += 1
            continue
        score = int(verdict.get("score", 0) or 0)
        summary = verdict.get("summary", "") or ""
        reason = verdict.get("reason", "") or ""
        is_rel = bool(verdict.get("relevant")) and score >= threshold
        db.update_verdict(item["id"], score, summary, reason, is_rel)
        evaluated += 1
        if is_rel:
            relevant += 1
        if i % 5 == 0 or i == len(pending):
            try:
                await msg.edit_text(
                    f"🧠 Оценено {i}/{len(pending)}. Релевантных: {relevant}, ошибок: {errors}"
                )
            except Exception:
                pass

    # Отправляем релевантные, которые ещё не доставлены и не просрочены
    all_rel = db.list_undelivered_relevant(threshold)
    to_send = [t for t in all_rel if is_active(t.get("deadline"), strict=True)]
    skipped_expired = len(all_rel) - len(to_send)
    for t in to_send:
        verdict = {"score": t["score"], "summary": t["summary"], "reason": t["reason"]}
        await send_tender(update, t, verdict, t["id"])
        db.mark_delivered(t["id"])

    await msg.edit_text(
        f"✅ Оценка завершена.\n"
        f"Оценено: {evaluated}, ошибок: {errors}\n"
        f"Релевантных: {len(all_rel)}, отправлено: {len(to_send)}, "
        f"пропущено (просрочено/без даты): {skipped_expired}"
    )


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def send_tender(update: Update, item: dict, verdict: dict, tender_id: int):
    def _f(v, dash="—"):
        s = (v or "").strip() if isinstance(v, str) else (str(v) if v else "")
        return s or dash
    text = (
        f"<b>{_esc(_f(item.get('title')))}</b>\n\n"
        f"🏢 {_esc(_f(item.get('customer')))}\n"
        f"💰 {_esc(_f(item.get('price')))}\n"
        f"⏰ до {_esc(_f(item.get('deadline'), 'дата не распознана'))}\n"
        f"📊 Релевантность: {verdict.get('score')}/10\n\n"
        f"💡 {_esc(_f(verdict.get('summary'), ''))}\n"
        f"<i>{_esc(_f(verdict.get('reason'), ''))}</i>"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔗 Открыть", url=item["url"] or "https://zakupki.gov.ru"),
        InlineKeyboardButton("👍", callback_data=f"up:{tender_id}"),
        InlineKeyboardButton("👎", callback_data=f"down:{tender_id}"),
    ]])
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


async def feedback_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    vote, tid = q.data.split(":")
    db.record_feedback(int(tid), vote)
    await q.edit_message_reply_markup(reply_markup=None)
    await q.message.reply_text("Записал 👌")


async def menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    fake = type("O", (), {"message": q.message})()
    if q.data == "evaluate":
        await run_evaluate(fake, ctx)
    elif q.data == "deep_search":
        await run_deep_search(fake, ctx)
    elif q.data == "status":
        await status_cmd(fake, ctx)
    elif q.data == "show_kw":
        kws = "\n".join(f"• {k}" for k in CFG["keywords"])
        await q.message.reply_text(f"Ключевые слова:\n{kws}")


def main():
    if not TOKEN:
        raise SystemExit("TG_TOKEN не задан. Скопируй .env.example в .env и заполни.")
    db.init()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("evaluate", evaluate_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("keywords", keywords_cmd))
    app.add_handler(CommandHandler("deep_search", deep_search_cmd))
    app.add_handler(CallbackQueryHandler(feedback_cb, pattern=r"^(up|down):"))
    app.add_handler(CallbackQueryHandler(menu_cb, pattern=r"^(evaluate|status|show_kw|deep_search)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
    print("Bot running. Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
