"""БД исторической аналитики ЕИС. Отдельно от tenders.db.

tenders.db — воронка активного поиска (pending → relevant/irrelevant).
eis_history.db — слепок прошедших тендеров, контрактов, извещений для
аналитики: объём рынка, динамика, топ-заказчики, средние цены и т.п.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "eis_history.db"


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(
            """
            -- Партии загрузки: (fz × регион × подсистема × тип_документа × дата)
            -- это минимальная единица SOAP-вызова getDocsByOrgRegionRequest.
            CREATE TABLE IF NOT EXISTS download_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fz TEXT NOT NULL,                 -- 44 | 223
                region_code TEXT NOT NULL,        -- 77, 78, 50 ...
                subsystem TEXT NOT NULL,          -- PRIZ | RPP | RGK | RBG | RD | RI
                doc_type TEXT NOT NULL,           -- contract | purchaseNotice | protocol
                exact_date TEXT NOT NULL,         -- YYYY-MM-DD
                status TEXT DEFAULT 'pending',    -- pending | in_progress | ok | error
                request_id TEXT,                  -- uuid SOAP-запроса
                archive_count INTEGER DEFAULT 0,
                record_count INTEGER DEFAULT 0,
                error TEXT,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(fz, region_code, subsystem, doc_type, exact_date)
            );
            CREATE INDEX IF NOT EXISTS idx_batches_status ON download_batches(status);
            CREATE INDEX IF NOT EXISTS idx_batches_date ON download_batches(exact_date);

            -- Скачанные архивы: факт и метаданные (содержимое храним на диске в archives/).
            CREATE TABLE IF NOT EXISTS archives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                local_path TEXT,
                size_bytes INTEGER,
                sha256 TEXT,
                downloaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(batch_id) REFERENCES download_batches(id),
                UNIQUE(url)
            );

            -- Контракты 44-ФЗ / 223-ФЗ (основная витрина для аналитики).
            -- Структуру уточним после первого ответа сервиса; пока — минимум.
            CREATE TABLE IF NOT EXISTS contracts (
                reg_num TEXT PRIMARY KEY,
                fz TEXT NOT NULL,
                sign_date TEXT,
                price REAL,
                currency TEXT DEFAULT 'RUB',
                customer_inn TEXT,
                customer_name TEXT,
                customer_region TEXT,
                supplier_inn TEXT,
                supplier_name TEXT,
                okpd2_code TEXT,
                subject TEXT,
                source_archive_id INTEGER,
                loaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_archive_id) REFERENCES archives(id)
            );
            CREATE INDEX IF NOT EXISTS idx_contracts_fz ON contracts(fz);
            CREATE INDEX IF NOT EXISTS idx_contracts_sign_date ON contracts(sign_date);
            CREATE INDEX IF NOT EXISTS idx_contracts_customer ON contracts(customer_inn);
            CREATE INDEX IF NOT EXISTS idx_contracts_supplier ON contracts(supplier_inn);
            CREATE INDEX IF NOT EXISTS idx_contracts_okpd2 ON contracts(okpd2_code);
            CREATE INDEX IF NOT EXISTS idx_contracts_region ON contracts(customer_region);

            -- Извещения (начальные цены, контекст до контракта).
            CREATE TABLE IF NOT EXISTS notices (
                reg_num TEXT PRIMARY KEY,
                fz TEXT NOT NULL,
                publish_date TEXT,
                max_price REAL,
                customer_inn TEXT,
                customer_region TEXT,
                okpd2_code TEXT,
                subject TEXT,
                procurement_method TEXT,   -- электронный аукцион / конкурс / ...
                source_archive_id INTEGER,
                loaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(source_archive_id) REFERENCES archives(id)
            );
            CREATE INDEX IF NOT EXISTS idx_notices_publish_date ON notices(publish_date);
            CREATE INDEX IF NOT EXISTS idx_notices_customer ON notices(customer_inn);
            CREATE INDEX IF NOT EXISTS idx_notices_okpd2 ON notices(okpd2_code);
            """
        )


def upsert_batch(fz, region_code, subsystem, doc_type, exact_date) -> int:
    with conn() as c:
        c.execute(
            """INSERT OR IGNORE INTO download_batches
               (fz, region_code, subsystem, doc_type, exact_date)
               VALUES (?, ?, ?, ?, ?)""",
            (fz, region_code, subsystem, doc_type, exact_date),
        )
        row = c.execute(
            """SELECT id FROM download_batches
               WHERE fz=? AND region_code=? AND subsystem=? AND doc_type=? AND exact_date=?""",
            (fz, region_code, subsystem, doc_type, exact_date),
        ).fetchone()
        return row["id"]


def mark_batch_status(batch_id: int, status: str, **fields):
    cols = ["status=?"]
    vals = [status]
    for k, v in fields.items():
        cols.append(f"{k}=?")
        vals.append(v)
    vals.append(batch_id)
    with conn() as c:
        c.execute(f"UPDATE download_batches SET {', '.join(cols)} WHERE id=?", vals)


def list_pending_batches(limit: int | None = None) -> list[dict]:
    q = "SELECT * FROM download_batches WHERE status IN ('pending','error') ORDER BY id"
    args: tuple = ()
    if limit:
        q += " LIMIT ?"; args = (limit,)
    with conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def save_batch_result(batch_id: int, status: str, urls: list[str], request_id: str | None,
                      error: str | None = None):
    """Атомарно обновить статус партии и вписать archiveUrl'ы."""
    with conn() as c:
        c.execute(
            """UPDATE download_batches SET
                   status=?, archive_count=?, request_id=?, error=?,
                   finished_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (status, len(urls), request_id, error, batch_id),
        )
        for u in urls:
            c.execute(
                """INSERT OR IGNORE INTO archives (batch_id, url) VALUES (?, ?)""",
                (batch_id, u),
            )


def list_pending_archives(limit: int | None = None) -> list[dict]:
    q = """SELECT a.id, a.url, a.batch_id, b.region_code, b.subsystem, b.doc_type, b.exact_date
           FROM archives a JOIN download_batches b ON a.batch_id=b.id
           WHERE a.local_path IS NULL"""
    args: tuple = ()
    if limit:
        q += " LIMIT ?"; args = (limit,)
    with conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def mark_archive_downloaded(archive_id: int, local_path: str, size_bytes: int,
                            sha256: str | None = None):
    with conn() as c:
        c.execute(
            """UPDATE archives SET local_path=?, size_bytes=?, sha256=?,
                   downloaded_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (local_path, size_bytes, sha256, archive_id),
        )


