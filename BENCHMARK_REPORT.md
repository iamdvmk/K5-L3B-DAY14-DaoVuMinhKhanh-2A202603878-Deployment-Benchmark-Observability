# Benchmark & Observability Report — Day 14

**Họ tên:** Đào Vũ Minh Khánh — 2A202603878
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows + WSL2 (Ubuntu), Docker Desktop (Docker 29.9.3), Python 3.11.18 (venv `uv`); agent develop chạy local (v1 cổng 8001, v2 cổng 8002)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Một lần gọi LLM mock mất ~150–220 ms (p50 ≈ 190 ms ở mọi mức tải chưa bão hoà) → 500 ms còn ~2.5 lần dư cho mạng/xếp hàng. Đặt theo p95 vì trung bình che mất request chậm (mục 2.2). Ngưỡng này cũng là mặc định của `load_test.py` và alert `AgentHighLatencyP95`. |
| Error rate `/ask` | < 2 % | Mock tự sinh lỗi 503 ngẫu nhiên (đo được 0.33–2.00% ở mọi mức tải, kể cả concurrency 1) → 2% là mức "bình thường" của hệ thống; vượt 2% nghĩa là có sự cố thật. |
| Accuracy trên golden dataset | ≥ 85 % | Quality gate CI dùng `--min-accuracy 0.85`: chặn bản như v1 (4.3%) nhưng vẫn cho phép sai 3/23 câu khi thêm chủ đề mới. Sau khi sửa KB, v2 đạt 100% nên lần release này dùng `--min-accuracy 1.0` làm baseline mới. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Mỗi mức: `--requests 300`, file `reports/load_v2_c{N}.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.65 | 187.7 | 216.8 | 1667.8 | 2.00% | ✅ PASS |
| 10 | 41.0 | 188.9 | 219.6 | 1679.3 | 0.33% | ✅ PASS |
| 50 | 110.47 | 196.1 | 243.6 | 1696.6 | 1.67% | ✅ PASS |
| 100 | 59.25 | 363.1 | 3011.3 | 3296.5 | 2.00% | ❌ FAIL (p95 > 500 ms) |

**Nhận xét:** RPS tăng gần tuyến tính từ concurrency 1 → 50 (4.65 → 41.0 → 110.47 req/s) trong khi p50 gần như đứng yên (187.7 → 196.1 ms). Lý do: mỗi request phần lớn là *chờ* LLM (~150–200 ms, I/O), server async xử lý chồng nhiều request cùng lúc, nên thêm request song song = thêm việc xong mỗi giây. Ở concurrency 100 hệ thống **bão hoà**: RPS *giảm* còn 59.25 req/s, p50 tăng lên 363.1 ms và p95 vọt lên 3011.3 ms (vi phạm SLO) — request phải xếp hàng chờ event loop / kết nối, thời gian chờ cộng thẳng vào latency. Điểm tải hợp lý cho 1 instance nằm quanh 50 request đồng thời; muốn hơn phải scale ngang (mục 5). p99 ~1.7 s ngay cả ở concurrency 1 là do ~3% request bị làm chậm (`MOCK_SLOW_RATE=0.03` mặc định), không phải do tải; error 0.33–2% là lỗi 503 ngẫu nhiên của mock, có cả ở concurrency 1.

### 2.2 Tail latency

`--requests 300 --concurrency 20`, file `reports/load_v2_slow_{rate}.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 188.9 | 216.1 | 222.5 |
| 0.03 (mặc định) | 218.0 | 221.8 | 1683.9 |
| 0.1 | 372.9 | 1695.1 | 1715.0 |

