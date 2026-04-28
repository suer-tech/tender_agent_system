"""Пакетный загрузчик истории ЕИС через ДИС.

Пока — только MVP с командой --test (1 SOAP-запрос для проверки токена и
структуры ответа). После того как один запрос пройдёт и мы увидим реальную
структуру XML, допилим парсинг контрактов и массовый режим с воркерами.

Примеры:
    python load_history.py --test
    python load_history.py --test --region 78 --date 2025-03-15
    python load_history.py stats

Требует EIS_DIS_TOKEN в .env.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from core.sources.eis.dis import EisDisClient, EisDisError
from core.sources.eis import pipeline as eis_pipeline
from core.sources.eis import analytics_loader as eis_analytics_loader
from core.sources.eis import parsers as eis_parsers
from core.storage import eis_history, eis_analytics
from core.utils.vpn import vpn_status, vpn_off, vpn_on

load_dotenv()


def with_ru_ip(fn):
    """Обёртка: VPN OFF на время fn() (ДИС требует РФ-IP), в finally вернуть."""
    prev = vpn_status()
    need_restore = prev.get("connected", False)
    if need_restore:
        print(f"[vpn] выключаю VPN (профиль был {prev.get('profile')}, IP {prev.get('ip')})")
        if not vpn_off():
            raise RuntimeError("Не удалось выключить VPN — ДИС будет недоступен")
        time.sleep(2)
    try:
        return fn()
    finally:
        if need_restore:
            print(f"\n[vpn] возвращаю VPN -> {prev.get('profile')}")
            if not vpn_on(prev.get("profile")):
                print("[vpn] !! не удалось вернуть VPN — переподключись вручную")


def cmd_test(args):
    """Один SOAP-запрос: проверяем токен и смотрим, что возвращает сервис."""
    eis_history.init()

    client = EisDisClient()

    req = {
        "fz": args.fz,
        "region_code": args.region,
        "subsystem": args.subsystem,
        "doc_type": args.doc_type,
        "exact_date": args.date,
    }
    print("SOAP-запрос getDocsByOrgRegionRequest:")
    for k, v in req.items():
        print(f"  {k:12s}: {v}")

    batch_id = eis_history.upsert_batch(**req)
    eis_history.mark_batch_status(batch_id, "in_progress")

    try:
        result = client.get_docs_by_org_region(**req)
    except EisDisError as e:
        print(f"\n[FAIL] {e}")
        eis_history.mark_batch_status(batch_id, "error", error=str(e)[:500])
        return 1

    urls = result["archive_urls"]
    raw = result["raw_xml"]
    print(f"\n[OK] HTTP 200, {len(raw)} байт в ответе")
    print(f"URL архивов найдено: {len(urls)}")
    for u in urls[:5]:
        print(f"  - {u}")

    # Сохраним сырьё для офлайн-разбора первого успешного ответа.
    dump = Path("diag") / f"eis_dis_{batch_id}.xml"
    dump.parent.mkdir(exist_ok=True)
    dump.write_bytes(raw)
    print(f"\nСырой ответ: {dump}")

    eis_history.mark_batch_status(
        batch_id, "ok",
        request_id=result["request_id"],
        archive_count=len(urls),
    )
    print(f"\nBatch #{batch_id} помечен OK. Дальше: попробуем скачать один архив.")
    if urls and args.fetch:
        print(f"\nСкачиваю {urls[0]} ...")
        data = client.download_archive(urls[0])
        arch_path = Path("diag") / f"eis_dis_{batch_id}_archive_0.zip"
        arch_path.write_bytes(data)
        print(f"  → {arch_path} ({len(data)} байт)")
    return 0


def cmd_fetch(args):
    """Массовая выгрузка по пресету. Резюмируемая."""
    eis_history.init()
    regions, pairs, dates = eis_history.preset_jobs(args.preset)
    print(f"[plan] preset={args.preset}  regions={len(regions)}  "
          f"types={len(pairs)}  dates={len(dates)}  всего партий={len(regions)*len(pairs)*len(dates)}")
    planned = eis_history.plan_batches(regions, pairs, dates, fz=args.fz)
    print(f"[plan] pending/error в очереди: {planned}")

    if args.phase1_only:
        eis_pipeline.run_phase1(workers=args.workers_phase1)
    elif args.phase2_only:
        eis_pipeline.run_phase2(workers=args.workers_phase2)
    else:
        eis_pipeline.run_interleaved(
            workers_phase1=args.workers_phase1,
            workers_phase2=args.workers_phase2,
        )

    s = eis_history.stats()
    print("\n=== eis_history.db ===")
    for k, v in s.items():
        print(f"  {k}: {v}")

    # Автоматический парсинг + пересчёт bench_cache — чтобы аналитика в UI
    # сразу увидела новые данные.
    if args.auto_parse:
        print("\n[auto-parse] парсю архивы в eis_analytics.db...")
        eis_analytics_loader.run_parse()
        print("\n=== eis_analytics.db ===")
        for k, v in eis_analytics.stats().items():
            print(f"  {k}: {v}")

        print("\n[auto-parse] пересчитываю bench_cache (может занять 20-30 мин)...")
        from core.analytics.cache import refresh_bench_cache
        r = refresh_bench_cache()
        print(f"[auto-parse] bench_cache: {r['rows_written']} строк из {r['combos_checked']} комбинаций")

    return 0


def cmd_parse(args):
    """Распарсить скачанные архивы в eis_analytics.db."""
    types: set[str] | None = None
    if args.types:
        types = set(args.types)
        unknown = types - eis_parsers.ALL_PARSED_TYPES
        if unknown:
            print(f"[warn] эти типы не парсятся (пропускаю): {sorted(unknown)}")
            types &= eis_parsers.ALL_PARSED_TYPES
    eis_analytics_loader.run_parse(types=types, limit=args.limit)
    print("\n=== eis_analytics.db ===")
    for k, v in eis_analytics.stats().items():
        print(f"  {k}: {v}")
    return 0


def cmd_stats(args):
    eis_history.init()
    s = eis_history.stats()
    print("=== eis_history.db ===")
    for k, v in s.items():
        print(f"  {k}: {v}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    pt = sub.add_parser("test", help="Один SOAP-запрос для проверки токена и структуры ответа")
    pt.add_argument("--fz", default="44", choices=["44", "223"])
    pt.add_argument("--region", default="77", help="Код региона (77 — Москва)")
    pt.add_argument("--subsystem", default="PRIZ", help="PRIZ | RPP | RGK | RBG | RD | RI")
    pt.add_argument("--doc-type", dest="doc_type", default="contract",
                    help="contract | purchaseNotice | protocol")
    pt.add_argument("--date", default=(date.today() - timedelta(days=7)).isoformat(),
                    help="YYYY-MM-DD (по умолчанию — неделю назад)")
    pt.add_argument("--fetch", action="store_true", help="Скачать первый архив")
    pt.set_defaults(func=cmd_test)

    pf = sub.add_parser("fetch", help="Массовая выгрузка по пресету (резюмируемая)")
    pf.add_argument("--preset", required=True,
                    help="top10-jan2025 | top10-h1-2025 | "
                         "top10-jan2026 | top10-feb2026 | top10-mar2026 | "
                         "top10-apr2026-full | top10-may2026 | top10-jun2026 | "
                         "top10-q1-2026 | top10-q2-2026 | top10-h1-2026 | "
                         "top10-apr2026 (legacy 1-20 apr) | smoke")
    pf.add_argument("--fz", default="44")
    pf.add_argument("--workers-phase1", dest="workers_phase1", type=int, default=20,
                    help="параллелизм SOAP. Лимит ДИС 90/60 всё равно общий.")
    pf.add_argument("--workers-phase2", dest="workers_phase2", type=int, default=5,
                    help="параллелизм скачивания архивов.")
    pf.add_argument("--phase1-only", action="store_true")
    pf.add_argument("--phase2-only", action="store_true")
    pf.add_argument("--auto-parse", action="store_true",
                    help="После скачивания запустить parse + refresh_bench_cache (всё готово к аналитике)")
    pf.add_argument("--skip-vpn", action="store_true",
                    help="НЕ управлять VPN (VPS в РФ — нечего переключать).")
    pf.set_defaults(func=cmd_fetch)

    pp = sub.add_parser("parse", help="Распарсить archives/ в eis_analytics.db")
    pp.add_argument("--types", nargs="+",
                    help="Ограничить список doc_type (по умолчанию все 9 ядровых)")
    pp.add_argument("--limit", type=int, default=None,
                    help="Максимум архивов (для отладки)")
    pp.set_defaults(func=cmd_parse)

    ps = sub.add_parser("stats", help="Статистика eis_history.db")
    ps.set_defaults(func=cmd_stats)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 1
    # test/fetch делают сетевые запросы — нужен РФ-IP (кроме VPS в РФ).
    if args.cmd in ("test", "fetch"):
        skip_vpn = getattr(args, "skip_vpn", False)
        if skip_vpn:
            return args.func(args)
        return with_ru_ip(lambda: args.func(args))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
