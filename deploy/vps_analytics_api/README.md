# TenderAI Analytics API for VPS

Отдельный read-only API над `eis_analytics.db`.

## Локальный запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ANALYTICS_DB_PATH='C:\path\to\eis_analytics.db'
uvicorn app:app --reload --port 8770
```

## VPS

Сервис слушает только `127.0.0.1:8770`; наружу его можно проксировать через nginx.
База открывается в read-only режиме, поэтому API не изменяет аналитические данные.
