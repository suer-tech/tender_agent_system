# Развёртывание выгрузки ЕИС на VPS

Этот гайд запускает `load_history.py fetch --preset top10-apr2026` на VPS в РФ — скачивание данных за апрель 2026 по 10 ключевым регионам × 46 типов (PRIZ + RGK + RNP + UR + RJ + RPGZ). Всего **9 200 SOAP-запросов + ~3–10 тыс. архивов**, оценка **4–6 часов фоном**.

**Все команды выполняются от `root`.** Код живёт в `/root/tender/`.

---

## 1. Требования к VPS

- **Локация:** Россия (Timeweb / Beget / рег.ру / Selectel). Иностранный IP = бан токена.
- **ОС:** Ubuntu 22.04 или 24.04 LTS.
- **Ресурсы:** 1 vCPU, 1 GB RAM достаточно. **Диск ≥ 10 GB** (архивы + БД + логи).
- **Python 3.12+** (Ubuntu 24.04 — из коробки; 22.04 — через deadsnakes).
- Порты наружу не нужны — только клиент.

## 2. Системные пакеты

```bash
apt update && apt install -y git python3-venv python3-pip rsync screen curl htop
```

## 3. Код на VPS

### Через FileZilla (SFTP)
- Protocol: **SFTP**, Host: IP_VPS, Port: 22, User: `root`
- Папка на VPS: `/root/tender/` (создать, если нет)
- Залить содержимое проекта **кроме** `.venv/`, `__pycache__/`, `archives/`, `*.db`, `.env`

### Или через rsync (из WSL/git-bash на локальной машине)
```bash
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'archives' \
      --exclude '*.db' --exclude '.env' \
      /c/Users/user2/Documents/Cursor/tender/ \
      root@VPS_IP:/root/tender/
```

## 4. Python-окружение

```bash
cd /root/tender
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r deploy/requirements-eis.txt
```

Проверить импорты:
```bash
python -c "from core.sources.eis.dis import EisDisClient; from core.sources.eis import pipeline; print('ok')"
```

## 5. `.env` и токен

```bash
cd /root/tender
nano .env
```
Минимум для ЕИС-загрузчика:
```
EIS_DIS_TOKEN=<твой_активный_токен>
```
```bash
chmod 600 /root/tender/.env
```

Проверить внешний IP — **обязательно RU**:
```bash
curl -s https://ipinfo.io/json | grep country
# ожидаем "country": "RU"
```

## 6. Smoke-тест (1 минута)

Маленький прогон перед тяжёлой выгрузкой:
```bash
cd /root/tender && source .venv/bin/activate
python scripts/load_history.py fetch --preset smoke --skip-vpn
```
Должен отработать за ~1 минуту, скачать 4 архива в `archives/`. Если `code=13` промелькнёт — rate limiter сам подождёт 60 сек и продолжит, это норма. Если `EIS_DIS_TOKEN не задан` — проверь `.env`.

## 7. Запуск полной выгрузки

### Вариант 1 — через screen

```bash
cd /root/tender && source .venv/bin/activate
screen -S eis
python scripts/load_history.py fetch \
    --preset top10-apr2026 \
    --workers-phase1 20 --workers-phase2 5 \
    --skip-vpn \
    2>&1 | tee -a fetch.log
```

Управление screen:
- Отсоединиться (процесс продолжит работать): `Ctrl+A`, затем `D`
- Вернуться к сессии: `screen -r eis`
- Посмотреть живые сессии: `screen -ls`
- Закрыть принудительно: `screen -S eis -X quit`

### Вариант 2 — через systemd

```bash
cp /root/tender/deploy/eis-fetch.service /etc/systemd/system/
touch /var/log/eis-fetch.log
systemctl daemon-reload
systemctl start eis-fetch
systemctl status eis-fetch
```

Логи: `tail -f /var/log/eis-fetch.log`.

## 8. Мониторинг прогресса

Pipeline печатает прогресс каждые 50 партий (phase1) и каждые 100 архивов (phase2). Параллельно можно смотреть БД:

```bash
cd /root/tender
sqlite3 eis_history.db <<'SQL'
SELECT status, COUNT(*) FROM download_batches GROUP BY status;
SELECT COUNT(*) as archives_total,
       SUM(CASE WHEN local_path IS NOT NULL THEN 1 ELSE 0 END) as downloaded
FROM archives;
SELECT ROUND(SUM(size_bytes)/1024.0/1024.0, 1) as mb_on_disk FROM archives;
SQL
```

Disk/CPU: `df -h`, `htop`.

## 9. Что делать при сбоях

- **Pipeline остановился / VPS перезагрузился** — просто запусти ту же команду ещё раз. Pipeline резюмируется по статусам в `eis_history.db`: phase1 пропускает `ok/empty`, phase2 пропускает уже скачанные по `archives.local_path`.
- **Токен перестал работать** (`errorInfo code=24` или `#34`) — зайди в ЛК на `zakupki.gov.ru/pmd/auth/welcome`, перевыпусти, обнови `.env`, перезапусти.
- **RU-IP отвалился** (VPS вдруг через не-РФ туннель) — `curl ipinfo.io`. ЕИС забанит токен за обращения с иностранного IP.

## 10. Забрать данные к себе

После окончания выгрузки **на локальную машину** (из bash/WSL/PowerShell с rsync):
```bash
rsync -avzP root@VPS_IP:/root/tender/eis_history.db \
      /c/Users/user2/Documents/Cursor/tender/eis_history.db

rsync -avzP root@VPS_IP:/root/tender/archives/ \
      /c/Users/user2/Documents/Cursor/tender/archives/
```

Размер архивов ориентировочно 1–3 GB. Если канал плохой — пересылай ТОЛЬКО `eis_history.db` (метаданные + ссылки) и **не** таскай raw-архивы — парсить будем тем же кодом из тех же архивов на VPS, а структурированный результат забирать отдельным файлом.

## 11. Остановить / отключить

- screen: `screen -r eis` → Ctrl+C → `exit`.
- systemd: `systemctl stop eis-fetch && systemctl disable eis-fetch`.

## 12. После выгрузки

Следующий этап — парсинг архивов в структурированные таблицы (`notices`, `contracts`, `complaints`, …) для бенчмарков/риск-скора. Pipeline для этого пока не реализован (каждый из 46 типов — свой XSD). Минимальный набор для первого спринта — 4 типа: `epNotificationEF2020`, `epNotificationEOK2020`, `epNotificationEZK2020`, `contract` (из RGK) — покроет ~80% ценности для ценовых бенчмарков.

---

## Подводные камни

- **Лимит 90 req/60 сек** — жёсткий, общий на токен. Даже 20 воркеров phase1 не разгонят выше 1.5 rps; это нормально.
- **`--skip-vpn`** — обязательно на VPS (VPN там нет, без флага скрипт попытается дёрнуть `wiresock-connect-cli`, которого нет).
- **Запрет на параллельные запуски** — не запускай два `fetch` одновременно с одним токеном: оба упрутся в лимит и будут ретраиться друг на друга.
- **Токен не коммитить** — `.env` в `.gitignore`, `chmod 600`.
