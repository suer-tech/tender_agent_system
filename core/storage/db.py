import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent.parent / "tenders.db"


def init():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT,
            customer TEXT,
            price TEXT,
            deadline TEXT,
            url TEXT,
            description TEXT,
            score INTEGER,
            summary TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            delivered INTEGER DEFAULT 0,
            found_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, external_id)
        );
        CREATE TABLE IF NOT EXISTS feedback (
            tender_id INTEGER,
            vote TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def exists(source: str, external_id: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM tenders WHERE source=? AND external_id=?",
            (source, external_id),
        ).fetchone()
        return row is not None


def save_pending(tender: dict) -> int:
    with _conn() as c:
        c.execute(
            """INSERT OR IGNORE INTO tenders
            (source, external_id, title, customer, price, deadline, url, description, status)
            VALUES (?,?,?,?,?,?,?,?, 'pending')""",
            (
                tender["source"], tender["external_id"], tender.get("title"),
                tender.get("customer"), tender.get("price"), tender.get("deadline"),
                tender.get("url"), tender.get("description"),
            ),
        )
        # если уже было — подтягиваем дедлайн/поля, когда они стали известны
        c.execute(
            """UPDATE tenders SET
                deadline = COALESCE(NULLIF(?, ''), deadline),
                price    = COALESCE(NULLIF(?, ''), price),
                url      = COALESCE(NULLIF(?, ''), url),
                title    = COALESCE(NULLIF(?, ''), title),
                customer = COALESCE(NULLIF(?, ''), customer)
            WHERE source=? AND external_id=?""",
            (
                tender.get("deadline") or "",
                tender.get("price") or "",
                tender.get("url") or "",
                tender.get("title") or "",
                tender.get("customer") or "",
                tender["source"], tender["external_id"],
            ),
        )
        row = c.execute(
            "SELECT id FROM tenders WHERE source=? AND external_id=?",
            (tender["source"], tender["external_id"]),
        ).fetchone()
        return row["id"] if row else None


def list_pending() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM tenders WHERE status='pending' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def update_verdict(tender_id: int, score: int, summary: str, reason: str, relevant: bool):
    status = "relevant" if relevant else "irrelevant"
    with _conn() as c:
        c.execute(
            "UPDATE tenders SET score=?, summary=?, reason=?, status=? WHERE id=?",
            (score, summary, reason, status, tender_id),
        )


def list_undelivered_relevant(min_score: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM tenders WHERE status='relevant' AND delivered=0 AND score>=? ORDER BY score DESC",
            (min_score,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_delivered(tender_id: int):
    with _conn() as c:
        c.execute("UPDATE tenders SET delivered=1 WHERE id=?", (tender_id,))


def stats() -> dict:
    with _conn() as c:
        rows = c.execute(
            "SELECT status, COUNT(*) as n FROM tenders GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}


def record_feedback(tender_id: int, vote: str):
    with _conn() as c:
        c.execute("INSERT INTO feedback (tender_id, vote) VALUES (?,?)", (tender_id, vote))
