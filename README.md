# Tender Agent — тендерная аналитическая платформа

Сервис для поиска, оценки и анализа тендеров 44-ФЗ / 223-ФЗ / коммерческих площадок. Состоит из четырёх частей:

1. **Поиск в реальном времени** — Telegram-бот и веб-чат (`aixmode.online`) парсят zakupki.gov.ru и 6 коммерческих площадок, ИИ-агент оценивает релевантность под профиль пользователя.
2. **ЕИС-выгрузка** — SOAP-клиент к ДИС zakupki.gov.ru, рейт-лимитированный (90 req/min), докачивает архивы за указанный период по 10 ключевым регионам.
3. **Аналитическая витрина** — парсер ZIP→XML→SQL: 1.8 млн строк по извещениям, протоколам, контрактам, жалобам, РНП, планам-графикам за апрель 2026.
4. **LLM-бэкенд** — через OpenRouter (работает из РФ) или Claude Code CLI (опция).

---

## AI Agent System Design — коротко

**Зачем.** Госзаказ и B2B-закупки в РФ — 30–40 трлн ₽/год. Поставщик-МСП тратит 30–60 мин/тендер на ручной разбор; существующие сервисы ищут «по словам», не делают ценовых бенчмарков и risk-анализа. ДИС Минфина открыт с 2025 → прямой доступ к историческим данным, LLM дешёвые → per-tender оценка экономически осмысленна.

**Что делает.** Поиск на 7 площадках, LLM-фильтрация релевантности, извлечение требований из ТЗ, risk-карточка заказчика/поставщика (жалобы/РНП/отказы), ценовой бенчмарк по ОКПД2 × регион, ранжирование, сводная карточка в чате/боте.

**Как устроена.** Dialog Agent (чат) → Orchestrator (параллельный поиск) → Source Agents (7 парсеров) + Historical DB (витрина ЕИС). Поверх них — Relevance Agent (LLM), Risk Agent и Bench Agent (SQL по витрине), Extraction Agent (LLM по приложениям). Всё на Python, LLM через OpenRouter (Gemma free + Grok fallback), хранение в SQLite, веб на FastAPI+React.

**Гарантии и риски.** Фактические данные (цены, ИНН, номера) идут мимо LLM детерминированно — галлюцинаций там нет. LLM возвращает строгий JSON, при `no_json` — fallback на вторую модель. Rate-limit ЕИС соблюдается (90/60). Feedback-кнопки «👍/👎» в боте для auto-tuning порогов. Human-in-the-loop: агент не подаёт заявки сам, человек всегда в финале.

**Метрики качества.** Recall@20 (полнота поиска) ≥ 0.8, Precision@10 (точность отбора) ≥ 0.7, field coverage витрины ≥ 99% на ключевых полях, MAPE ценового бенчмарка < 20%.

📖 **Подробнее — [docs/AGENT_SYSTEM_DESIGN.md](docs/AGENT_SYSTEM_DESIGN.md)** (полный design doc: архитектура, агенты, источники, guardrails, evaluation, roadmap).

---

## Структура проекта

```
tender/
│
├─ core/                              ЯДРО — работа с данными и логика
│   ├─ sources/                       источники: откуда берём
│   │   ├─ eis/                       пакет ЕИС ДИС
│   │   │   ├─ dis.py                     SOAP-клиент (zeep, 90 req/min)
│   │   │   ├─ rate.py                    token-bucket
│   │   │   ├─ pipeline.py                оркестратор скачивания
│   │   │   ├─ parsers.py                 9 XML-парсеров
│   │   │   └─ analytics_loader.py        загрузка в витрину
│   │   ├─ zakupki_playwright.py      44-ФЗ через Playwright
│   │   ├─ bicotender.py / b2b_center.py / fabrikant.py
│   │   ├─ roseltorg.py / rts_tender.py / sber_ast.py
│   │   └─ common.py
│   ├─ storage/                       где храним (SQLite-БД)
│   │   ├─ db.py                      tenders.db — активная воронка бота
│   │   ├─ eis_history.py             eis_history.db — трекинг скачивания
│   │   └─ eis_analytics.py           eis_analytics.db — витрина аналитики
│   ├─ llm/                           ИИ-провайдеры
│   │   ├─ __init__.py                фасад: выбор по env LLM_PROVIDER
│   │   ├─ openrouter.py              OpenRouter (default)
│   │   └─ claude_cli.py              Claude Code CLI (только не-РФ IP)
│   ├─ agents/                        поисковые агенты (логика над sources)
│   │   ├─ bicotender_agent.py
│   │   └─ multi_search.py
│   └─ utils/vpn.py                   переключатель VPN (для локальной машины)
│
├─ apps/                              ИНТЕРФЕЙСЫ — как пользователь взаимодействует
│   ├─ bot/telegram_bot.py            Telegram-бот
│   └─ web/                           FastAPI + WebSocket-чат
│       ├─ app.py
│       ├─ chat_agent.py
│       └─ static/                    собранный React (prod)
│
├─ scripts/                           CLI — точки входа
│   ├─ run_web.py                     запуск FastAPI-веб
│   ├─ run_bicotender.py              парсинг Bicotender.ru
│   └─ load_history.py                fetch / parse / stats ЕИС
│
├─ frontend/                          исходник React/TypeScript/Vite
│   ├─ src/                           исходники (редактируй тут)
│   ├─ build.sh                       сборка + deploy в apps/web/static/
│   └─ package.json
│
├─ deploy/                            VPS-развёртывание
│   ├─ VPS_WEB.md                         гайд для aixmode.online
│   ├─ VPS_DEPLOY.md                      гайд для ЕИС-загрузчика
│   ├─ tenderai-web.service               systemd-unit веб
│   ├─ eis-fetch.service                  systemd-unit ЕИС
│   ├─ nginx-aixmode.conf                 nginx-конфиг HTTPS
│   └─ requirements-eis.txt               минимум для ЕИС
│
├─ docs/                              документация
│   ├─ EIS_consumer_guide.pdf             официальная инструкция Минфина
│   ├─ eis_analytics_playbook.md          сценарии аналитики
│   └─ eis_nsi_doctypes_catalog.txt       каталог 126+93 типов документов
│
├─ data/                              runtime-state парсеров (в .gitignore)
│   ├─ bicotender_state/ / bicotender_docs/
│   └─ fabrikant_state/ / rts_state/
│
├─ archives/                          сырые ZIP от ЕИС (в .gitignore, ~14 GB)
├─ diag/                              живые диагностические скрипты
│   ├─ status.py                          сводка по eis_history.db
│   └─ eis_throughput_probe.db            результаты нагрузочного теста
│
├─ README.md / requirements.txt / .env / .env.example / .gitignore / config.yaml
└─ tenders.db / eis_history.db / eis_analytics.db
```

