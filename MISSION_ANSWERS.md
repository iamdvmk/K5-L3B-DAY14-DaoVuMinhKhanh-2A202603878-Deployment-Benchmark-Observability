# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found
1.  Hardcode secret: OPENAI_API_KEY = "sk-hardcoded-...", DATABASE_URL có password123.
2.  Log lộ secret: print(f"[DEBUG] Using key: {OPENAI_API_KEY}").
3.  Dùng print() thay vì logging có cấu trúc.
4.  DEBUG = True, reload=True bật cứng.
5.  host="localhost", port=8000 cố định: container/cloud không truy cập được, không đọc PORT.
6.  Không có /health → platform không biết khi nào restart.
7.  Không xử lý SIGTERM → deploy là cắt ngang request.

### Exercise 1.2: Chạy bản develop
```
curl -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode | Biến môi trường (config.py) | Cùng một code chạy dev/staging/prod; secret không lọt lên Git |
| Health check | Không có | /health, /ready | Platform biết khi nào restart / khi nào route traffic |
| Logging | print() | JSON | Lọc, tìm kiếm được; không in secret |
| Shutdown | Đột ngột | Graceful (SIGTERM) | Không mất request khi deploy/scale |
| Host/Port | localhost:8000 | 0.0.0.0:$PORT | Cloud cấp PORT, container cần bind mọi interface |

```
curl -i -X POST http://localhost:8000/ask -H 'Content-Type: application/json' -d '{"question":"Hello"}'
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:10:59 GMT
server: uvicorn
content-length: 144
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)
1. **Base image:** `python:3.11` — bản Python đầy đủ (Debian + compiler, tool build), nặng nhưng tiện cho dev.
2. **Working directory:** `/app` (`WORKDIR /app`), các lệnh `COPY`, `RUN`, `CMD` sau đó đều chạy trong thư mục này.
3. **Vì sao `COPY requirements.txt` trước `COPY` code:** Docker cache theo từng layer. Requirements ít thay đổi nên layer `pip install` được dùng lại; sửa `app.py` chỉ build lại các layer copy code phía sau, không cài lại thư viện → build nhanh hơn rất nhiều.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, bị ghi đè khi chạy `docker run image <lệnh khác>`. `ENTRYPOINT` là chương trình cố định của container, tham số của `docker run` được nối vào sau nó. Thường dùng `ENTRYPOINT` cho executable chính, `CMD` cho tham số mặc định.

### Exercise 2.2: Build và chạy container develop
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run --rm -p 8000:8000 my-agent:develop
```
```text
$ curl -X POST "http://localhost:8000/ask?question=What%20is%20Docker"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build & image size
- **Stage 1 (`builder`, `python:3.11-slim`):** cài `gcc`, `libpq-dev` rồi `pip install --user` dependencies vào `/root/.local`.
- **Stage 2 (`runtime`, `python:3.11-slim`):** tạo user non-root `appuser`, chỉ copy thư mục `.local` đã cài từ builder cùng `main.py` và `utils/mock_llm.py`, có `HEALTHCHECK`, chạy bằng `USER appuser`.
- **Vì sao nhỏ hơn:** image cuối không chứa compiler, header file, apt cache, pip cache của stage builder, và dùng base `slim` thay cho bản Python đầy đủ.

Số đo bằng `docker images | grep my-agent`:
```text
my-agent:advanced   1287d0322601   240MB    57.4MB
my-agent:develop    5368bb53aadb   1.67GB   426MB
```
| Image | Dung lượng trên đĩa | Content size (nén) |
|-------|--------------------:|-------------------:|
| develop | 1.67 GB (~1670 MB) | 426 MB |
| production (advanced) | 240 MB | 57.4 MB |
| **Giảm** | **≈ 85.6 %** | ≈ 86.5 % |

