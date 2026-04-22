#!/bin/bash
# Сборка React-фронтенда и деплой в web/static/.
# Использование: bash frontend/build.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "[frontend] npm run build..."
npm run build

echo "[frontend] deploy to ../apps/web/static/..."
rm -rf ../apps/web/static/assets
cp -r dist/. ../apps/web/static/

echo "[frontend] done. Если сервер живой — перезапусти:"
echo "           systemctl restart tenderai-web   (VPS)"
echo "           или Ctrl+C и заново python run_web.py (локально)"
