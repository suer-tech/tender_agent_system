"""Оркестратор парсинга ZIP-архивов в eis_analytics.db.

Обход archives/<date>/<subsystem>/<doc_type>/<region>/*.zip, распаковка XML,
вызов парсера, UPSERT в соответствующую таблицу.

Идемпотентно: повторный запуск перезаписывает строки с теми же PK.
"""
from __future__ import annotations

import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import parsers as P
from core.storage import eis_analytics

ARCHIVES_ROOT = Path(__file__).parent.parent.parent.parent / "archives"


def _log(msg: str):
    print(msg, flush=True)


def _walk_archives(doc_types: set[str]) -> list[tuple[Path, str, str]]:
    """Вернуть [(zip_path, doc_type, region), ...] для указанных типов."""
    out = []
    if not ARCHIVES_ROOT.exists():
        return out
    for date_dir in sorted(ARCHIVES_ROOT.iterdir()):
        if not date_dir.is_dir():
            continue
        for subsys_dir in date_dir.iterdir():
            if not subsys_dir.is_dir():
                continue
            for dt_dir in subsys_dir.iterdir():
                if not dt_dir.is_dir() or dt_dir.name not in doc_types:
                    continue
                for region_dir in dt_dir.iterdir():
                    if not region_dir.is_dir():
                        continue
                    for zip_path in region_dir.glob("*.zip"):
                        out.append((zip_path, dt_dir.name, region_dir.name))
    return out


def _upsert_notice(con: sqlite3.Connection, notice: dict, items: list[dict],
                   ikz_codes: list[str], src: str):
    cols = list(notice.keys())
    notice["source_archive"] = src
    cols.append("source_archive")
    placeholders = ",".join("?" * len(cols))
    con.execute(
        f"INSERT OR REPLACE INTO notices ({','.join(cols)}) VALUES ({placeholders})",
        [notice[k] for k in cols],
    )
    reg = notice.get("reg_number")
    if not reg:
        return
    con.execute("DELETE FROM notice_items WHERE reg_number=?", (reg,))
    for it in items:
        it["reg_number"] = reg
        con.execute(
            """INSERT OR REPLACE INTO notice_items
               (reg_number, index_num, okpd2_code, okpd2_name, ktru_code, ktru_name,
                name, price, quantity, okei_code)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (reg, it["index_num"], it["okpd2_code"], it["okpd2_name"],
             it["ktru_code"], it["ktru_name"], it["name"], it["price"],
             it["quantity"], it["okei_code"]),
        )
    # ИКЗ — отдельная таблица, обновляем атомарно.
    con.execute("DELETE FROM notice_ikz_codes WHERE reg_number=?", (reg,))
    for code in ikz_codes:
        con.execute(
            "INSERT OR IGNORE INTO notice_ikz_codes (reg_number, ikz) VALUES (?, ?)",
            (reg, code),
        )


def _upsert_protocol(con: sqlite3.Connection, row: dict, src: str):
    row["source_archive"] = src
    cols = list(row.keys())
    ph = ",".join("?" * len(cols))
    con.execute(
        f"INSERT OR REPLACE INTO protocols ({','.join(cols)}) VALUES ({ph})",
        [row[k] for k in cols],
    )


def _upsert_contract(con: sqlite3.Connection, contract: dict, items: list[dict], src: str):
    contract["source_archive"] = src
    cols = list(contract.keys())
    ph = ",".join("?" * len(cols))
    con.execute(
        f"INSERT OR REPLACE INTO contracts ({','.join(cols)}) VALUES ({ph})",
        [contract[k] for k in cols],
    )
    if not contract.get("reg_num"):
        return
    con.execute("DELETE FROM contract_items WHERE reg_num=?", (contract["reg_num"],))
    for it in items:
        it["reg_num"] = contract["reg_num"]
        con.execute(
            """INSERT OR REPLACE INTO contract_items
               (reg_num, index_num, okpd2_code, okpd2_name, ktru_code, ktru_name,
                name, price, quantity, sum_amount, okei_code, vat_code)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (it["reg_num"], it["index_num"], it["okpd2_code"], it["okpd2_name"],
             it["ktru_code"], it["ktru_name"], it["name"], it["price"],
             it["quantity"], it["sum_amount"], it["okei_code"], it["vat_code"]),
        )


def _upsert_complaint(con: sqlite3.Connection, row: dict, src: str):
    row["source_archive"] = src
    cols = list(row.keys())
    ph = ",".join("?" * len(cols))
    con.execute(
        f"INSERT OR REPLACE INTO complaints ({','.join(cols)}) VALUES ({ph})",
        [row[k] for k in cols],
    )


def _upsert_refusal(con: sqlite3.Connection, row: dict, src: str):
    row["source_archive"] = src
    cols = list(row.keys())
    ph = ",".join("?" * len(cols))
    con.execute(
        f"INSERT OR REPLACE INTO unilateral_refusals ({','.join(cols)}) VALUES ({ph})",
        [row[k] for k in cols],
    )