Cách tính: (1670 − 240) / 1670 × 100 ≈ 85.6 %.

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)
```text
            Client
              │  :80 (HTTP) / :443
              ▼
        ┌───────────┐
        │   nginx   │  reverse proxy / load balancer (cổng duy nhất mở ra ngoài)
        └─────┬─────┘
              │ http://agent:8000
              ▼
        ┌───────────┐
        │   agent   │  FastAPI (build stage runtime), healthcheck /health
        └──┬─────┬──┘
           │     │
 redis://redis:6379   http://qdrant:6333
           ▼     ▼
     ┌────────┐ ┌────────┐
     │ redis  │ │ qdrant │
     │ cache/ │ │ vector │
     │session │ │   DB   │
     └────────┘ └────────┘
   Tất cả cùng network "internal" (bridge); volume redis_data, qdrant_data
```
- Services được start: `agent`, `redis`, `qdrant`, `nginx`.
- Giao tiếp: các container gọi nhau bằng **tên service** qua DNS nội bộ của network `internal`. `agent` dùng `depends_on: condition: service_healthy`, nên chỉ khởi động sau khi redis và qdrant healthy. Chỉ nginx publish cổng ra máy host; agent, redis, qdrant không lộ ra ngoài.

Kết quả test qua Nginx:
```text
$ curl http://localhost/health
{"status":"ok","uptime_seconds":25.8,"version":"2.0.0","timestamp":"2026-11-26T08:52:50.922711"}

$ curl -X POST http://localhost/ask -H 'Content-Type: application/json' -d '{"question":"Explain microservices"}'
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment
- URL: https://your-app.railway.app
- Screenshot: [Link to screenshot in repo]

## Part 4: API Security
 
### Exercise 4.1: API Key authentication (`04-api-gateway/develop`)
Chạy: `AGENT_API_KEY=secret-key-123 python app.py`
 
- **API key được check ở đâu:** hàm `verify_api_key` trong `app.py`, gắn vào `/ask` bằng `Depends(verify_api_key)`. Hàm đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)` rồi so với biến môi trường `AGENT_API_KEY`.
- **Sai key thì sao:** thiếu key → **401** `Missing API key`; có key nhưng sai → **403** `Invalid API key.`
- **Rotate key:** key đọc từ env nên chỉ cần đổi giá trị `AGENT_API_KEY` trên môi trường rồi restart/redeploy, không sửa code. Muốn không gián đoạn client thì tạm cho phép cả key cũ và key mới trong thời gian chuyển, sau đó gỡ key cũ.
- **Nhận xét thêm:**
  - `/ask` đọc body bằng `await request.json()` mà không validate: gọi kiểu `?question=Hello` không có JSON body → server trả **500 Internal Server Error** thay vì lỗi 4xx rõ ràng (tôi gặp lỗi này khi test).
  - Lúc khởi động app `print(f"API Key: {API_KEY}")` → lộ secret trong log.
  - So sánh key bằng `!=` thay vì `secrets.compare_digest` (có thể bị timing attack).
Không có key → 401:
```text
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 09:11:42 GMT
server: uvicorn
content-length: 67
content-type: application/json
 
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```
 
Key đúng → 200:
```text
$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" \
    -H 'Content-Type: application/json' -d '{"question":"Hello"}'
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 09:13:19 GMT
server: uvicorn
content-length: 122
content-type: application/json
 
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```
 
### Exercise 4.2: JWT authentication (`04-api-gateway/production`)
**JWT flow (`auth.py`):**
1. Client gọi `POST /auth/token` với `{"username","password"}`; `authenticate_user` kiểm tra trong `DEMO_USERS` (`student`/`demo123` role `user`, `teacher` role `admin`).
2. `create_token` tạo payload gồm `sub` (username), `role`, `iat`, `exp` (+60 phút), ký **HS256** bằng `JWT_SECRET` (đọc từ env).
3. Client gửi `Authorization: Bearer <token>` cho mọi request.
4. `verify_token` decode và kiểm tra chữ ký + hạn: thiếu token → **401**, token hết hạn → **401** `Token expired`, chữ ký sai → **403** `Invalid token.`
5. Server không cần tra DB mỗi request vì username/role đã nằm trong token (stateless).
Lấy token (token đã che):
```text
$ TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
    -H 'Content-Type: application/json' \
    -d '{"username":"student","password":"demo123"}' \
    | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
$ echo ${TOKEN:0:20}...
eyJhbGciOiJIUzI1NiIs...
```
 
