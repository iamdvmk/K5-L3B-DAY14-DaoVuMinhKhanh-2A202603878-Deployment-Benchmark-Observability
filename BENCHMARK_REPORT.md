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

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...