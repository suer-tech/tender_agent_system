"""Pipeline массовой выгрузки ЕИС ДИС.

Phase 1: SOAP getDocsByOrgRegion на каждую партию (регион × тип × дата),
    собираем archiveUrl. Rate-limiter 90/60 — один общий на пул.
Phase 2: параллельное скачивание архивов через тот же токен.

Режим по умолчанию — подённый (interleaved): для каждой даты сначала
phase 1 (получение URL), затем phase 2 (скачивание архивов), потом
следующая дата. Это предотвращает протухание ссылок на архивы.
"""
from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .dis import EisDisClient, EisDisError, EisDisRateError
from .rate import TokenBucket
from core.storage import eis_history


ARCHIVES_ROOT = Path(__file__).parent.parent.parent.parent / "archives"


def _log(msg: str):
    print(msg, flush=True)


def run_phase1(workers: int = 20, limit: int | None = None,
               rate_limiter: TokenBucket | None = None,
               exact_date: str | None = None) -> dict:
    """SOAP по pending батчам. exact_date — фильтр по конкретной дате."""
    eis_history.init()
    batches = eis_history.list_pending_batches(limit, exact_date=exact_date)
    total = len(batches)
    if total == 0:
        _log("[phase1] нет pending — всё уже обработано")
        return {"ok": 0, "empty": 0, "error": 0, "archives": 0}

    _log(f"[phase1] стартую {total} партий, {workers} воркеров, rate=90/60")
    rate = rate_limiter or TokenBucket(90, 60.0)
    client = EisDisClient(rate_limiter=rate)

    stats = {"ok": 0, "empty": 0, "error": 0, "archives": 0}
    lock = threading.Lock()
    done = 0

    def work(b: dict):
        nonlocal done
        try:
            res = client.get_docs_by_org_region(
                fz=b["fz"], region_code=b["region_code"],
                subsystem=b["subsystem"], doc_type=b["doc_type"],
                exact_date=b["exact_date"],
            )
            urls = res["archive_urls"]
            eis_history.save_batch_result(
                b["id"], "ok" if urls else "empty", urls, res["request_id"]
            )
            with lock:
                if urls:
                    stats["ok"] += 1; stats["archives"] += len(urls)
                else:
                    stats["empty"] += 1
        except (EisDisError, EisDisRateError) as e:
            eis_history.save_batch_result(b["id"], "error", [], None, str(e)[:500])
            with lock:
                stats["error"] += 1
        finally:
            with lock:
                done_now = done = done + 1
            if done_now % 50 == 0 or done_now == total:
                _log(f"  [{done_now}/{total}] ok={stats['ok']} empty={stats['empty']} "
                     f"err={stats['error']} arc={stats['archives']}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in as_completed([ex.submit(work, b) for b in batches]):
            pass

    _log(f"[phase1] готово: {stats}")
    return stats


def _archive_local_path(batch: dict, url: str) -> Path:
    """<root>/<exact_date>/<subsystem>/<doc_type>/<region>/<hash>.zip"""
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    return (ARCHIVES_ROOT
            / batch["exact_date"] / batch["subsystem"] / batch["doc_type"]
            / batch["region_code"] / f"{h}.zip")


def run_phase2(workers: int = 5, limit: int | None = None,
               rate_limiter: TokenBucket | None = None,
               exact_date: str | None = None) -> dict:
    """Скачать архивы с local_path=NULL. exact_date — фильтр по дате."""
    eis_history.init()
    todo = eis_history.list_pending_archives(limit, exact_date=exact_date)
    total = len(todo)
    if total == 0:
        _log("[phase2] нет не-скачанных архивов")
        return {"ok": 0, "error": 0, "bytes": 0}

    _log(f"[phase2] качаю {total} архивов, {workers} параллельно -> {ARCHIVES_ROOT}")
    rate = rate_limiter or TokenBucket(90, 60.0)
    client = EisDisClient(rate_limiter=rate)

    stats = {"ok": 0, "error": 0, "bytes": 0}
    lock = threading.Lock()
    done = 0

    def work(a: dict):
        nonlocal done
        path = _archive_local_path(a, a["url"])
        try:
            if path.exists() and path.stat().st_size > 0:
                body = path.read_bytes()
            else:
                body = client.download_archive(a["url"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            sha = hashlib.sha256(body).hexdigest()
            eis_history.mark_archive_downloaded(a["id"], str(path), len(body), sha)
            with lock:
                stats["ok"] += 1; stats["bytes"] += len(body)
        except Exception as e:
            with lock:
                stats["error"] += 1
            _log(f"  err [{a['id']}] {type(e).__name__}: {str(e)[:120]}")
        finally:
            with lock:
                done_now = done = done + 1
            if done_now % 100 == 0 or done_now == total:
                mb = stats["bytes"] / 1024 / 1024
                _log(f"  [{done_now}/{total}] ok={stats['ok']} err={stats['error']} {mb:.1f} MB")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _ in as_completed([ex.submit(work, a) for a in todo]):
            pass

    _log(f"[phase2] готово: {stats['ok']} OK, {stats['error']} err, "
         f"{stats['bytes']/1024/1024:.1f} MB")
    return stats


def run_interleaved(workers_phase1: int = 20, workers_phase2: int = 5) -> dict:
    """Подённый режим: phase1 + phase2 для каждой даты, затем следующая.

    Перед обработкой каждой даты автоматически сбрасывает протухшие ссылки
    (архивы с local_path=NULL) и переводит их батчи обратно в pending,
    чтобы phase1 получила свежие URL.
    """
    eis_history.init()
    dates = eis_history.list_dates_needing_work()
    if not dates:
        _log("[fetch] нет дат для обработки")
        return {"dates": 0}

    _log(f"[fetch] подённый режим: {len(dates)} дат ({dates[0]} .. {dates[-1]})")
    rate = TokenBucket(90, 60.0)

    totals = {
        "dates": len(dates),
        "p1_ok": 0, "p1_empty": 0, "p1_err": 0, "p1_archives": 0,
        "p2_ok": 0, "p2_err": 0, "p2_bytes": 0,
    }

    for i, d in enumerate(dates, 1):
        _log(f"\n{'='*50}")
        _log(f"  день {i}/{len(dates)}: {d}")
        _log(f"{'='*50}")

        stale = eis_history.reset_stale_archives(d)
        if stale:
            _log(f"  [reset] очищено {stale} протухших ссылок, батчи -> pending")

        s1 = run_phase1(workers=workers_phase1, rate_limiter=rate, exact_date=d)
        totals["p1_ok"] += s1.get("ok", 0)
        totals["p1_empty"] += s1.get("empty", 0)
        totals["p1_err"] += s1.get("error", 0)
        totals["p1_archives"] += s1.get("archives", 0)

        s2 = run_phase2(workers=workers_phase2, rate_limiter=rate, exact_date=d)
        totals["p2_ok"] += s2.get("ok", 0)
        totals["p2_err"] += s2.get("error", 0)
        totals["p2_bytes"] += s2.get("bytes", 0)

    _log(f"\n{'='*50}")
    _log(f"[fetch] итого за {totals['dates']} дат:")
    _log(f"  phase1: ok={totals['p1_ok']} empty={totals['p1_empty']} "
         f"err={totals['p1_err']} archives={totals['p1_archives']}")
    mb = totals["p2_bytes"] / 1024 / 1024
    _log(f"  phase2: ok={totals['p2_ok']} err={totals['p2_err']} {mb:.1f} MB")
    return totals