**Nhận xét:** **p99 nhạy nhất**: chỉ 3% request chậm đã đẩy p99 từ 222.5 ms lên 1683.9 ms (~7.6 lần) trong khi avg chỉ tăng 188.9 → 218.0 ms (+15%) và p50 gần như không đổi (~189 ms). Khi tỉ lệ chậm lên 10% (> 5%), nhóm chậm lan sang **p95** (216.1 → 1695.1 ms) và SLO p95 ≤ 500 ms bị vỡ, avg cũng chỉ mới 372.9 ms. SLO không nên đặt theo average vì average bị số đông request nhanh kéo xuống: avg 218 ms trông "đạt" nhưng cứ 100 người thì ~3 người chờ > 1.6 s. p95/p99 đo đúng trải nghiệm của nhóm người dùng tệ nhất, và là nhóm hay bỏ đi nhất. Throughput cũng giảm (103.2 → 66.8 → 45.1 req/s) vì request chậm giữ chỗ một trong 20 luồng lâu hơn.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Golden dataset 23 câu; file `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.8 | 109.1 | 113.7 |
| Tổng cost (USD) | 0.000414 | 0.000762 | 0.00079 |
| Cost / câu đúng (USD) | 0.00041355 | 0.00003627 | 0.00003436 |
| Latency p50 / p95 (ms) | 162.2 / 185.3 | 189.5 / 1515.2 | 193.4 / 216.0 |
| Quality gate | ❌ FAIL (ngưỡng 80%) | ✅ PASS (ngưỡng 80%, 0 regression so với v1) | ✅ PASS (ngưỡng 100%, 0 regression so với v2) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | `KNOWLEDGE_BASE` không có tài liệu về JWT nên retrieval trả rỗng. Thêm mục keyword `["jwt"]` vào cuối `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py`: API key là chuỗi bí mật cố định, không tự hết hạn; JWT là token có chữ ký số, chứa thông tin user và thời điểm hết hạn. |
| scaling-03 ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Không có tài liệu về HPA. Thêm mục keyword `["hpa", "kubernetes", "autoscal"]`: HPA scale số pod theo CPU, memory hoặc custom metrics (RPS, độ dài hàng đợi). |

Không sửa `golden_dataset.jsonl`. Sau khi sửa phải tắt/bật lại v2 vì KB chỉ được đọc lúc khởi động.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v1 không có retrieval nên chỉ trả lời chung chung (4.3%); v2 thêm context từ `KNOWLEDGE_BASE` lên 91.3%, sửa KB lên 100%. Lỗi còn lại của v2 là *thiếu tài liệu*, không phải lỗi model — sửa dữ liệu rẻ hơn đổi model.
- **Chi phí:** v2 tốn ~1.9 lần token/câu (57.8 → 109.1) vì prompt chứa thêm context, tổng cost tăng 0.000414 → 0.000762 USD. Nhưng **cost / câu đúng giảm ~11 lần** (0.00041355 → 0.00003627 USD) vì v1 trả tiền cho câu trả lời sai. So theo "cost / câu" sẽ chọn nhầm v1 rẻ mà vô dụng; "cost / câu đúng" mới phản ánh tiền bỏ ra để có kết quả dùng được. Thêm 2 tài liệu chỉ tăng 4.6 token/câu.
- **Latency:** p50 v2 cao hơn v1 khoảng 27 ms (162.2 → 189.5 ms) do prompt dài hơn. p95 của v2 trong lần eval đầu (1515.2 ms) và lần sau khi sửa (216.0 ms) chênh nhau **không phải nhờ sửa KB**: với 23 câu, chỉ cần 1–2 câu rơi vào nhóm ~3% request bị làm chậm ngẫu nhiên (`reliability-01` 1659.6 ms, `cost-01` 1706.6 ms ở lần đầu) là p95 nhảy vọt. Muốn so latency giữa hai phiên bản phải dùng load test nhiều request (mục 2), không dùng eval 23 câu.
- **Quyết định:** chọn v2 (sau sửa KB): đúng 100%, rẻ nhất tính trên câu đúng, latency p50 vẫn xa SLO 500 ms.

**CI quality gate:** `.github/workflows/eval.yml` chạy trên mỗi pull request: bật agent v2 (`MOCK_ERROR_RATE=0` để lỗi ngẫu nhiên không làm fail CI), rồi `python eval/run_eval.py --min-accuracy 0.85`. `run_eval.py` trả **exit code 1** khi accuracy dưới ngưỡng hoặc có câu regression → step fail → job đỏ; bật branch protection "Require status checks to pass" trên `main` thì PR không merge được.

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose -p k5-day14-observability ...` trong `06-lab-complete/benchmark-observability/production/` (nginx + 3 agent + Prometheus + Grafana + Jaeger + Locust).

