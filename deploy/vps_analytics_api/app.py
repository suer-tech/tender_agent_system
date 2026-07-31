from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from core.analytics.market import (
    customer_details,
    item_details,
    market_overview,
    supplier_details,
    time_series_by_month,
    top_customers,
    top_items_in_sector,
    top_sectors,
    top_suppliers,
)
from core.analytics.plans import (
    plans_available_years,
    plans_calendar,
    plans_overview,
    plans_top_customers,
    plans_top_sectors,
)


app = FastAPI(title="TenderAI Analytics API", version="1.0.0")

origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=origins != ["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    from core.storage.eis_analytics import DB_PATH
    return {"status": "ok", "database": str(DB_PATH), "database_exists": DB_PATH.exists()}


@app.get("/api/market/overview")
def api_market_overview(from_date: str, to_date: str, okpd2: str = "", region: str = ""):
    return market_overview(okpd2 or None, region or None, from_date, to_date)


@app.get("/api/market/top-sectors")
def api_top_sectors(from_date: str, to_date: str, region: str = "", limit: int = Query(20, ge=1, le=100)):
    return top_sectors(region or None, from_date, to_date, limit)


@app.get("/api/market/top-items-in-sector")
def api_top_items(from_date: str, to_date: str, okpd2: str, region: str = "", limit: int = Query(15, ge=1, le=100)):
    return top_items_in_sector(okpd2, region or None, from_date, to_date, limit)


@app.get("/api/market/item-details")
def api_item_details(
    from_date: str,
    to_date: str,
    okpd2_code: str,
    region: str = "",
    contracts_limit: int = Query(20, ge=1, le=100),
    contracts_offset: int = Query(0, ge=0),
    sort_by: str = "date",
    sort_dir: str = "desc",
):
    return item_details(okpd2_code, region or None, from_date, to_date,
                        contracts_limit, contracts_offset, sort_by, sort_dir)


@app.get("/api/market/top-customers")
def api_top_customers(from_date: str, to_date: str, okpd2: str = "", region: str = "", limit: int = Query(20, ge=1, le=100)):
    return top_customers(okpd2 or None, region or None, from_date, to_date, limit)


@app.get("/api/market/top-suppliers")
def api_top_suppliers(from_date: str, to_date: str, okpd2: str = "", region: str = "", limit: int = Query(20, ge=1, le=100)):
    return top_suppliers(okpd2 or None, region or None, from_date, to_date, limit)


@app.get("/api/market/timeseries")
def api_timeseries(from_date: str, to_date: str, okpd2: str = "", region: str = ""):
    return time_series_by_month(okpd2 or None, region or None, from_date, to_date)


@app.get("/api/market/customer-details")
def api_customer_details(
    from_date: str, to_date: str, inn: str,
    contracts_limit: int = Query(20, ge=1, le=100), contracts_offset: int = Query(0, ge=0),
    sort_by: str = "date", sort_dir: str = "desc",
):
    return customer_details(inn, from_date, to_date, contracts_limit, contracts_offset, sort_by, sort_dir)


@app.get("/api/market/supplier-details")
def api_supplier_details(
    from_date: str, to_date: str, inn: str,
    contracts_limit: int = Query(20, ge=1, le=100), contracts_offset: int = Query(0, ge=0),
    sort_by: str = "date", sort_dir: str = "desc",
):
    return supplier_details(inn, from_date, to_date, contracts_limit, contracts_offset, sort_by, sort_dir)


@app.get("/api/plans/years")
def api_plans_years():
    return {"years": plans_available_years()}


@app.get("/api/plans/overview")
def api_plans_overview(plan_year: Optional[int] = None, okpd2: str = "", region: str = ""):
    return plans_overview(plan_year, region or None, okpd2 or None)


@app.get("/api/plans/top-sectors")
def api_plans_top_sectors(plan_year: Optional[int] = None, region: str = "", limit: int = Query(30, ge=1, le=100)):
    return plans_top_sectors(plan_year, region or None, limit)


@app.get("/api/plans/top-customers")
def api_plans_top_customers(plan_year: Optional[int] = None, okpd2: str = "", region: str = "", limit: int = Query(20, ge=1, le=100)):
    return plans_top_customers(plan_year, region or None, okpd2 or None, limit)


@app.get("/api/plans/calendar")
def api_plans_calendar(plan_year: Optional[int] = None, okpd2: str = "", region: str = "", top_sectors: int = Query(8, ge=1, le=30)):
    return plans_calendar(plan_year, region or None, okpd2 or None, top_sectors)
