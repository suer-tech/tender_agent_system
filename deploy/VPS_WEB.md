# Развёртывание веб-интерфейса TenderAI на `aixmode.online`

Цель — запустить FastAPI-приложение (`apps/web/app.py` + WebSocket-чат с ИИ-агентом) на VPS и опубликовать по HTTPS на домене `aixmode.online`.

**Стек:** Ubuntu 22.04/24.04 + Python 3.12+ + uvicorn (systemd-unit) + nginx (reverse proxy с SSL) + Let's Encrypt (certbot). ИИ — через OpenRouter (работает из РФ), Claude CLI — как опция.

**Все команды выполняются от `root`.** Код живёт в `/root/tender/`. Это упрощает начальный старт, но в продакшене лучше потом завести отдельного пользователя; сейчас оставляем как есть.

**Порт:** `8765` (чтобы не конфликтовать с чужим приложением на 8000, которое уже стоит на VPS).

---

## 1. Требования

- VPS с **публичным IPv4**. Локация — любая (домен не имеет геоограничений, OpenRouter работает отовсюду). Если на этом же VPS крутится ЕИС-загрузчик — VPS **обязательно должен быть в РФ**.
- Ubuntu 22.04 / 24.04 LTS.
- Ресурсы: минимум 1 vCPU / 1 GB RAM; для комфорта — 2 GB.
- Доступ к DNS домена `aixmode.online`.

## 2. DNS

В панели регистратора домена настроить:

```
Тип   Имя                 Значение            TTL
A     aixmode.online      <IP_VPS>            600
A     www.aixmode.online  <IP_VPS>            600
```

Проверить:
```bash
dig +short aixmode.online
dig +short www.aixmode.online
```
Должны вернуть IP VPS. **До этого момента получить SSL-сертификат не получится.**

## 3. Системные пакеты

```bash
apt update && apt install -y git python3-venv python3-pip nginx certbot \
    python3-certbot-nginx rsync screen htop ufw

# firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

## 4. Код на VPS

### Через FileZilla (SFTP)
- Protocol: **SFTP**, Host: IP_VPS, Port: 22, User: `root`
- В правой панели — `/root/tender/` (создать, если нет).
- Залить содержимое локального `C:\Users\user2\Documents\Cursor\tender\` **кроме** `.venv/`, `__pycache__/`, `archives/`, `*.db`, `.env`.

### Или через rsync (из WSL/git-bash на локальной машине)
```bash
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude 'archives' \
      --exclude '*.db' --exclude '.env' \
      /c/Users/user2/Documents/Cursor/tender/ \
      root@VPS_IP:/root/tender/
```

## 5. Python-окружение

```bash
cd /root/tender
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. `.env`

Создать `/root/tender/.env`:

```bash
cd /root/tender
nano .env
```

Минимально — для web+LLM:

```
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free
OPENROUTER_FALLBACK_MODEL=x-ai/grok-4.1-fast
OPENROUTER_REFERER=https://aixmode.online
OPENROUTER_APP_NAME=TenderAI
```

Если на этом VPS будут ещё Telegram-бот / ЕИС-загрузчик / парсеры площадок — добавить свои ключи:

```
TG_TOKEN=
TG_ALLOWED_CHAT_ID=
BICOTENDER_LOGIN=
BICOTENDER_PASSWORD=
EIS_DIS_TOKEN=
```

Закрыть файл на чтение только для root:
```bash
chmod 600 /root/tender/.env
```

## 7. Проверка запуска вручную

```bash
cd /root/tender && source .venv/bin/activate
python scripts/run_web.py --host 127.0.0.1 --port 8765
```

В **другой** SSH-сессии:
```bash
curl -s http://127.0.0.1:8765/ | head -5
```
Должен вернуться HTML, начинающийся с `<!DOCTYPE html>` и содержащий `TenderAI`. Если вернулось «Not Found / please check your spelling» — это чужое Flask-приложение (проверь, не перепутал ли порт).

Если ошибка запуска — читай stderr в первой сессии. Частые причины:
- не установлен какой-то пакет (`pip list | grep fastapi` должен показывать `fastapi==0.115.6`);
- `OPENROUTER_API_KEY` пустой в `.env` — не критично для самого запуска, но чат отвечать не будет.

Остановить — `Ctrl+C`.

## 8. systemd-юнит (автозапуск)

```bash
cp /root/tender/deploy/tenderai-web.service /etc/systemd/system/
touch /var/log/tenderai-web.log

systemctl daemon-reload
systemctl enable tenderai-web
systemctl start tenderai-web
systemctl status tenderai-web      # должен быть active (running)
```

Логи:
```bash
tail -f /var/log/tenderai-web.log
# или
journalctl -u tenderai-web -f
```

