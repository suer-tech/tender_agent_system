"""Провайдер Claude через локальный CLI (`claude -p`).

Требует установленного и залогиненного Claude Code. С РФ-IP не работает —
Anthropic блокирует. Оставлен для совместимости и для dev-машин вне РФ.

Используется фасадом llm.__init__ когда LLM_PROVIDER=claude.
"""
from __future__ import annotations

import json
import re
import subprocess


PROMPT_TEMPLATE = """Ты — эксперт по оценке тендеров. Оцени тендер ниже на релевантность.

Ответь СТРОГО валидным JSON без каких-либо пояснений до или после:
{{"relevant": true|false, "score": 0-10, "summary": "1-2 предложения о сути закупки", "reason": "кратко почему релевантно/нет"}}

Тендер:
Название: {title}
Заказчик: {customer}
Цена: {price}
Описание: {description}
"""


def _call_claude_cli(prompt: str, *, timeout: int = 120) -> str | None:
    try:
        res = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8",
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[claude_cli] {type(e).__name__}: {e}")
        return None
    return (res.stdout or "").strip() or None


def evaluate(tender: dict, timeout: int = 120) -> dict | None:
    prompt = PROMPT_TEMPLATE.format(
        title=tender.get("title", ""),
        customer=tender.get("customer", ""),
        price=tender.get("price", ""),
        description=(tender.get("description") or "")[:3000],
    )
    raw = _call_claude_cli(prompt, timeout=timeout)
    if not raw:
        return {"error": "no_output"}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"error": "no_json", "raw": raw[:500]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"error": "bad_json", "raw": raw[:500]}