def _upsert_unfair(con: sqlite3.Connection, row: dict, founders: list[dict], src: str):
    row["source_archive"] = src
    cols = list(row.keys())
    ph = ",".join("?" * len(cols))
    con.execute(
        f"INSERT OR REPLACE INTO unfair_suppliers ({','.join(cols)}) VALUES ({ph})",
        [row[k] for k in cols],
    )
    if not row.get("reg_number"):
        return
    con.execute(
        "DELETE FROM unfair_supplier_founders WHERE unfair_reg_number=?",
        (row["reg_number"],),
    )
    for f in founders:
        con.execute(
            """INSERT INTO unfair_supplier_founders
               (unfair_reg_number, founder_inn, founder_name, role_code, role_name)
               VALUES (?,?,?,?,?)""",
            (row["reg_number"], f["founder_inn"], f["founder_name"],
             f["role_code"], f["role_name"]),
        )


def _upsert_plan(con: sqlite3.Connection, plan: dict, positions: list[dict], src: str):
    plan["source_archive"] = src
    cols = list(plan.keys())
    ph = ",".join("?" * len(cols))
    con.execute(
        f"INSERT OR REPLACE INTO tender_plans ({','.join(cols)}) VALUES ({ph})",
        [plan[k] for k in cols],
    )
    if not plan.get("plan_number"):
        return
    # Перетираем все позиции этого плана (новая версия плана может удалить часть)
    con.execute("DELETE FROM tender_plan_positions WHERE plan_number=?", (plan["plan_number"],))
    if not positions:
        return
    pos_cols = list(positions[0].keys()) + ["source_archive"]
    pos_ph = ",".join("?" * len(pos_cols))
    for p in positions:
        if not p.get("position_number"):
            continue
        p["source_archive"] = src
        con.execute(
            f"INSERT OR REPLACE INTO tender_plan_positions ({','.join(pos_cols)}) VALUES ({pos_ph})",
            [p[k] for k in pos_cols],
        )


def run_parse(types: set[str] | None = None, limit: int | None = None) -> dict:
    """Пройти по архивам, распарсить, записать в eis_analytics.db.

    Args:
        types: подмножество doc_type для обработки. None = все 9 ядровых.
        limit: максимум архивов (для отладки).
    """
    eis_analytics.init()
    if types is None:
        types = P.ALL_PARSED_TYPES

    archives = _walk_archives(types)
    if limit:
        archives = archives[:limit]
    total = len(archives)
    _log(f"[parse] к обработке {total} архивов, типов: {len(types)}")
    if total == 0:
        return {"archives": 0}

    run_started = datetime.now().isoformat(timespec="seconds")
    t0 = time.time()

    stats = {
        "archives": 0, "xmls": 0, "errors": 0,
        "notice": 0, "protocol": 0, "contract": 0,
        "complaint": 0, "refusal": 0, "unfair": 0, "plan": 0,
    }

    with eis_analytics.conn() as con:
        for i, (zpath, doc_type, region) in enumerate(archives, 1):
            try:
                with zipfile.ZipFile(zpath) as z:
                    for name in z.namelist():
                        if not name.lower().endswith(".xml"):
                            continue
                        with z.open(name) as f:
                            body = f.read()
                        stats["xmls"] += 1
                        try:
                            res = P.parse_xml(body, region_hint=region)
                        except Exception as e:
                            stats["errors"] += 1
                            if stats["errors"] <= 5:
                                _log(f"  [err] {zpath.name}/{name}: {e}")
                            continue
                        if res is None:
                            continue
                        cat, data = res
                        src = f"{zpath.parent.name}/{zpath.name}/{name}"
                        try:
                            if cat == "notice":
                                _upsert_notice(con, *data, src)
                            elif cat == "protocol":
                                _upsert_protocol(con, data, src)
                            elif cat == "contract":
                                _upsert_contract(con, *data, src)
                            elif cat == "complaint":
                                _upsert_complaint(con, data, src)
                            elif cat == "refusal":
                                _upsert_refusal(con, data, src)
                            elif cat == "unfair":
                                _upsert_unfair(con, *data, src)
                            elif cat == "plan":
                                _upsert_plan(con, *data, src)
                            stats[cat] += 1
                        except sqlite3.Error as e:
                            stats["errors"] += 1
                            if stats["errors"] <= 5:
                                _log(f"  [sql] {zpath.name}/{name}: {e}")
                stats["archives"] += 1
            except zipfile.BadZipFile:
                stats["errors"] += 1
                _log(f"  [bad zip] {zpath}")
                continue

            if i % 100 == 0 or i == total:
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed > 0 else 0
                eta = (total - i) / rate / 60 if rate > 0 else 0
                _log(f"  [{i}/{total}] xmls={stats['xmls']} err={stats['errors']} "
                     f"{rate:.1f} arc/s, ETA {eta:.1f} min")
                con.commit()

        # лог прогона
        con.execute(
            """INSERT INTO parse_runs
               (started_at, finished_at, archives_total, archives_processed,
                xmls_processed, errors, doc_types)
               VALUES (?,?,?,?,?,?,?)""",
            (run_started, datetime.now().isoformat(timespec="seconds"),
             total, stats["archives"], stats["xmls"], stats["errors"],
             ",".join(sorted(types))),
        )

    _log(f"[parse] done за {time.time()-t0:.1f} сек: {stats}")
    return stats