## Быстрый старт

### 1. Установка Python-окружения

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows
source .venv/bin/activate           # Linux/macOS

pip install -r requirements.txt
playwright install chromium         # только если планируется парсинг площадок
```

### 2. Конфигурация `.env`

Скопируй `.env.example` → `.env`, заполни ключи:

```ini
# Telegram-бот (необязательно, если не нужен бот)
TG_TOKEN=...
TG_ALLOWED_CHAT_ID=...

# Bicotender (опционально — для платных фильтров и скачивания доков)
BICOTENDER_LOGIN=
BICOTENDER_PASSWORD=

# ЕИС ДИС — для выгрузки тендерной истории
# Получить: https://zakupki.gov.ru/pmd/auth/welcome → Госуслуги →
#           «потребитель машиночитаемых данных» (физлицо)
EIS_DIS_TOKEN=

# LLM (OpenRouter работает из РФ без VPN, Claude CLI — только не-РФ IP)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free
OPENROUTER_FALLBACK_MODEL=x-ai/grok-4.1-fast
```

---

## 3 основных сценария использования

### A. Telegram-бот (поиск тендеров в реальном времени)

```bash
python -m apps.bot.telegram_bot
```

В Telegram: `/start` → «🔎 Искать тендеры» → вводишь ключевое слово или используешь `/search <фраза>`.

Бот ищет на zakupki.gov.ru, оценивает каждый найденный тендер через LLM-агент по профилю пользователя (`config.yaml`) и присылает отфильтрованный список.

### B. Веб-интерфейс (чат с ИИ-агентом)

```bash
python scripts/run_web.py                    # http://localhost:8000
python scripts/run_web.py --host 0.0.0.0     # доступ по сети
```

Открой `http://localhost:8000`, пиши в чат. Агент делает то же, что бот, но с интерфейсом чата, историей сессий и карточками тендеров.

**Продакшен-развёртывание** — `deploy/VPS_WEB.md`. Публикуется на `aixmode.online` через nginx + Let's Encrypt + systemd.

### C. ЕИС-выгрузка и аналитика

```bash
# 1. Скачать архивы за нужный период (preset top10-apr2026 = 10 ключевых регионов × 46 типов × 20 дней)
python scripts/load_history.py fetch --preset top10-apr2026
#    ~4-6 часов на ПК (VPN выключается автоматически), идемпотентно.

# 2. Распарсить скачанные ZIP-XML → eis_analytics.db
python scripts/load_history.py parse
#    ~18 минут на 13 GB / 283k XML-файлов.

# 3. Смотреть сводку
python scripts/load_history.py stats
python diag/status.py              # подробная сводка со скоростями
```

После `parse` в `eis_analytics.db` лежит структурированная витрина (notices / protocols / contracts / contract_items / complaints / refusals / unfair_suppliers / tender_plans) — 1.8 млн строк. С ней можно работать SQL-запросами или подцеплять к веб-интерфейсу.

**Сценарии аналитики поверх витрины** — `docs/eis_analytics_playbook.md`.

---

## Работа с фронтендом (UI)

Веб-интерфейс — React + TypeScript + Vite в `frontend/`. Собранный продакшен-бандл лежит в `apps/web/static/` (именно его отдаёт FastAPI).

### Поменять UI (локально)

