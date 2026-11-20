# Deploy BOT MATRIX on Railway

## Security rules (GitGuardian / leaks)

- **Never commit** `.env`, bot tokens, SMTP passwords, or `SECRET_KEY`.
- Put **all secrets only** in Railway → Project → Variables.
- Bot tokens users paste in the UI are **encrypted at rest** with `SECRET_KEY`.
- API logs and error pages run token redaction (`[REDACTED_BOT_TOKEN]`).
- `.gitignore` and `.dockerignore` exclude `.env`, `storage/`, databases.

If GitGuardian ever flags a token: **revoke it in BotFather immediately**, rotate `SECRET_KEY` only if you understand encrypted data will need re-entry of bot tokens.

---

## 1. Create the project

1. Push this folder to a **private** GitHub/GitLab repo (no secrets in history).
2. Railway → **New Project** → **Deploy from GitHub** → select the repo.
3. Root directory: the folder that contains `Dockerfile` / `package.json` (this `proj` folder).

Build uses `Dockerfile` (`railway.toml`). Health check: `GET /health`.

---

## 2. Variables (Railway → Variables)

| Variable | Required | Example / notes |
|----------|----------|-----------------|
| `SECRET_KEY` | **Yes** | `openssl rand -hex 32` — keep forever for the same volume |
| `BASE_URL` | Recommended | `https://your-service.up.railway.app` |
| `ADMIN_EMAILS` | Recommended | your admin email(s), comma-separated |
| `CONNECT_BOT_TOKEN` | Optional | platform connect bot only |
| `DATABASE_URL` | Optional | Railway Postgres plugin URL; else SQLite on volume |
| `SMTP_*` | Optional | only if email OTP |
| `REQUIRE_EMAIL_OTP` | Optional | `0` or `1` |
| `RATE_LIMITS` | Recommended prod | `1` |
| `TURNSTILE_*` | Optional | Cloudflare |

`PORT` and `RAILWAY_*` are set by Railway automatically. Do **not** put real tokens in the repo or in build args.

---

## 3. Persistent storage

SQLite + uploads live under `/app/storage`.

Railway → service → **Volumes** → mount a volume at:

```text
/app/storage
```

Without a volume, data is wiped on every redeploy.

---

## 4. Optional Postgres

1. Railway → **Add** → **PostgreSQL**.
2. Variable `DATABASE_URL` is linked automatically.
3. Redeploy. No other code change needed.

---

## 5. After deploy

1. Open the public HTTPS URL.
2. Register the admin account (email in `ADMIN_EMAILS`).
3. Add bots **only in the UI** — tokens stay encrypted in the DB, not in git.
4. Set `BASE_URL` to the final custom domain if you add one.

---

## Local vs Railway

| | Local | Railway |
|--|--------|---------|
| Start | `./start.bat` or `npm run dev` | Docker `CMD` / `node dist/server.cjs` |
| Secrets | `.env` (gitignored) | Variables UI |
| Port | 3000 | `$PORT` |
| API | Node proxies `/api` → Python `127.0.0.1:5001` | same |

---

## Troubleshooting

- **Healthcheck fail**: wait for first boot (Python deps); check Deploy Logs.
- **White page**: ensure `vite build` succeeded; open `/health`.
- **Bots lost after redeploy**: attach `/app/storage` volume; keep same `SECRET_KEY`.
- **Cannot decrypt tokens**: `SECRET_KEY` changed — set the original key back or re-add bots.
