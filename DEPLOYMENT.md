# Deployment Information

## Public URL
https://agent-production-6b4e60d3.up.railway.app

## Platform
Railway — project `VinUniLab14`, environment `production`, region US East, 1 replica.

| Service | Vai trò |
|---------|---------|
| `agent` | AI agent Part 6, build từ `06-lab-complete/Dockerfile` (multi-stage, `python:3.11-slim`, 238 MB), cấu hình bằng `06-lab-complete/railway.toml` (builder `DOCKERFILE`, healthcheck `/health`, restart `ON_FAILURE`) |
| `Redis` | Railway Redis database (volume `redis-volume`), lưu state rate limit + cost guard |

Deploy bằng Railway CLI: `railway up --service agent`.

> Ghi chú: builder của Railway báo lỗi `header key "exclude-patterns" contains value with non-printable ASCII characters` khi đọc các file ignore trong repo (comment tiếng Việt / CRLF ở `.gitignore`, `.dockerignore` gốc repo). Vì vậy tôi deploy từ một bản copy gọn của `06-lab-complete` gồm đúng các file Dockerfile cần (`app/`, `utils/`, `Dockerfile`, `requirements.txt`, `railway.toml`). Image build ra giống hệt bản trong repo.

## Test Commands

```bash
export BASE=https://agent-production-6b4e60d3.up.railway.app
```

### Health Check
```bash
curl $BASE/health
# Expected: {"status":"ok"}
```

### Readiness (Redis)
```bash
curl $BASE/ready
# Expected: {"status":"ready","redis":"up"}
```

### API Test (with authentication)
```bash
# Không có API key → 401
curl -X POST $BASE/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# Có API key → 200
curl -X POST $BASE/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

### Kết quả tự kiểm (2026-11-26, chỉ in mã HTTP để không lộ key)
```text
$ curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
200
$ curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
200
$ curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'
401
$ curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'
200
```

| Kiểm tra | Mong đợi | Kết quả |
|----------|----------|---------|
| `GET /health` | 200 | ✅ 200 |
| `GET /ready` (Redis trên Railway) | 200 | ✅ 200 |
| `POST /ask` không key | 401 | ✅ 401 |
| `POST /ask` có key | 200 | ✅ 200 |

`python 06-lab-complete/check_production_ready.py --public-url "$BASE"` → **PASS 12/12 · 44/44 checks**, gồm `Public URL: GET https://agent-production-6b4e60d3.up.railway.app/health → 200`.

## Environment Variables Set
Đặt trên dashboard Railway (service `agent` → Variables), không ghi trong code hay repo:

- `AGENT_API_KEY` — secret, chỉ có trên Railway
- `REDIS_URL` — variable reference `${{Redis.REDIS_URL}}` tới service Redis
- `ENVIRONMENT=production`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `PORT` — Railway tự cấp; container chạy `uvicorn ... --port ${PORT:-8000}`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png) — project `VinUniLab14`: service `agent` và `Redis` đều Online
- [Service running](screenshots/running.png) — service `agent`: deployment ACTIVE, "Deployment successful", domain public
- [Test results](screenshots/test.png) — 4 lệnh tự kiểm 200 / 200 / 401 / 200 + `check_production_ready.py --public-url`