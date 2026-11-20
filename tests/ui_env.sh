#!/usr/bin/env bash
# Starts mock Telegram + the full app (proxy, Vite, API) on a throw-away database
cd "$(dirname "$0")/.."
T=${UI_TMP:-/tmp/ui}
mkdir -p $T
python3 tests/mock_telegram.py 8081 > $T/mock.log 2>&1 &
sleep 1
: > $T/mails.jsonl
python3 tests/smtp_sink.py 2527 $T/mails.jsonl > $T/smtp.log 2>&1 &
curl -s -X POST localhost:8081/_mock/add_bot -H 'content-type: application/json' -d '{"token":"9000000001:CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC","username":"matrix_connect_bot"}' >/dev/null
curl -s -X POST localhost:8081/_mock/add_bot -H 'content-type: application/json' -d '{"token":"8822824343:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","username":"my_test_bot"}' >/dev/null
export TELEGRAM_API_ROOT=http://127.0.0.1:8081 CONNECT_BOT_TOKEN=9000000001:CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC APP_DB_PATH=$T/app.db DATABASE_URL=sqlite:///$T/engine.db SECRET_KEY=ui-test BM_TEST_NO_RATE_LIMIT=1 SMTP_HOST=127.0.0.1 SMTP_PORT=2527 SMTP_STARTTLS=0 SMTP_USER=u@x.io SMTP_PASSWORD=pw ADMIN_EMAILS=admin@x.io ADMIN_CONTACT_URL=https://t.me/matrix_admin
exec npx tsx server.ts > $T/app.log 2>&1
