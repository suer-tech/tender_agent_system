"""Мультиплатформенный поиск тендеров с авто-переключением VPN.

Пайплайн:
1. VPN ON  → Claude строит семантическую карту (ключевые слова)
2. VPN OFF → Поиск на российских площадках (zakupki, rts, b2b, roseltorg, fabrikant)
3. VPN ON  → Поиск на bicotender (работает через любой IP)
4.           Дедупликация: оставляем только уникальные тендеры
5. VPN ON  → Claude анализирует каждый тендер
6. VPN ON  → Claude генерирует отчёт
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.utils.vpn import vpn_on, vpn_off, vpn_status
from core.sources import bicotender
from core.sources.common import is_active


# Площадки, требующие российский IP (VPN OFF)
RUSSIAN_SOURCES = {
    "zakupki":   "sources.zakupki_playwright",
    "rts":       "sources.rts_tender",
    "b2b":       "sources.b2b_center",
    "roseltorg": "sources.roseltorg",
    "fabrikant": "sources.fabrikant",
}


def search_russian_platforms(
    keyword: str,
    limit: int = 10,
    sources: list[str] | None = None,
) -> list[dict]:
    """Поиск на российских площадках (нужен российский IP → VPN OFF)."""
    import importlib

    active_sources = sources or list(RUSSIAN_SOURCES.keys())
    all_results: list[dict] = []

    for name in active_sources:
        module_path = RUSSIAN_SOURCES.get(name)
        if not module_path:
            continue
        try:
            mod = importlib.import_module(module_path)
            print(f"[multi] {name}: ищу '{keyword}'...")
            items = mod.search(keyword, limit=limit, headless=True)
            # Фильтруем просроченные
            active_items = [it for it in items if is_active(it.get("deadline"))]
            all_results.extend(active_items)
            print(f"[multi] {name}: {len(active_items)} активных из {len(items)}")
        except Exception as e:
            print(f"[multi] {name}: ошибка - {str(e)[:80]}")

    return all_results


def search_all_platforms(
    keywords: list[str],
    limit_per_source: int = 10,
    use_russian: bool = True,
    use_bicotender: bool = True,
    russian_sources: list[str] | None = None,
) -> list[dict]:
    """Поиск по всем площадкам с автоматическим переключением VPN.

    Returns:
        Дедуплицированный список тендеров со всех площадок.
    """
    all_tenders: list[dict] = []
    seen_titles: set[str] = set()  # для дедупликации по названию
    seen_ids: set[str] = set()     # для дедупликации по external_id

    def _dedup_add(items: list[dict]):
        for item in items:
            eid = f"{item.get('source', '')}:{item.get('external_id', '')}"
            title_key = item.get("title", "").lower().strip()[:80]
            if eid in seen_ids:
                continue
            # Дедупликация по похожему названию (один тендер на разных площадках)
            if title_key and title_key in seen_titles:
                continue
            seen_ids.add(eid)
            if title_key:
                seen_titles.add(title_key)
            all_tenders.append(item)

    initial_vpn = vpn_status()

    # --- Этап 1: Российские площадки (VPN OFF) ---
    if use_russian:
        print("\n[multi] === Российские площадки (VPN OFF) ===")
        vpn_off()

        for kw in keywords[:3]:  # макс 3 ключевых слова для российских площадок
            try:
                items = search_russian_platforms(kw, limit=limit_per_source, sources=russian_sources)
                _dedup_add(items)
            except Exception as e:
                print(f"[multi] ошибка поиска '{kw}': {e}")

        print(f"[multi] Найдено на российских площадках: {len(all_tenders)}")

    # --- Этап 2: Bicotender (любой IP) ---
    if use_bicotender:
        print("\n[multi] === Bicotender ===")
        # Bicotender работает с любого IP, но для надёжности включаем VPN
        vpn_on()

        for kw in keywords[:4]:
            try:
                items = bicotender.search_with_filters(kw, limit=limit_per_source, headless=True)
                _dedup_add(items)
            except Exception as e:
                print(f"[multi] bicotender '{kw}': {e}")

        print(f"[multi] Всего после bicotender: {len(all_tenders)}")

    # --- Восстанавливаем VPN для Claude ---
    if not vpn_status()["connected"]:
        vpn_on()

    print(f"\n[multi] Итого уникальных тендеров: {len(all_tenders)}")
    return all_tenders
