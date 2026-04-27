"""Структурированная витрина для аналитики ЕИС.

Отдельная БД от eis_history.db: там учёт скачивания архивов, здесь — разобранные
данные (notices, contracts, complaints, ...). UPSERT по первичным ключам —
повторный парсинг тех же файлов безопасен.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "eis_analytics.db"


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _migrate_tender_plans(c: sqlite3.Connection):
    """Добить недостающие колонки в существующую tender_plans (если БД создана
    до раздела «Планы»). Безопасно для свежей БД — там CREATE TABLE сам
    создаст всё, и эти ALTER просто пропустятся (колонки уже есть)."""
    has_table = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tender_plans'"
    ).fetchone()
    if not has_table:
        return
    existing = {r[1] for r in c.execute("PRAGMA table_info(tender_plans)").fetchall()}
    additions = [
        ("version_number", "INTEGER"),
        ("plan_year", "INTEGER"),
        ("plan_period_first", "INTEGER"),
        ("plan_period_second", "INTEGER"),
        ("customer_kpp", "TEXT"),
    ]
    for col, typ in additions:
        if col not in existing:
            c.execute(f"ALTER TABLE tender_plans ADD COLUMN {col} {typ}")


def init():
    with conn() as c:
        _migrate_tender_plans(c)
        c.executescript(
            """
            -- ============ ИЗВЕЩЕНИЯ (PRIZ/epNotification*) ============
            CREATE TABLE IF NOT EXISTS notices (
                reg_number TEXT PRIMARY KEY,          -- purchaseNumber
                version INTEGER,
                doc_type TEXT,                        -- epNotificationEF2020/EOK2020/EZK2020/EZT2020
                publish_date TEXT,
                submit_start_dt TEXT,
                submit_end_dt TEXT,
                max_price REAL,                       -- НМЦК
                currency TEXT,
                placing_way_code TEXT,                -- EAP20/EOK20/EZK20/EZT
                placing_way_name TEXT,
                etp_code TEXT,
                etp_name TEXT,
                purchase_object TEXT,                 -- текст-описание
                customer_reg_num TEXT,
                customer_inn TEXT,
                customer_kpp TEXT,
                customer_name TEXT,
                customer_region TEXT,                 -- берём из пути к архиву
                exec_start_date TEXT,
                exec_end_date TEXT,
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_notices_customer ON notices(customer_inn);
            CREATE INDEX IF NOT EXISTS idx_notices_publish ON notices(publish_date);
            CREATE INDEX IF NOT EXISTS idx_notices_region ON notices(customer_region);

            -- ИКЗ-коды извещения (n:1 на notice). Нужно для матчинга
            -- извещений с позициями плана-графика: одна позиция плана → один ИКЗ;
            -- одно извещение может покрывать несколько ИКЗ (мультилот).
            -- Если ИКЗ позиции плана появился здесь — закупка уже запущена,
            -- в «Календаре возможностей» её скрываем.
            CREATE TABLE IF NOT EXISTS notice_ikz_codes (
                reg_number TEXT NOT NULL,
                ikz TEXT NOT NULL,
                PRIMARY KEY (reg_number, ikz)
            );
            CREATE INDEX IF NOT EXISTS idx_notice_ikz ON notice_ikz_codes(ikz);
            -- «Канонический» ИКЗ — без 27-29 (это «номер лота в извещении»;
            -- в позиции плана он всегда 000, а в извещении становится реальным).
            -- Матчинг план↔извещение должен идти по каноническому виду.
            CREATE INDEX IF NOT EXISTS idx_notice_ikz_canon
                ON notice_ikz_codes(SUBSTR(ikz,1,26) || SUBSTR(ikz,30));

            -- позиции извещения (объект закупки разбит по КТРУ/ОКПД2)
            CREATE TABLE IF NOT EXISTS notice_items (
                reg_number TEXT,
                index_num INTEGER,
                okpd2_code TEXT,
                okpd2_name TEXT,
                ktru_code TEXT,
                ktru_name TEXT,
                name TEXT,
                price REAL,
                quantity REAL,
                okei_code TEXT,                       -- единица измерения
                PRIMARY KEY (reg_number, index_num)
            );
            CREATE INDEX IF NOT EXISTS idx_notice_items_okpd2 ON notice_items(okpd2_code);

            -- ============ ПРОТОКОЛЫ ИТОГОВЫЕ (PRIZ/epProtocol*Final) ============
            CREATE TABLE IF NOT EXISTS protocols (
                reg_number TEXT,                      -- номер протокола
                purchase_number TEXT,                 -- связка с notices.reg_number
                doc_type TEXT,                        -- epProtocolEF2020Final/EOK2020Final/...
                publish_date TEXT,
                participants_count INTEGER,           -- сколько участников всего
                winner_inn TEXT,                      -- победитель (первый)
                winner_name TEXT,
                winner_is_individual INTEGER,
                final_price REAL,                     -- цена победителя
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (reg_number, doc_type)
            );
            CREATE INDEX IF NOT EXISTS idx_protocols_purchase ON protocols(purchase_number);
            CREATE INDEX IF NOT EXISTS idx_protocols_winner ON protocols(winner_inn);

            -- ============ КОНТРАКТЫ (RGK/contract) ============
            CREATE TABLE IF NOT EXISTS contracts (
                reg_num TEXT PRIMARY KEY,             -- регистрационный № контракта
                purchase_number TEXT,                 -- связка с notices
                publish_date TEXT,
                sign_date TEXT,
                contract_price REAL,
                currency TEXT,
                contract_subject TEXT,
                advance_percent REAL,
                exec_start_date TEXT,
                exec_end_date TEXT,
                customer_reg_num TEXT,
                customer_inn TEXT,
                customer_kpp TEXT,
                customer_name TEXT,
                customer_region TEXT,
                supplier_inn TEXT,
                supplier_kpp TEXT,
                supplier_name TEXT,
                supplier_type TEXT,                   -- legalEntityRF/individualRF/foreignOrg/IP
                placing_foundation TEXT,              -- singleCustomer.reason.name
                plan_2020_number TEXT,                -- связка с RPGZ
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_contracts_purchase ON contracts(purchase_number);
            CREATE INDEX IF NOT EXISTS idx_contracts_customer ON contracts(customer_inn);
            CREATE INDEX IF NOT EXISTS idx_contracts_supplier ON contracts(supplier_inn);
            CREATE INDEX IF NOT EXISTS idx_contracts_sign ON contracts(sign_date);
            CREATE INDEX IF NOT EXISTS idx_contracts_region ON contracts(customer_region);

            -- позиции контракта
            CREATE TABLE IF NOT EXISTS contract_items (
                reg_num TEXT,
                index_num INTEGER,
                okpd2_code TEXT,
                okpd2_name TEXT,
                ktru_code TEXT,
                ktru_name TEXT,
                name TEXT,
                price REAL,
                quantity REAL,
                sum_amount REAL,
                okei_code TEXT,
                vat_code TEXT,
                PRIMARY KEY (reg_num, index_num)
            );
            CREATE INDEX IF NOT EXISTS idx_contract_items_okpd2 ON contract_items(okpd2_code);

            -- ============ ЖАЛОБЫ (RJ/complaint) ============
            CREATE TABLE IF NOT EXISTS complaints (
                reg_number TEXT PRIMARY KEY,
                reg_date TEXT,
                publish_date TEXT,
                ko_name TEXT,                         -- ФАС
                ko_inn TEXT,
                ko_region TEXT,                       -- из addr
                customer_inn TEXT,
                customer_name TEXT,
                applicant_inn TEXT,
                applicant_name TEXT,
                applicant_type TEXT,                  -- legalEntity/individual/IP/foreign
                purchase_number TEXT,                 -- на какую закупку
                purchase_name TEXT,
                appeal_action_code TEXT,
                appeal_action_name TEXT,
                text_summary TEXT,
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_complaints_customer ON complaints(customer_inn);
            CREATE INDEX IF NOT EXISTS idx_complaints_applicant ON complaints(applicant_inn);
            CREATE INDEX IF NOT EXISTS idx_complaints_purchase ON complaints(purchase_number);

            -- ============ ОДНОСТОРОННИЕ ОТКАЗЫ (UR) ============
            CREATE TABLE IF NOT EXISTS unilateral_refusals (
                reg_number TEXT PRIMARY KEY,
                publish_date TEXT,
                initiator TEXT,                       -- 'customer' | 'supplier'
                contract_reg_num TEXT,                -- связка с contracts.reg_num
                customer_inn TEXT,
                customer_name TEXT,
                supplier_inn TEXT,
                supplier_name TEXT,
                reason_summary TEXT,
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_refusals_contract ON unilateral_refusals(contract_reg_num);
            CREATE INDEX IF NOT EXISTS idx_refusals_supplier ON unilateral_refusals(supplier_inn);

            -- ============ РНП (RNP/unfairSupplier2022) ============
            CREATE TABLE IF NOT EXISTS unfair_suppliers (
                reg_number TEXT PRIMARY KEY,
                version INTEGER,
                publish_date TEXT,
                first_version_date TEXT,
                approve_org_name TEXT,                -- ФАС которая внесла
                create_reason TEXT,                   -- CANCEL_CONTRACT / EVASION / ...
                supplier_inn TEXT,
                supplier_kpp TEXT,
                supplier_name TEXT,
                supplier_short_name TEXT,
                supplier_type TEXT,                   -- legalEntityRF/individualRF/IP/foreign
                auto_exclude_date TEXT,
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_unfair_suppliers_inn ON unfair_suppliers(supplier_inn);

            -- учредители из РНП (ловим аффилированность)
            CREATE TABLE IF NOT EXISTS unfair_supplier_founders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unfair_reg_number TEXT,
                founder_inn TEXT,
                founder_name TEXT,
                role_code TEXT,
                role_name TEXT,
                FOREIGN KEY (unfair_reg_number) REFERENCES unfair_suppliers(reg_number)
            );
            CREATE INDEX IF NOT EXISTS idx_unfair_founders_inn ON unfair_supplier_founders(founder_inn);

            -- ============ ПЛАНЫ-ГРАФИКИ (RPGZ/tenderPlan2020) ============
            -- Заголовок плана: один заказчик публикует один план на год
            -- (plan_year), который покрывает текущий + 2 следующих года
            -- (plan_period_first, plan_period_second). Версия растёт при правках.
            CREATE TABLE IF NOT EXISTS tender_plans (
                plan_number TEXT PRIMARY KEY,
                version_number INTEGER,
                plan_year INTEGER,
                plan_period_first INTEGER,
                plan_period_second INTEGER,
                publish_date TEXT,
                customer_inn TEXT,
                customer_kpp TEXT,
                customer_name TEXT,
                customer_region TEXT,
                total_amount REAL,
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tender_plans_customer ON tender_plans(customer_inn);
            CREATE INDEX IF NOT EXISTS idx_tender_plans_year ON tender_plans(plan_year);
            CREATE INDEX IF NOT EXISTS idx_tender_plans_region ON tender_plans(customer_region);

            -- Позиции плана: одна строка = одна запланированная закупка.
            -- Гранулярность по времени — год (publishYear). Финансы:
            -- total — суммарно по всем годам, currentYear — текущий plan_year.
            CREATE TABLE IF NOT EXISTS tender_plan_positions (
                position_number TEXT PRIMARY KEY,     -- positionNumber, уникален глобально
                plan_number TEXT NOT NULL,            -- FK на tender_plans
                ikz TEXT,                             -- идентификационный код закупки
                purchase_number TEXT,                 -- порядковый внутри плана
                publish_year INTEGER,                 -- ГОД, когда планируется выйти на торги
                okpd2_code TEXT,
                okpd2_name TEXT,
                purchase_object TEXT,                 -- текстовое описание объекта
                kvr_code TEXT,                        -- вид расходов бюджета (244, 247...)
                position_canceled INTEGER DEFAULT 0,  -- 1 если позиция отменена
                public_discussion INTEGER DEFAULT 0,
                position_publish_date TEXT,
                position_last_update TEXT,
                amount_total REAL,                    -- финансы на все годы
                amount_current_year REAL,             -- финансы на plan_year
                amount_first_year REAL,
                amount_second_year REAL,
                customer_inn TEXT,                    -- денормализовано из плана для быстрых запросов
                customer_region TEXT,
                plan_year INTEGER,                    -- денормализовано из плана
                source_archive TEXT,
                parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_plan_pos_plan ON tender_plan_positions(plan_number);
            CREATE INDEX IF NOT EXISTS idx_plan_pos_okpd2 ON tender_plan_positions(okpd2_code);
            CREATE INDEX IF NOT EXISTS idx_plan_pos_customer ON tender_plan_positions(customer_inn);
            CREATE INDEX IF NOT EXISTS idx_plan_pos_year ON tender_plan_positions(publish_year);
            CREATE INDEX IF NOT EXISTS idx_plan_pos_region ON tender_plan_positions(customer_region);
            CREATE INDEX IF NOT EXISTS idx_plan_pos_active ON tender_plan_positions(position_canceled, publish_year);
            -- См. notice_ikz_codes выше — единая «каноническая» форма для матчинга.
            CREATE INDEX IF NOT EXISTS idx_plan_pos_ikz_canon
                ON tender_plan_positions(SUBSTR(ikz,1,26) || SUBSTR(ikz,30));

            -- лог прогонов парсера
            CREATE TABLE IF NOT EXISTS parse_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                archives_total INTEGER,
                archives_processed INTEGER,
                xmls_processed INTEGER,
                errors INTEGER,
                doc_types TEXT,
                note TEXT
            );

            -- ============ BENCH CACHE (материализованные агрегаты) ============
            -- Пересчитывается в core.analytics.cache.refresh_bench_cache
            -- okpd2_prefix: '62', '62.01', '62.01.12' — разная гранулярность
            -- region_code: '77' или '' (= вся РФ)
            CREATE TABLE IF NOT EXISTS bench_cache (
                okpd2_prefix TEXT NOT NULL,
                region_code TEXT NOT NULL DEFAULT '',
                period_months INTEGER NOT NULL,
                sample_size INTEGER NOT NULL,
                nmck_median REAL,
                nmck_p25 REAL,
                nmck_p75 REAL,
                final_price_median REAL,
                final_price_p25 REAL,
                final_price_p75 REAL,
                discount_pct_median REAL,
                discount_pct_p25 REAL,
                discount_pct_p75 REAL,
                contracts_with_discount INTEGER,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (okpd2_prefix, region_code, period_months)
            );
            CREATE INDEX IF NOT EXISTS idx_bench_cache_okpd2 ON bench_cache(okpd2_prefix);
            """
        )


def stats() -> dict:
    with conn() as c:
        s = {}
        for table in ["notices", "notice_items", "protocols", "contracts",
                       "contract_items", "complaints", "unilateral_refusals",
                       "unfair_suppliers", "unfair_supplier_founders",
                       "tender_plans", "tender_plan_positions"]:
            s[table] = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return s
