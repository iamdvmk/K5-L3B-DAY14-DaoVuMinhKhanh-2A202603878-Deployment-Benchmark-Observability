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

### Exercise 1.2: Logging
curl -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

### Exercise 1.3: Comparison table
| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode | Biến môi trường (config.py) | Cùng một code chạy dev/staging/prod; secret không lọt lên Git |
| Health check | Không có | /health, /ready | Platform biết khi nào restart / khi nào route traffic |
| Logging | print() | JSON | Lọc, tìm kiếm được; không in secret |
| Shutdown | Đột ngột | Graceful (SIGTERM) | Không mất request khi deploy/scale |
| Host/Port | localhost:8000 | 0.0.0.0:$PORT | Cloud cấp PORT, container cần bind mọi interface |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions
1. Base image: [Your answer]
2. Working directory: [Your answer]
...

### Exercise 2.3: Image size comparison
- Develop: [X] MB
- Production: [Y] MB
- Difference: [Z]%

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