```bash
cd frontend
npm install                         # первый раз
# правишь frontend/src/app/Root.tsx или components/*.tsx
bash frontend/build.sh              # собирает + копирует в apps/web/static/
# перезапусти web-сервер (Ctrl+C в run_web.py и заново)
```

Скрипт `frontend/build.sh` делает: `npm run build` → `cp -r dist/. ../apps/web/static/`.

### Деплой UI-изменений на продакшен

Залей `apps/web/static/*` (и/или `frontend/src/*`, если на VPS тоже билд) через FileZilla на VPS, затем:

```bash
# на VPS
systemctl restart tenderai-web
```

---

## Сопровождение

### Обновить ЕИС-данные за новый период

```bash
# Поменять пресет в core/storage/eis_history.py::preset_jobs или добавить новый:
# пример: top10-may2026 = те же регионы × 46 типов × дни мая

python scripts/load_history.py fetch --preset <имя_пресета>
python scripts/load_history.py parse
```

Pipeline **идемпотентный** — повторный запуск пропустит уже скачанное / распарсенное. Безопасно прерывать `Ctrl+C`.

### Сменить LLM-провайдер

В `.env` поменяй `LLM_PROVIDER`:
- `openrouter` (default) — работает из РФ, fallback между двумя моделями;
- `claude` — использует локальный Claude Code CLI (требует не-РФ IP).

### Сменить LLM-модель (без смены провайдера)

В `.env`:
```ini
OPENROUTER_MODEL=anthropic/claude-haiku-4.5
OPENROUTER_FALLBACK_MODEL=google/gemini-2.5-flash
```
Список моделей — https://openrouter.ai/models.

### Обновить токен ЕИС (раз в 90 дней)

Старый перестаёт работать с ошибкой `errorInfo code=24` — перевыпустить в ЛК `zakupki.gov.ru/pmd/auth/welcome`, вписать новый в `.env`, перезапустить.

### Перепарсить данные (например, после правки парсера)

```bash
# Полный перегон (~18 мин):
rm eis_analytics.db
python scripts/load_history.py parse

# Или только конкретные типы (быстрее):
python scripts/load_history.py parse --types contract epProtocolEF2020Final
```

Таблицы парсятся через `INSERT OR REPLACE` по первичному ключу, так что повторные прогоны безопасны.

### Добавить новую коммерческую площадку

1. Создать `core/sources/<платформа>.py` по шаблону `core/sources/bicotender.py` (Playwright + persistent context в `data/<платформа>_state/`).
2. Создать `core/agents/<платформа>_agent.py` — агент поиска с параметрами.
3. Подключить в `apps/bot/telegram_bot.py` и/или `apps/web/chat_agent.py`.

---

## Типовые проблемы и решения

| Проблема | Решение |
|---|---|
| `EIS_DIS_TOKEN не задан` | Создать `.env`, положить туда токен из ЛК потребителя |
| `errorInfo code=13` во время fetch | Нормально — rate limit 90/60, клиент сам подождёт 60 сек |
| `errorInfo code=24` | Токен устарел — перевыпустить в ЛК |
| `Failed to connect to int.zakupki.gov.ru` | IP не российский / датацентровый банлист. Запускать с домашнего IP или арендовать VPS у другого хостера. |
| Claude API не работает на VPS | VPS в РФ → Anthropic блокирует. Использовать OpenRouter (работает) |
| WebSocket ломается на HTTPS | В фронтенде должно быть `wss://` при HTTPS. Если правили `frontend/src/app/Root.tsx` — пересобрать через `bash frontend/build.sh` |
| nginx 404 на `aixmode.online` | В `deploy/nginx-aixmode.conf` проверить `proxy_pass` — порт должен совпадать с `tenderai-web.service` |
| `ModuleNotFoundError: No module named 'core'` | Запускать из корня проекта. Скрипты в `scripts/` сами вставляют `ROOT` в `sys.path`, но `python -m apps.bot.telegram_bot` — только из корня. |

---

## Требования

- **Python 3.12+**
- **Node.js 18+** (только для пересборки фронтенда)
- **Для выгрузки ЕИС** — российский IP (домашний или VPS в РФ). Датацентровые IP могут блокироваться сервисом zakupki.
- **Для LLM** — доступ в интернет (OpenRouter) или локальный `claude` CLI.

---

## Ссылки на документацию

- [docs/eis_analytics_playbook.md](docs/eis_analytics_playbook.md) — сценарии аналитики по витрине
- [docs/eis_nsi_doctypes_catalog.txt](docs/eis_nsi_doctypes_catalog.txt) — 126 типов документов 44-ФЗ + 93 типа 223-ФЗ
- [docs/EIS_consumer_guide.pdf](docs/EIS_consumer_guide.pdf) — официальная инструкция Минфина
- [deploy/VPS_WEB.md](deploy/VPS_WEB.md) — развёртывание веб-интерфейса на `aixmode.online`
- [deploy/VPS_DEPLOY.md](deploy/VPS_DEPLOY.md) — развёртывание ЕИС-загрузчика на РФ-VPS