Проверка, что порт слушается:
```bash
ss -tlnp | grep ':8765'
curl -s http://127.0.0.1:8765/ | head -3
```

## 9. Nginx + HTTPS

### 9.1 Временный HTTP-конфиг (чтобы получить сертификат)

```bash
mkdir -p /var/www/certbot

cat > /etc/nginx/sites-available/aixmode.online <<'EOF'
server {
    listen 80;
    server_name aixmode.online www.aixmode.online;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'TenderAI bootstrap — waiting for SSL'; add_header Content-Type text/plain; }
}
EOF

ln -sf /etc/nginx/sites-available/aixmode.online /etc/nginx/sites-enabled/aixmode.online
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

Проверить, что по HTTP домен открывается:
```bash
curl -I http://aixmode.online
```
Должен быть `HTTP/1.1 200 OK` с нашим bootstrap-текстом.

### 9.2 Получить Let's Encrypt сертификат
```bash
certbot certonly --webroot -w /var/www/certbot \
    -d aixmode.online -d www.aixmode.online \
    --email your@email.here --agree-tos --no-eff-email
```

После успеха файлы будут в `/etc/letsencrypt/live/aixmode.online/`.

### 9.3 Подставить боевой конфиг

```bash
cp /root/tender/deploy/nginx-aixmode.conf /etc/nginx/sites-available/aixmode.online
nginx -t && systemctl reload nginx
```

### 9.4 Автопродление

Certbot ставит таймер `certbot.timer` при установке. Проверить:
```bash
systemctl status certbot.timer
```

Чтобы после обновления сертификата nginx автоматически перезагружался:
```bash
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/bin/sh
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

## 10. Проверка результата

- Открыть в браузере: **https://aixmode.online** — должен показаться интерфейс TenderAI.
- Редирект с HTTP: `curl -I http://aixmode.online` → `301 Moved Permanently` на `https://`.
- Зайти в чат, написать что-нибудь. Если LLM не отвечает — смотрим логи:
  ```bash
  tail -f /var/log/tenderai-web.log
  tail -f /var/log/nginx/aixmode.error.log
  ```
  Частые причины:
  - `OPENROUTER_API_KEY не задан` — поправить `.env`, `systemctl restart tenderai-web`.
  - `HTTP 404: model not found` — не та строка `OPENROUTER_MODEL` (на OpenRouter могли переименовать модель). Поправить и перезапустить.
  - WebSocket не коннектится — убедиться, что в nginx-конфиге есть `Upgrade` headers для `/ws/` (в нашем — есть).

## 11. Обновление кода

Перезалить изменившиеся файлы через FileZilla (SFTP, root, `/root/tender/`), потом:
```bash
cd /root/tender && source .venv/bin/activate
pip install -r requirements.txt       # если менялись зависимости
systemctl restart tenderai-web
```

## 12. Масштабирование

- **Больше нагрузки** → увеличить `--workers` в systemd-юните (правило: `2 × CPU + 1`). Внимание: `apps/web/app.py:sessions = {}` — in-memory, при нескольких воркерах сессии не разделяются между ними. Для продакшена выносить в Redis/Postgres (отдельная задача, не MVP).
- **Долгие LLM-ответы** → в nginx установлен `proxy_read_timeout 3600s` для `/ws/` и `300s` для остальных локаций. Меняется в `nginx-aixmode.conf`.
- **Rate limit по IP** (защита от спама) — добавить в nginx:
  ```nginx
  limit_req_zone $binary_remote_addr zone=chat:10m rate=10r/m;
  # в location / — limit_req zone=chat burst=5;
  ```

## 13. Web + ЕИС-загрузчик на одном VPS?

Да, можно. Оба кладём в `/root/tender/`, используют один `.env` и один venv. Если VPS в РФ — всё совместимо:
- web+LLM через OpenRouter работают из РФ.
- ЕИС-загрузчик (`load_history.py fetch`) тоже требует РФ-IP.

Команда запуска ЕИС-выгрузки в этом случае — через `screen` (описано в `VPS_DEPLOY.md`).

Если VPS **не в РФ** — ЕИС с него выгружать нельзя (бан токена), нужен отдельный РФ-VPS для crawler'а, обмен через `rsync eis_history.db`.

## 14. Файлы в этом деплое

- `deploy/tenderai-web.service` — systemd-юнит (User=root, порт 8765)
- `deploy/nginx-aixmode.conf` — nginx-конфиг (HTTP→HTTPS + WS proxy)
- `deploy/VPS_WEB.md` — эта инструкция
- `deploy/VPS_DEPLOY.md` — инструкция для ЕИС-загрузчика (тоже от root)