**Sự cố khi dựng stack:** lần đầu 100% request lỗi (Locust median 1 ms, Nginx trả 502 `no live upstreams`). Log agent: `ModuleNotFoundError: No module named 'uvicorn'` → container restart liên tục. Nguyên nhân: `Dockerfile` copy thư viện vào `/home/agent/.local` nhưng user `agent` được tạo với home `/app` (`useradd -d /app`), nên Python tìm user site-packages ở `/app/.local`. Sửa: thêm `ENV PYTHONUSERBASE=/home/agent/.local` (giống Dockerfile Part 5). Ngoài ra `.env` bị CRLF (`AGENT_VERSION=v2\r`) do checkout trên Windows → bỏ `\r` bằng `sed -i 's/\r$//'`.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`) — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing** — `screenshots/prometheus-alert-firing.png` (2 alert cùng firing)

**Exercise 7.4 — đọc dashboard khi Locust chạy 30 users / ramp 5, 3 instance:**

Giá trị lúc chụp: Traffic **18.5 req/s**, Error rate **1.47%**, Latency p95 **294.83 ms**, Saturation (in-flight) **7**, Instances up **3**, LLM cost (1h) **$0.70**.

1. **p95 và avg, khoảng cách nói lên điều gì?** p95 ≈ 295 ms, avg ≈ 230 ms (Locust CSV: avg `/ask` 228.1 ms ở 3 instance), p50 ≈ 190 ms, còn p99 trên panel Latency ≈ 1.9 s. avg và p95 gần nhau, nhưng p99 cao gấp ~10 lần p50: đa số request đều nhanh, còn một nhóm nhỏ (~3%, `MOCK_SLOW_RATE=0.03`) rất chậm. avg bị số đông request nhanh kéo xuống nên che mất nhóm chậm → phải nhìn p95/p99 (và đặt SLO theo percentile).
2. **Nginx có chia đều traffic không?** Có. Query Prometheus `sum by (instance) (rate(http_requests_total{route="/ask"}[1m]))` trong lúc có tải:
   ```text
   "instance": "172.19.0.5:8000"   6.181818181818182
   "instance": "172.19.0.8:8000"   6.290909090909091
   "instance": "172.19.0.9:8000"   6.1090909090909085
   ```
   Ba instance nhận 6.11–6.29 req/s (lệch < 3%), tổng ≈ 18.6 req/s khớp panel Traffic → round-robin mặc định của `upstream agent_cluster`.
3. **Vì sao input tokens/s > output tokens/s?** Mỗi request v2 gửi vào LLM cả câu hỏi **lẫn context retrieval** từ `KNOWLEDGE_BASE`, nên prompt dài hơn câu trả lời. Ví dụ trace chậm ở mục 4.3: input 95 token, output 55 token. Đây cũng là lý do v2 tốn ~1.9 lần token/câu so với v1 (mục 3).
4. **`curl http://localhost:8080/metrics` trả về gì?** **404**. `nginx.conf` có `location = /metrics { return 404; }`: `/metrics` chỉ dành cho Prometheus scrape trực tiếp từng agent trong mạng nội bộ Docker; public ra ngoài sẽ lộ route, lưu lượng, cost, thông tin process. Ngoài ra qua Nginx mỗi lần chỉ trúng 1 instance theo round-robin nên số liệu cũng vô nghĩa.

### 4.2 Thí nghiệm "phá hệ thống"

`promtool test rules /p/alert_rules_test.yml` → `SUCCESS`. Thí nghiệm làm trong lúc Locust chạy 30 users, 3 instance. Giờ PENDING lấy từ `ALERTS_FOR_STATE` của Prometheus, giờ FIRING = PENDING + `for`.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (22:15:28) | `AgentHighErrorRate` (giá trị 0.1917 > 0.05) | PENDING 22:15:52, FIRING 22:16:52 → **84 s** | Error rate (stat) và Requests/s theo status code (đường 503 tăng) |
| B | `MOCK_SLOW_RATE=0.3` | Không thực hiện | – | (dự kiến: Latency /ask p95, `AgentHighLatencyP95` sau `for: 2m`) |
| C | `LLM_MODEL=mock-llm-large` | Không thực hiện riêng — xem ghi chú | – | Cost burn rate (USD/giờ) |
| D | `docker pause k5-day14-observability-agent-1` (22:15:31) | `AgentInstanceDown` (instance `172.19.0.5:8000`) | PENDING 22:15:32, FIRING 22:16:02 → **31 s** | Instances up (3 → 2) |
| E | `AGENT_VERSION=v1` | Không thực hiện trên stack; không alert nào firing (xem bên dưới) | – | Không panel hạ tầng nào đổi màu |

**Giải thích thời gian:** thời gian tới FIRING ≈ chờ lần scrape kế tiếp (5 s) + thời gian để biểu thức vượt ngưỡng + `for`.
- D nhanh (31 s): `up{job="agent"} == 0` đúng ngay ở lần scrape đầu tiên thất bại (~1 s sau khi pause), rồi giữ thêm `for: 30s`.
- A chậm hơn (84 s): `rate(...[1m])` là trung bình 1 phút, cần ~24 s để tỉ lệ lỗi trung bình vượt 5% (lỗi mới trộn với dữ liệu cũ 1%), rồi giữ thêm `for: 1m`. `for` giúp tránh báo động giả khi lỗi chỉ tăng vọt vài giây.