Không có token → 401:
```text
$ curl -i -X POST http://localhost:8000/ask \
    -H 'Content-Type: application/json' -d '{"question":"Explain JWT"}'
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 09:19:09 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin
 
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```
 
Có token → 200:
```text
$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 09:17:45 GMT
server: uvicorn
content-length: 192
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin
 
{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```
 
Nhận xét:
- Middleware `security_headers` thêm đủ `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`. Nhưng `server: uvicorn` vẫn còn: middleware xoá header `server`, nhưng uvicorn gắn header này sau middleware → phải tắt bằng `server_header=False` khi chạy uvicorn.
- Field `budget_remaining_usd` thực ra trả `usage.total_cost_usd` (số tiền **đã dùng**, 1.9e-05 USD sau 1 request), không phải số còn lại → đặt tên sai.
### Exercise 4.3: Rate limiting (`rate_limiter.py`)
- **Algorithm:** **Sliding Window** — mỗi user một `deque` timestamp; mỗi request bỏ các timestamp cũ hơn 60 giây rồi đếm số còn lại, nếu ≥ limit thì chặn.
- **Limit:** `rate_limiter_user = RateLimiter(max_requests=10, window_seconds=60)` → **10 req/phút** cho user thường; `rate_limiter_admin` → **100 req/phút**.
- **Bypass cho admin:** không bỏ qua hoàn toàn mà chọn limiter theo role trong JWT: `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`.
- **Khi vượt:** trả **429 Too Many Requests** kèm `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- **Hạn chế:** state nằm trong RAM của process → chạy nhiều worker/instance thì mỗi nơi đếm riêng (user được nhân limit), restart là mất. Production cần lưu trong Redis (sorted set).
Vòng lặp 15 request với token `student`:
```text
$ for i in $(seq 1 15); do
    curl -s -o /dev/null -w "$i -> %{http_code}\n" -X POST http://localhost:8000/ask \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
      -d "{\"question\":\"Test $i\"}"
  done
1 -> 200
2 -> 200
3 -> 200
4 -> 200
5 -> 200
6 -> 200
7 -> 200
8 -> 200
9 -> 200
10 -> 200
11 -> 429
12 -> 429
13 -> 429
14 -> 429
15 -> 429
```
 
Response 429:
```text
$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d '{"question":"one more"}'
HTTP/1.1 429 Too Many Requests
date: Thu, 26 Nov 2026 09:19:29 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795684830
retry-after: 50
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin
 
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":50}}
```
 
**Giải thích:** request đầu tiên (Exercise 4.2) lúc 09:17:45 đã trượt ra khỏi cửa sổ 60 giây khi vòng lặp chạy lúc ~09:19:20, nên vòng lặp có đủ 10 request 200, request thứ 11 bị 429. `retry-after: 50` = số giây đến khi request cũ nhất trong cửa sổ hiện tại hết hạn và có lại 1 lượt.
 
### Exercise 4.4: Cost guard (`cost_guard.py`)
**Cách hoạt động hiện tại:**
1. **Trước khi gọi LLM** — `cost_guard.check_budget(username)`:
   - Tổng chi phí toàn hệ thống trong ngày ≥ **$10** → **503** (tạm ngừng dịch vụ đến hôm sau).
   - Chi phí của user trong ngày ≥ **$1** → **402 Payment Required** kèm `used_usd`, `budget_usd`, `resets_at: midnight UTC`.
   - Dùng ≥ **80%** budget → ghi log warning để cảnh báo sớm.
2. **Sau khi gọi LLM** — `cost_guard.record_usage(username, input_tokens, output_tokens)`: cộng token vào bản ghi theo ngày (`UsageRecord.day`), chi phí = `input/1000 × $0.00015 + output/1000 × $0.0006` (giá gpt-4o-mini); sang ngày mới `_get_record` tạo bản ghi mới → tự reset.
3. Hạn chế: state trong RAM, nhiều instance sẽ đếm riêng và mất khi restart.
**Cách implement bằng Redis theo yêu cầu bài ($10/tháng/user, reset đầu tháng):**
```python
import redis
from datetime import datetime
 
