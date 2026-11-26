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

### Exercise 4.1-4.3: Test results
[Paste your test outputs]

### Exercise 4.4: Cost guard implementation
[Explain your approach]

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes
[Your explanations and test results]

## AI log
| Lần | Hỏi AI gì | Nhận được gì | Tự kiểm tra thế nào |
|-----|-----------|--------------|---------------------|
| 1 | Claude: hướng dẫn theo checkpoint, CP1 | Danh sách anti-pattern + bảng so sánh | Tự chạy develop/production, đối chiếu từng dòng với app.py, config.py |