**Ghi chú về chi phí (liên quan thí nghiệm C):** `LLMCostBurnRateHigh` đã **tự firing lúc 22:13:02** (PENDING 22:11:02 + `for: 2m`) dù chưa đổi model — trong lúc benchmark scale 100 users (~60 req/s). Panel Cost burn rate lên ~$4–5/giờ, vượt ngưỡng $2/giờ. Nghĩa là chỉ riêng lưu lượng cao với `mock-llm-small` đã đủ đốt quá ngân sách; đổi sang `mock-llm-large` (đắt ~16 lần) sẽ chạm ngưỡng ở lưu lượng thấp hơn nhiều. Cost alert là lớp bảo vệ bổ sung cho cost guard (402) ở Part 6.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đổi sang v1 làm accuracy rơi từ 100% xuống 4.3% (mục 3), nhưng v1 vẫn trả 200 nhanh hơn, ít token hơn → error rate, latency, instance, cost đều "xanh". Alert hạ tầng chỉ đo *hệ thống có chạy không*, không đo *trả lời có đúng không*. Phát hiện bằng:
1. **Quality gate trước khi deploy:** `run_eval.py --min-accuracy 0.85 --baseline` trong CI (`.github/workflows/eval.yml`) — v1 sẽ fail với exit code 1, không merge/deploy được.
2. **Eval định kỳ trên production:** cron chạy golden dataset vào môi trường thật, đẩy accuracy thành metric (vd `eval_accuracy`) và alert khi dưới SLO 85%.
3. **Metric/alert chất lượng gián tiếp:** theo dõi `agent_version` đang chạy (thay đổi bất thường), tỉ lệ câu không tìm được context, độ dài câu trả lời, feedback 👍/👎 của user.

**Vì sao lỗi 504 ở Nginx không hiện trên metric của agent:** 504 do **Nginx tự sinh** khi agent không trả lời trong thời gian `proxy_read_timeout`. Request có thể chưa tới agent, hoặc agent vẫn đang xử lý / bị treo nên chưa ghi xong `http_requests_total`, và nếu agent trả lời muộn thì nó ghi status 200. Prometheus chỉ scrape `/metrics` của agent nên không thấy 504. Muốn thấy phải đo ở tầng trước: metric/log của Nginx (exporter hoặc access log), hoặc đo phía client (Locust, synthetic check, SLO đo từ góc nhìn người dùng).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được (Jaeger → `observable-agent` → sắp xếp theo Duration giảm dần):