TOP10_REGIONS = [
    "77",  # Москва
    "78",  # Санкт-Петербург
    "50",  # Московская область
    "16",  # Татарстан
    "66",  # Свердловская
    "23",  # Краснодарский
    "54",  # Новосибирская
    "61",  # Ростовская
    "52",  # Нижегородская
    "74",  # Челябинская
]

SUBSYSTEM_TYPES_44 = {
    "PRIZ": [
        "epClarificationDoc", "epClarificationDocRequest", "epClarificationResult",
        "epClarificationResultRequest", "epNoticeApplicationCancel",
        "epNoticeApplicationsAbsence", "epNotificationCancel",
        "epNotificationCancelFailure", "epNotificationEF2020",
        "epNotificationEOK2020", "epNotificationEZK2020", "epNotificationEZT2020",
        "epProtocolCancel", "epProtocolDeviation", "epProtocolEF2020Final",
        "epProtocolEF2020SubmitOffers", "epProtocolEOK2020Final",
        "epProtocolEOK2020FirstSections", "epProtocolEOK2020SecondSections",
        "epProtocolEZK2020Final", "epProtocolEZT2020Final",
        "epProtocolEvDevCancel", "epProtocolEvasion", "fcsNotification111",
        "fcsNotificationCancel", "fcsNotificationCancelFailure", "fcsPurchaseDocument",
    ],
    "RGK": [
        "contract", "contractAvailableForElAct", "contractCancel",
        "contractProcedure", "contractProcedureCancel",
    ],
    "RNP": ["unfairSupplier2022", "unfairSupplier2022Exclude", "unfairSupplierIKZ"],
    "UR": [
        "contractProcedureUnilateralRefusal", "contractProcedureUnilateralRefusalCancel",
        "parContractProcedureUnilateralRefusal", "parContractProcedureUnilateralRefusalCancel",
    ],
    "RJ": [
        "complaint", "complaintCancel", "complaintTransfer",
        "parElectronicComplaintAccept", "parElectronicComplaintRefusal", "tenderSuspension",
    ],
    "RPGZ": ["tenderPlan2020"],
}


def preset_jobs(preset: str) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """Вернуть (regions, [(subsystem, doc_type)], dates) по имени пресета."""
    from datetime import date, timedelta
    if preset == "top10-apr2026":
        regions = TOP10_REGIONS
        pairs = [(s, t) for s, types in SUBSYSTEM_TYPES_44.items() for t in types]
        dates = [(date(2026, 4, 1) + timedelta(days=i)).isoformat() for i in range(20)]
        return regions, pairs, dates
    if preset == "smoke":
        regions = ["77"]
        pairs = [("PRIZ", "epNotificationEF2020"), ("RGK", "contract")]
        dates = [(date.today() - timedelta(days=i)).isoformat() for i in (2, 3)]
        return regions, pairs, dates
    raise ValueError(f"Неизвестный пресет: {preset}. Доступно: top10-apr2026, smoke")


def plan_batches(regions: list[str], pairs: list[tuple[str, str]], dates: list[str],
                 fz: str = "44") -> int:
    """Вписать все (регион × подсистема × тип × дата) со статусом pending.
    Идемпотентно — existing rows не трогаем."""
    with conn() as c:
        for r in regions:
            for (subsys, doc_type) in pairs:
                for d in dates:
                    c.execute(
                        """INSERT OR IGNORE INTO download_batches
                           (fz, region_code, subsystem, doc_type, exact_date)
                           VALUES (?, ?, ?, ?, ?)""",
                        (fz, r, subsys, doc_type, d),
                    )
        total = c.execute(
            "SELECT COUNT(*) FROM download_batches WHERE status IN ('pending','error')"
        ).fetchone()[0]
    return total


def stats() -> dict:
    with conn() as c:
        batches = {
            r["status"]: r["n"]
            for r in c.execute(
                "SELECT status, COUNT(*) as n FROM download_batches GROUP BY status"
            ).fetchall()
        }
        return {
            "batches": batches,
            "contracts": c.execute("SELECT COUNT(*) FROM contracts").fetchone()[0],
            "notices": c.execute("SELECT COUNT(*) FROM notices").fetchone()[0],
            "archives": c.execute("SELECT COUNT(*) FROM archives").fetchone()[0],
        }
