# TenderAI unified API for VPS

Единый API над базой аналитики: аналитика, чат и поиск тендеров.

Сервис запускается из полного репозитория TenderAI, а база аналитики остаётся
отдельным файлом на VPS. В `.env` указываются `ANALYTICS_DB_PATH`,
`BICOTENDER_LOGIN`, `BICOTENDER_PASSWORD` и `SEARCH_LLM_*`.

Поиск использует все источники проекта: zakupki, RTS, B2B, Roseltorg,
Fabrikant и Bicotender. Запросы идут напрямую с VPS, без VPN.

## Локальный запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ANALYTICS_DB_PATH='C:\path\to\eis_analytics.db'
uvicorn apps.web.app:app --reload --port 8770
```

## VPS

Сервис слушает только `127.0.0.1:8770`; наружу его можно проксировать через nginx.
База открывается в read-only режиме, поэтому API не изменяет аналитические данные.
