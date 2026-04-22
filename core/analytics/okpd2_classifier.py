"""Классификатор тендеров в ОКПД2.

Стратегия:
  1. TF-IDF match названия тендера с названиями позиций `notice_items.name` и
     `contract_items.name` → находим ОКПД2, которые чаще всего ассоциируются
     с похожими формулировками.
  2. Без LLM, на уровне SQL + набор стоп-слов + базовый токенизатор.
  3. Возвращаем top-3 кандидатов с confidence (0..1).
  4. Если лучший confidence < 0.4 → возвращаем пустой список (явно не угадано).

Это быстрая эвристика, не ML — нам хватает для карточки. LLM-fallback
сделаем позже, когда будет реальный use-case, где эвристика промахивается.
"""
from __future__ import annotations

import re
from collections import Counter

from ..storage import eis_analytics


_STOP = set("""
и в во не что он на я с со как а то все она так его но да ты к у же
вы за бы по только ее мне было вот от меня еще нет о из ему теперь
когда даже ну вдруг ли если уже или ни быть был него до вас нибудь
опять уж вам сказал ведь там потом себя ничего ей может они тут где
есть надо ней для мы тебя их чем была сам чтоб без будто чего раз
тоже себе под будет ж тогда кто этот того потому этого какой совсем
ним здесь эту которое которая которых которому которого какое какие
оказание услуг услуги работы работ товаров товар поставка поставки
закупка закупки выполнение оказать поставить выполнить
""".split())


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    text = text.lower()
    # оставляем только буквы/цифры/пробелы
    text = re.sub(r"[^\wа-яё\s]+", " ", text, flags=re.U)
    tokens = [t for t in text.split() if len(t) >= 3 and t not in _STOP]
    return tokens


def guess_okpd2(title: str, description: str = "", limit: int = 3) -> list[dict]:
    """Вернуть список кандидатов [{code, name, confidence}] по тексту тендера."""
    full = f"{title or ''} {description or ''}".strip()
    tokens = _tokenize(full)
    if not tokens:
        return []

    # Ограничиваемся топ-20 самых редких токенов (более информативные)
    token_counts = Counter(tokens)
    # Используем первые 20 токенов в порядке появления (сохраняет контекст)
    query_tokens = list(dict.fromkeys(tokens))[:20]

    # Собираем запрос: ищем items, имена которых содержат наши токены
    # (SQLite без полнотекста — используем LIKE; грубо, но работает на MVP)
    like_clauses = " OR ".join(["LOWER(name) LIKE ?"] * len(query_tokens))
    params = [f"%{t}%" for t in query_tokens]

    with eis_analytics.conn() as conn:
        rows = conn.execute(f"""
            SELECT okpd2_code, okpd2_name, COUNT(*) AS matches
            FROM contract_items
            WHERE okpd2_code IS NOT NULL AND ({like_clauses})
            GROUP BY okpd2_code
            ORDER BY matches DESC
            LIMIT 50
        """, params).fetchall()

    if not rows:
        return []

    # Считаем scoring: доля от общего числа матчей + бонус за специфичность
    total_matches = sum(r["matches"] for r in rows)
    if total_matches == 0:
        return []

    results = []
    top_match = rows[0]["matches"]
    for r in rows[:limit]:
        confidence = round(r["matches"] / total_matches, 3)
        # Normalization к 1.0: максимальный кандидат должен иметь confidence 0.5-1.0
        # в зависимости от доминирования над остальными
        norm = round(r["matches"] / top_match * (top_match / total_matches + 0.3), 3)
        norm = min(norm, 1.0)
        results.append({
            "code": r["okpd2_code"],
            "name": r["okpd2_name"],
            "confidence": norm,
            "matches": r["matches"],
        })

    # Фильтр по минимальной уверенности
    results = [r for r in results if r["confidence"] >= 0.4]
    return results