r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
MONTHLY_BUDGET_USD = 10.0
 
def check_budget(user_id: str, estimated_cost: float) -> bool:
    """True nếu còn budget, False nếu vượt."""
    key = f"budget:{user_id}:{datetime.now().strftime('%Y-%m')}"   # mỗi tháng một key
    current = float(r.get(key) or 0)
    if current + estimated_cost > MONTHLY_BUDGET_USD:
        return False                                  # endpoint trả 402
    r.incrbyfloat(key, estimated_cost)                # cộng dồn, atomic
    r.expire(key, 32 * 24 * 3600)                     # key tự hết hạn → reset đầu tháng
    return True
```
- Key chứa `YYYY-MM` nên sang tháng mới tự dùng key mới (reset), `EXPIRE` dọn key cũ.
- `INCRBYFLOAT` là atomic nên nhiều instance cùng cộng không bị mất số.
- State ở Redis nên mọi instance dùng chung, restart không mất.
**Vì sao cần cả rate limit và cost guard:** rate limit bảo vệ **tốc độ** (chặn spam, DoS, bot gọi dồn dập); cost guard bảo vệ **tiền**. Một user gửi chậm, dưới rate limit, nhưng prompt dài hoặc model đắt vẫn có thể đốt hết ngân sách → chỉ cost guard chặn được. Ngược lại, hàng nghìn request rẻ làm quá tải server thì chỉ rate limit chặn được.

## Part 5: Scaling & Reliability
 
### Exercise 5.1: Health checks (`05-scaling-reliability/develop`)
- **`/health` — liveness:** "process còn sống không?". Trả 200 khi process chạy, kèm `uptime`, `version`, và check bộ nhớ bằng `psutil` (dùng > 90% → `degraded`). Nếu liveness fail, platform **restart** container.
- **`/ready` — readiness:** "sẵn sàng nhận traffic chưa?". Trả 503 khi `_is_ready = False` (đang khởi động hoặc đang shutdown), 200 khi sẵn sàng, kèm số `in_flight_requests`. Nếu readiness fail, load balancer **ngừng gửi request** tới instance đó nhưng **không restart** nó.
- Khác nhau: một instance có thể còn sống (`/health` 200) nhưng chưa sẵn sàng (`/ready` 503), ví dụ đang load model, mất kết nối Redis, hoặc đang drain request khi shutdown. Gộp hai cái làm một thì hoặc platform restart nhầm instance chỉ đang bận, hoặc vẫn gửi traffic vào instance chưa dùng được.
```text
$ curl -i http://localhost:8000/health ; curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 09:24:42 GMT
server: uvicorn
content-length: 186
content-type: application/json
 
