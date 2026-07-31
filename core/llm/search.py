"""Отдельный OpenAI-compatible LLM для поиска и анализа тендеров.

Провайдер изолирован от общего OpenRouter-конфига: его ключ и URL остаются
на backend/VPS и не должны попадать во frontend или GitHub.
"""
from __future__ import annotations

import json
import os
import re

import requests


class SearchLLMError(RuntimeError):
    """Ошибка вызова выделенного LLM-провайдера."""


def _models() -> list[str]:
    primary = os.getenv("SEARCH_LLM_MODEL", "").strip()
    fallback = os.getenv("SEARCH_LLM_FALLBACK_MODEL", "").strip()
    models = [model for model in (primary, fallback) if model]
    if not models:
        raise SearchLLMError("SEARCH_LLM_MODEL не задан в .env")
    return list(dict.fromkeys(models))


def _content(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SearchLLMError(f"unexpected shape: {exc}; body={str(data)[:300]}") from exc

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    if not isinstance(content, str) or not content.strip():
        raise SearchLLMError(f"empty response; body={str(data)[:300]}")
    return content.strip()


def call_text(
    prompt: str,
    *,
    timeout: int = 120,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str:
    """Вызвать отдельный OpenAI-compatible endpoint с fallback-моделью."""
    base_url = os.getenv("SEARCH_LLM_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("SEARCH_LLM_API_KEY", "").strip()
    if not base_url:
        raise SearchLLMError("SEARCH_LLM_BASE_URL не задан в .env")
    if not api_key:
        raise SearchLLMError("SEARCH_LLM_API_KEY не задан в .env")

    last_error: SearchLLMError | None = None
    for model in _models():
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = SearchLLMError(f"network ({model}): {exc}")
            continue

        if response.status_code != 200:
            last_error = SearchLLMError(
                f"HTTP {response.status_code} ({model}): {response.text[:300]}"
            )
            continue

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            last_error = SearchLLMError(f"not json ({model}): {exc}")
            continue

        if "error" in data:
            last_error = SearchLLMError(f"api error ({model}): {data['error']}")
            continue
        try:
            return _content(data)
        except SearchLLMError as exc:
            last_error = exc

    raise last_error or SearchLLMError("LLM request failed")


def call_json(prompt: str, *, timeout: int = 120) -> dict | None:
    raw = call_text(prompt, timeout=timeout)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"error": "no_json", "raw": raw[:300]}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"error": "bad_json", "raw": raw[:300]}
