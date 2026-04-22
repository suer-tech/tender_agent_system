"""Общие утилиты для источников."""
import re
from datetime import date, datetime


def parse_ru_date(s: str | None) -> date | None:
    if not s:
        return None
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def is_active(deadline: str | None, today: date | None = None, strict: bool = False) -> bool:
    """True если дедлайн >= сегодня.

    strict=False — нераспознанный дедлайн считается активным (на этапе сбора).
    strict=True — без даты считается НЕ активным (на этапе отправки).
    """
    today = today or date.today()
    d = parse_ru_date(deadline)
    if d is None:
        return not strict
    return d >= today