{"status":"ok","uptime_seconds":30.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T09:24:43.850126+00:00","checks":{"memory":{"status":"ok","used_percent":11.5}}}
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 09:24:42 GMT
server: uvicorn
content-length: 37
content-type: application/json
 
{"ready":true,"in_flight_requests":1}
```
`in_flight_requests: 1` chính là request `/ready` đang được middleware `track_requests` đếm.
 
### Exercise 5.2: Graceful shutdown
Cách app làm: middleware `track_requests` đếm `_in_flight_requests`; khi uvicorn nhận SIGTERM, nó ngừng nhận kết nối mới, chờ request đang chạy xong (`timeout_graceful_shutdown=30`), rồi chạy phần shutdown của `lifespan`: đặt `_is_ready = False` (để `/ready` trả 503, load balancer ngừng gửi traffic), chờ `_in_flight_requests` về 0 rồi thoát.
 
Test: bật app, gửi 1 request, ngay 0.05s sau gửi SIGTERM.
```text
$ python app.py > shutdown.log 2>&1 &
$ PID=$!; sleep 3
$ curl -s -X POST "http://localhost:8000/ask?question=Long%20task" &
$ sleep 0.05; kill -TERM $PID; wait
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}[1]-  Done    python app.py > shutdown.log 2>&1
 
$ tail -15 shutdown.log
INFO:     Started server process [3156]
INFO:     Waiting for application startup.
2026-11-26 16:28:40,588 INFO Agent starting up...
2026-11-26 16:28:40,589 INFO Loading model and checking dependencies...
2026-11-26 16:28:40,791 INFO ✅ Agent is ready!
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Shutting down
INFO:     127.0.0.1:52934 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-26 16:28:46,471 INFO 🔄 Graceful shutdown initiated...
2026-11-26 16:28:46,473 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [3156]
2026-11-26 16:28:46,480 INFO Received signal 15 — uvicorn will handle graceful shutdown
```
**Quan sát:**
- `Shutting down` xuất hiện **trước** dòng `POST /ask ... 200 OK` → request đang chạy vẫn được xử lý xong và client nhận được câu trả lời, không bị cắt ngang.
- Process tự thoát sạch (job báo `Done`, không phải `Killed`).
- Dòng `Received signal 15` của handler tự viết lại in **cuối cùng**: trong lúc chạy, uvicorn chiếm quyền xử lý SIGTERM; khi tắt xong nó trả lại handler cũ và phát lại tín hiệu. Nghĩa là graceful shutdown do uvicorn + `lifespan` đảm nhận; nếu tự viết handler mà không gọi lại handler của uvicorn thì process có thể không bao giờ tắt.
### Exercise 5.3: Stateless design (`05-scaling-reliability/production/app.py`)
- **Anti-pattern:** lưu `conversation_history = {}` trong RAM. Khi chạy nhiều instance, mỗi instance có bộ nhớ riêng → request tiếp theo của cùng user rơi vào instance khác sẽ **không thấy history**; restart/scale down là mất state.
- **Cách bản production làm:** `save_session` / `load_session` lưu session vào Redis với key `session:{session_id}` và TTL 3600s (`SETEX`); `append_to_history` đọc session, thêm message (giữ tối đa 20), ghi lại. Instance nào cũng đọc được session nên có thể scale ngang tự do.
- **Nhận xét:**
  - Nếu không kết nối được Redis lúc khởi động, app fallback sang `_memory_store` (RAM) và vẫn chạy → quay lại đúng anti-pattern mà không báo lỗi rõ. Production nên fail ở `/ready` (app đã có: `/ready` ping Redis, lỗi → 503).
  - `append_to_history` là read-modify-write không atomic: hai request cùng session tới 2 instance cùng lúc có thể ghi đè nhau và mất 1 message. Có thể dùng `RPUSH` + `LTRIM` trên Redis list để thêm message atomic.
### Exercise 5.4: Load balancing (Nginx + 3 agent)
```text
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
$ docker compose -p k5-day14-scaling ps
NAME                       IMAGE                    SERVICE   STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   agent     Up 17 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   agent     Up 17 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   agent     Up 17 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             nginx     Up 16 seconds             0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           redis     Up 28 seconds (healthy)   6379/tcp
```
```text
$ for i in $(seq 1 10); do
    curl -s -X POST http://localhost:8080/chat -H 'Content-Type: application/json' \
      -d "{\"question\":\"Request $i\"}" | python -c 'import sys,json;print(json.load(sys.stdin)["served_by"])'
  done
