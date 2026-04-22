"""LLM-фасад. Выбор провайдера через env.

Переменные окружения:
    LLM_PROVIDER            = openrouter | claude   (по умолчанию openrouter)
    OPENROUTER_API_KEY      = ключ OpenRouter
    OPENROUTER_MODEL        = основная модель  (default: google/gemma-4-26b-a4b-it:free)
    OPENROUTER_FALLBACK_MODEL = фоллбэк        (default: x-ai/grok-4.1-fast)

API:
    call_text(prompt, timeout=120) -> str | None
    call_json(prompt, timeout=120) -> dict | None   # извлекает {...} из ответа
    evaluate(tender) -> dict                         # оценка тендера (legacy-контракт)

Провайдер `claude` сохраняет прежний функционал: subprocess к `claude -p`
(требует залогиненного Claude Code на машине, НЕ работает с РФ-IP).
"""
from __future__ import annotations

import json
import os
import re

from . import claude_cli, openrouter


DEFAULT_OR_MODEL = "google/gemma-4-26b-a4b-it:free"
DEFAULT_OR_FALLBACK = "x-ai/grok-4.1-fast"


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "openrouter").strip().lower()


def _or_models() -> list[str]:
    primary = os.getenv("OPENROUTER_MODEL", DEFAULT_OR_MODEL).strip()
    fallback = os.getenv("OPENROUTER_FALLBACK_MODEL", DEFAULT_OR_FALLBACK).strip()
    out = [primary]
    if fallback and fallback != primary:
        out.append(fallback)
    return out


def call_text(prompt: str, *, timeout: int = 120, max_tokens: int = 1024) -> str | None:
    """Синхронный вызов LLM. Возвращает строку или None при неудаче."""
    prov = _provider()
    if prov == "claude":
        return claude_cli._call_claude_cli(prompt, timeout=timeout)
    # openrouter (default)
    last_err: Exception | None = None
    for model in _or_models():
        try:
            return openrouter.call_text(prompt, model, timeout=timeout, max_tokens=max_tokens)
        except openrouter.OpenRouterError as e:
            print(f"[llm] openrouter {model} failed: {e}")
            last_err = e
            continue
    if last_err:
        print(f"[llm] все OR-модели упали; последняя ошибка: {last_err}")
    return None


def call_json(prompt: str, *, timeout: int = 120) -> dict | None:
    raw = call_text(prompt, timeout=timeout)
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"error": "no_json", "raw": raw[:300]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"error": "bad_json", "raw": raw[:300]}


# ---------- legacy-контракт оценки тендера (evaluate) ----------

_EVAL_PROMPT = """Ты — эксперт по оценке тендеров. Оцени тендер ниже на релевантность.

Ответь СТРОГО валидным JSON без каких-либо пояснений до или после:
{{"relevant": true|false, "score": 0-10, "summary": "1-2 предложения о сути закупки", "reason": "кратко почему релевантно/нет"}}

Тендер:
Название: {title}
Заказчик: {customer}
Цена: {price}
Описание: {description}
"""


def evaluate(tender: dict, timeout: int = 120) -> dict | None:
    prompt = _EVAL_PROMPT.format(
        title=tender.get("title", ""),
        customer=tender.get("customer", ""),
        price=tender.get("price", ""),
        description=(tender.get("description") or "")[:3000],
    )
    return call_json(prompt, timeout=timeout)
