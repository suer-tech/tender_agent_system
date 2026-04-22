"""OpenRouter-провайдер. Один ключ, любая модель по ID.

Работает из РФ без VPN (прокси-сервис openrouter.ai пропускает).
"""
from __future__ import annotations

import json
import os

import requests

BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")


class OpenRouterError(RuntimeError):
    pass


def call_text(prompt: str, model: str, *, timeout: int = 120,
              max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """Сырой текстовый вызов. Бросает исключение при любых ошибках — выше по
    стеку фасад поймает и при необходимости переключится на fallback."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError("OPENROUTER_API_KEY не задан в .env")

    try:
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://tender-agent.local"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "tender-agent"),
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise OpenRouterError(f"network: {e}") from e

    if r.status_code != 200:
        raise OpenRouterError(f"HTTP {r.status_code}: {r.text[:300]}")

    try:
        data = r.json()
    except json.JSONDecodeError as e:
        raise OpenRouterError(f"not json: {e}; body={r.text[:200]}") from e

    if "error" in data:
        raise OpenRouterError(f"api error: {data['error']}")

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError) as e:
        raise OpenRouterError(f"unexpected shape: {e}; body={str(data)[:300]}") from e