instance-bb6f84
instance-7e3d0f
instance-2b79d4
instance-bb6f84
instance-7e3d0f
instance-2b79d4
instance-bb6f84
instance-7e3d0f
instance-2b79d4
instance-bb6f84
```
- 3 instance được start, chỉ Nginx mở cổng ra ngoài (8080); agent và Redis nằm trong network nội bộ.
- Nginx chia request theo **round-robin** (mặc định của `upstream agent_cluster`): 10 request xoay vòng đúng thứ tự bb6f84 → 7e3d0f → 2b79d4.
- `nginx.conf` có `proxy_next_upstream error timeout http_503` + `proxy_next_upstream_tries 3`: instance lỗi hoặc trả 503 (chưa ready) thì Nginx thử instance khác.
### Exercise 5.5: Test stateless (`python test_stateless.py`)
Tôi dừng hẳn 1 instance (`docker stop k5-day14-scaling-agent-1`, tức `instance-7e3d0f`) rồi chạy script:
```text
$ docker stop k5-day14-scaling-agent-1
$ python test_stateless.py
============================================================
Stateless Scaling Demo
============================================================
 
Session ID: 73071258-bf9c-4571-89f4-95ae583393f7
 
Request 1: [instance-2b79d4]
  Q: What is Docker?
Request 2: [instance-2b79d4]
  Q: Why do we need containers?
Request 3: [instance-bb6f84]
  Q: What is Kubernetes?
Request 4: [instance-2b79d4]
  Q: How does load balancing work?
Request 5: [instance-bb6f84]
  Q: What is Redis used for?
------------------------------------------------------------
Total requests: 5
Instances used: {'instance-bb6f84', 'instance-2b79d4'}
✅ All requests served despite different instances!
 
--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: How does load balancing work?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Redis used for?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
 
✅ Session history preserved across all instances via Redis!
```
Log của agent còn sống (`docker compose -p k5-day14-scaling logs agent`) cho thấy `Storage: Redis ✅` và các `POST /chat` được phục vụ bình thường.
 
**Giải thích kết quả:**
- Sau khi 1 instance bị dừng, Nginx tự chuyển traffic sang 2 instance còn lại; không request nào lỗi.
- 5 câu hỏi của cùng một session được trả lời bởi **2 instance khác nhau**, nhưng history đọc về vẫn đủ **10 message** (5 hỏi + 5 đáp, đúng thứ tự) → state nằm trong Redis, không phụ thuộc instance nào xử lý request.
- Nếu lưu history trong RAM, mỗi instance chỉ thấy phần hội thoại mình xử lý và history sẽ bị thiếu/lộn xộn.
Dọn dẹp: `docker compose -p k5-day14-scaling down` (dùng `-p` riêng để không nhầm với project `production` của Part 2 và Part 7).
 
## AI log
| Lần | Hỏi AI gì | Nhận được gì | Tự kiểm tra thế nào |
|-----|-----------|--------------|---------------------|
| 1 | Claude: hướng dẫn theo checkpoint, CP1 | Danh sách anti-pattern + bảng so sánh | Tự chạy develop/production, đối chiếu từng dòng với app.py, config.py |
| 2 | Claude: soạn câu trả lời Part 2 từ output tôi chạy | Giải thích Dockerfile, multi-stage, sơ đồ compose, cách tính % | Đối chiếu với Dockerfile/compose; số MB là số tôi đo bằng `docker images` |
| 3 | Claude: lệnh test graceful shutdown, load balancing, stateless; hoàn thiện Part 5 | Lệnh test + giải thích kết quả | Tự chạy, output là của tôi; tự dừng 1 instance để kiểm chứng; đối chiếu với app.py, nginx.conf |