- `trace_id`: `4143cb9d81d57956dd9498acd1d213ae` (`observable-agent: POST /ask`, 22:09:43.418, 4 span, depth 3, status 200)
- Tổng thời gian: **1704.2 ms** (Jaeger: 1.7 s)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (1685.0 ms, **98.9%**). `agent.retrieve_context` chỉ 17.3 ms (~1%); phần còn lại của agent < 2 ms. Token: input 95, output 55.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T15:09:45.122351+00:00", "level": "INFO", "service": "observable-agent", "instance": "30e5b040758e", "event": "llm_call", "trace_id": "4143cb9d81d57956dd9498acd1d213ae", "span_id": "99c40ad9b876b71b", "request_id": "3f59acce37b7", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1685.0}
{"ts": "2026-11-26T15:09:45.122765+00:00", "level": "INFO", "service": "observable-agent", "instance": "30e5b040758e", "event": "http_request", "trace_id": "4143cb9d81d57956dd9498acd1d213ae", "span_id": "99c40ad9b876b71b", "request_id": "3f59acce37b7", "method": "POST", "route": "/ask", "status": 200, "ms": 1704.2}
```

**Kết luận:** request chậm vì **chính lời gọi LLM chậm** (rơi vào nhóm ~3% `MOCK_SLOW_RATE`), không phải do retrieval hay code agent. Giảm tail latency phải xử lý ở tầng gọi LLM (timeout + retry/hedging, fallback model, cache câu hỏi lặp lại); thêm instance không giúp (mục 5).

**Trace lỗi:** log `llm_error` dùng để tìm trace lỗi trong Jaeger (Lookup by Trace ID):

```json
{"ts": "2026-11-26T15:00:04.936216+00:00", "level": "INFO", "service": "observable-agent", "instance": "8ed533881a3f", "event": "llm_error", "trace_id": "1e9ef039f9b7a4ce8c7c1c6cf9753397", "span_id": "b19940be60ca2fc3", "request_id": "42c7b1b8a8c6", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

Trace lỗi có 3 span báo lỗi; span gọi LLM chứa event `exception` với thông báo `503 Service Unavailable (mock)` (`screenshots/jaeger-error-trace.png`). Lỗi được đánh dấu lan lên span cha nên tìm được bằng `error=true`.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu lấy từ dòng `Aggregated` của `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv` (spawn rate 10, `--host http://nginx`).

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.55 | 190 | 220 | 1700 | 66 / 7852 (0.84%) |
| 3 | 66.19 | 190 | 220 | 1700 | 72 / 7902 (0.91%) |

Riêng `POST /ask`: 1 instance 59.40 req/s, avg 237.3 ms; 3 instance 60.11 req/s, avg 228.1 ms. Failures đều là `503 Service Unavailable` từ mock (`MOCK_ERROR_RATE=0.01`).

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance **gần như không đổi** (RPS +1%, p50/p95/p99 giữ nguyên). Không phải scale vô dụng mà bài test chưa làm 1 instance quá tải:
- **Nút thắt ở phía tạo tải:** `locustfile.py` cho mỗi user nghỉ `between(0.5, 2)` giây giữa các request. Mỗi vòng ≈ 1.25 s nghỉ + ~0.2 s chờ → 100 user tạo tối đa ≈ 100 / 1.45 ≈ **69 req/s**. Đo được 65–66 req/s, tức là đã chạm trần của Locust. Ở CP7, 1 instance develop chịu được ~110 req/s, nên 1 instance production vẫn còn dư.
- **Latency do LLM, không do CPU:** p50 ≈ 190 ms là thời gian chờ LLM mock (`MOCK_LATENCY_MS=120` + jitter), p99 ≈ 1700 ms là nhóm `MOCK_SLOW_RATE`. Thêm instance không làm LLM trả lời nhanh hơn.
- Muốn thấy lợi ích của scale cần tải vượt sức 1 instance (vd 400–500 users, hoặc giảm `wait_time`): khi đó 1 instance sẽ xếp hàng (p95 tăng vọt như concurrency 100 ở mục 2.1) còn 3 instance chia tải được. Scale ngang tăng **thông lượng** và **khả năng chịu lỗi** (thí nghiệm D: mất 1 instance vẫn phục vụ được), không giảm latency của dependency chậm.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Trung bình nói dối, percentile nói thật.** 3% request chậm chỉ làm avg tăng 15% nhưng đẩy p99 lên 7.6 lần; SLO và alert phải đặt theo p95/p99, và phải chạy đủ nhiều request (eval 23 câu không đủ để so latency).
  2. **"Xanh" về hạ tầng không có nghĩa là đúng.** Thí nghiệm E và so sánh v1/v2: chất lượng chỉ đo được bằng eval trên golden dataset + quality gate; "cost / câu đúng" mới là thước đo chi phí có ý nghĩa (v2 đắt hơn mỗi câu nhưng rẻ hơn ~11 lần mỗi câu đúng).
  3. **Metric, log, trace phải nối với nhau.** Grafana cho biết *có* vấn đề (p99 cao), Jaeger cho biết *ở đâu* (span LLM chiếm 98.9%), log có cùng `trace_id` cho biết *chi tiết* (model, token, cost). Khi dựng stack bị 502, chính log agent (`ModuleNotFoundError`) chỉ ra lỗi Dockerfile.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

  - **Chất lượng:** metric `eval_accuracy` từ eval định kỳ + alert khi < 85%; tỉ lệ câu không tìm được context; feedback người dùng.
  - **Phía client / Nginx:** tỉ lệ 502/504 và latency đo ở Nginx hoặc synthetic check, vì agent không thấy lỗi xảy ra trước nó.
  - **Burn-rate SLO đa cửa sổ** (vd 1h và 6h) thay cho ngưỡng cố định, để vừa bắt sự cố nhanh vừa ít báo giả.
  - **LLM provider:** latency/timeout/lỗi theo model và provider, số lần retry, alert khi tỉ lệ 429/503 từ provider tăng.
  - **Chi phí theo user:** cost/ngày theo API key, alert khi một user dùng > 80% ngân sách (bổ sung cho cost guard 402).
  - **Saturation:** in-flight requests, CPU/RAM container, độ dài hàng đợi; alert để autoscale trước khi p95 vỡ.