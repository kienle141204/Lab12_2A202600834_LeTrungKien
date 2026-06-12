# Day 12 Lab - Mission Answers

> **Student Name:** Lê Trung Kiên  
> **Student ID:** 2A202600834  
> **Date:** 12/6/2026

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Đọc file `01-localhost-vs-production/develop/app.py`, tìm được **7 vấn đề**:

1. **API key hardcode trong code** — `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"`. Nếu push lên GitHub, key bị lộ ngay lập tức và không thể thu hồi.

2. **Database credentials hardcode** — `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Tương tự, mật khẩu database bị lộ trong code.

3. **Dùng `print()` thay vì logging** — Các dòng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vô tình log ra secret trong output. Không có log level, không có timestamp, không parse được bằng log aggregator.

4. **Không có health check endpoint** — Platform (Railway, Render, Kubernetes) không có cách nào biết agent có đang chạy tốt không để restart khi cần.

5. **Port cứng `port=8000`** — Không đọc từ biến môi trường `PORT`. Trên Railway/Render, PORT được inject tự động và thường khác 8000.

6. **`host="localhost"`** — Chỉ nhận kết nối từ chính máy đó. Bên trong container, localhost = container, không thể nhận traffic từ bên ngoài. Phải dùng `0.0.0.0`.

7. **`reload=True` luôn bật** — Debug reload chỉ nên dùng trong development. Trong production, nó làm tốc độ chậm đi và có thể gây restart bất ngờ.

---

### Exercise 1.2: Quan sát khi chạy basic version

Chạy `python app.py` trong `develop/` → app khởi động bình thường, request `/ask` trả về response.

**Nhưng KHÔNG production-ready vì:**
- Chạy ở `localhost:8000` → không thể nhận traffic từ container/internet
- Port cứng → xung đột nếu deploy lên platform inject PORT khác
- Nếu commit code này lên GitHub: key bị lộ ngay
- Platform không biết cách kiểm tra app có còn sống không (không có `/health`)

---

### Exercise 1.3: Bảng so sánh develop vs production

| Feature | Basic (develop) | Advanced (production) | Tại sao quan trọng? |
|---|---|---|---|
| **Config / Secrets** | Hardcode trực tiếp trong code (`OPENAI_API_KEY = "sk-..."`) | Đọc từ environment variables qua `config.py` / `Settings` | Nếu hardcode, secret bị lộ khi push lên Git. Env vars được inject an toàn bởi platform, không bao giờ vào code |
| **Health check** | Không có | `GET /health` trả về status, uptime, version | Platform cần endpoint này để biết app còn sống không → tự động restart khi crash |
| **Readiness probe** | Không có | `GET /ready` trả về 503 khi đang khởi động | Load balancer không route traffic vào instance chưa sẵn sàng → tránh request lỗi trong lúc startup |
| **Logging** | `print()` in ra stdout lẫn secrets | JSON structured logging (`{"event":..., "level":...}`) | JSON logs dễ parse bởi Datadog/Loki/CloudWatch. Structured logs hỗ trợ tìm kiếm, alert, dashboard |
| **Host binding** | `host="localhost"` | `host="0.0.0.0"` | `localhost` chỉ nhận kết nối từ bên trong container. `0.0.0.0` nhận từ mọi network interface → bắt buộc để container nhận traffic |
| **Port** | `port=8000` cứng | `port=int(os.getenv("PORT", 8000))` | Railway/Render inject `PORT` tự động (thường là số khác 8000). Không đọc từ env → app không start được trên cloud |
| **Debug mode** | `reload=True` luôn bật | `reload=settings.debug` — chỉ bật khi `DEBUG=true` | Debug reload làm chậm app, có thể restart bất ngờ. Production cần stable, predictable |
| **Graceful shutdown** | Không có | `signal.signal(SIGTERM, handle_sigterm)` + lifespan | Platform gửi SIGTERM trước khi kill container. Xử lý signal → hoàn thành request đang xử lý, tránh mất dữ liệu |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

**Đọc file `02-docker/develop/Dockerfile`:**

1. **Base image là gì?**
   `python:3.11` — bản full distribution (~1 GB), bao gồm compiler, debugger, tài liệu và các công cụ hệ thống.

2. **Working directory là gì?**
   `/app` — được đặt bằng lệnh `WORKDIR /app`. Toàn bộ lệnh `COPY`, `RUN`, `CMD` sau đó đều thực thi trong thư mục này.

3. **Tại sao COPY requirements.txt trước khi COPY code?**
   Docker build theo từng layer và cache lại. Nếu `requirements.txt` không đổi, layer `pip install` sẽ được lấy từ cache — không cần cài lại toàn bộ dependencies khi chỉ sửa code. Nếu COPY code trước, mỗi lần sửa code dù nhỏ cũng sẽ trigger pip install lại từ đầu → build chậm hơn nhiều.

4. **CMD vs ENTRYPOINT khác nhau thế nào?**
   - `CMD` — lệnh mặc định khi container start, **có thể override** khi chạy: `docker run image python other.py`
   - `ENTRYPOINT` — lệnh **cố định**, không bị override bởi argument thông thường. Dùng khi muốn container luôn chạy một chương trình nhất định.
   - Trong Dockerfile này dùng `CMD ["python", "app.py"]` → linh hoạt, dễ debug bằng cách override.

---

### Exercise 2.3: Image size comparison

| | Develop | Production |
|---|---|---|
| **Image name** | `agent-develop:latest` | `agent-production:latest` |
| **Size** | 1.66 GB | 236 MB |
| **Base image** | `python:3.11` (full) | `python:3.11-slim` |
| **Build stages** | 1 stage | 2 stages (builder + runtime) |

**Chênh lệch: 1.42 GB — production nhỏ hơn 86%**

**Tại sao production nhỏ hơn nhiều?**

1. **Base image `slim`** — `python:3.11-slim` (~150 MB) bỏ toàn bộ compiler, debugger, tài liệu so với `python:3.11` (~1 GB).

2. **Multi-stage build** — Stage 1 (builder) dùng `gcc`, `libpq-dev` để compile dependencies, nhưng toàn bộ Stage 1 bị **bỏ lại** sau khi build. Stage 2 (runtime) chỉ `COPY --from=builder` lấy đúng các packages đã compile, không mang theo build tools.

3. **`--no-cache-dir`** — pip không lưu cache (~50-100 MB) vì trong container không cần cài lại.

---

### Exercise 2.4: Docker Compose stack

**4 services được start:**

```
Client (browser/curl)
        │
        ▼ port 80/443
  ┌──────────────┐
  │    Nginx     │  ← reverse proxy, load balancer
  └──────┬───────┘
         │ round-robin
   ┌─────┴──────┐
   ▼            ▼
┌───────┐   ┌───────┐   ← agent (2 replicas, port 8000, không expose ra ngoài)
│Agent 1│   │Agent 2│
└───┬───┘   └───┬───┘
    │            │
    └─────┬──────┘
          │
    ┌─────┴──────────────┐
    ▼                    ▼
┌─────────┐        ┌──────────┐
│  Redis  │        │  Qdrant  │
│(cache)  │        │(vectors) │
└─────────┘        └──────────┘
```

**Các services communicate thế nào:**
- Tất cả nằm trong network `internal` (bridge) — cách ly hoàn toàn, bên ngoài không truy cập trực tiếp được
- Chỉ Nginx được expose ra ngoài qua port 80/443
- Agent kết nối Redis qua hostname `redis:6379` (Docker DNS tự resolve)
- Agent kết nối Qdrant qua hostname `qdrant:6333`
- Nginx load balance đến các agent instance qua hostname `agent:8000`
- Agent chỉ start sau khi Redis và Qdrant healthy (`depends_on` + `condition: service_healthy`)

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

**Platform:** Railway  
**Public URL:** https://lab11-production-c560.up.railway.app

**Các bước đã thực hiện:**
1. Copy `utils/mock_llm.py` vào `03-cloud-deployment/railway/utils/` để deployment tự chứa đủ file
2. `railway login` — đăng nhập qua browser
3. `railway init` — tạo project `lab11` trên workspace
4. `railway up` — upload và deploy code
5. `railway domain` — nhận public URL

**Kết quả test:**

Health check:
```
GET https://lab11-production-c560.up.railway.app/health
→ {"status":"ok","uptime_seconds":4583.7,"platform":"Railway","timestamp":"2026-06-12T08:57:51.321388+00:00"}
```

Ask endpoint:
```
POST https://lab11-production-c560.up.railway.app/ask
Body: {"question": "Am I on the cloud?"}
→ {"question":"Am I on the cloud?","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","platform":"Railway"}
```

**Quan sát:** Agent đang chạy ổn định trên cloud với uptime ~76 phút. Response trả về đúng field `"platform": "Railway"` — xác nhận đây là bản deploy trên Railway, không phải local.

**Lý do Railway phù hợp cho prototype:**
- Deploy chỉ bằng `railway up` — không cần cấu hình server, DNS, hay container registry
- Tự động detect Python qua Nixpacks, không cần Dockerfile
- PORT được inject tự động qua env var
- Health check tự động restart container khi fail

---

## Part 4: API Security

### Exercise 4.1: API Key authentication

**API key được check ở đâu?**
Trong `app.py` qua FastAPI `Security` dependency — hàm `verify_api_key()` đọc header `X-API-Key` và so sánh với biến môi trường `AGENT_API_KEY`.

**Điều gì xảy ra nếu sai key?**
Server trả về `401 Unauthorized` với message rõ ràng.

**Làm sao rotate key?**
Chỉ cần thay giá trị `AGENT_API_KEY` trong environment variable rồi restart container — không cần sửa code.

**Kết quả test thực tế:**
```
# Không có key → 401
POST http://localhost:8000/ask (no header)
← {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Key đúng → 200
POST http://localhost:8000/ask (X-API-Key: my-secret-key)
← {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud..."}

# Key sai → 401
POST http://localhost:8000/ask (X-API-Key: wrong-key)
← {"detail":"Invalid API key."}
```

---

### Exercise 4.2: JWT authentication

**JWT flow hoạt động như sau:**

```
Client                          Server
  │                               │
  │  POST /auth/token             │
  │  {username, password}  ──────►│ authenticate_user()
  │                               │ create_token() → HS256 signed
  │◄────── {access_token: "eyJ..."│
  │                               │
  │  POST /ask                    │
  │  Authorization: Bearer eyJ...─►│ verify_token()
  │                               │ jwt.decode() → extract {sub, role}
  │◄────── {answer: "..."}        │
```

**Cấu trúc JWT payload:**
- `sub` — username (user identifier)
- `role` — `user` hoặc `admin`
- `iat` — thời điểm tạo token
- `exp` — hết hạn sau 60 phút

**Demo users có sẵn:**
| Username | Password | Role | Daily limit |
|---|---|---|---|
| student | demo123 | user | 50 req |
| teacher | teach456 | admin | 1000 req |

**Ưu điểm JWT so với API Key đơn giản:** Stateless — server không cần lưu session, token tự chứa thông tin user và quyền. Dễ scale vì mọi instance đều verify được chỉ với `JWT_SECRET`.

---

### Exercise 4.3: Rate limiting

**Algorithm được dùng: Sliding Window Counter**

Cách hoạt động:
- Mỗi user có 1 `deque` lưu timestamps của các request
- Mỗi request mới: xóa timestamps cũ hơn 60 giây, đếm còn lại
- Nếu số request trong window ≥ limit → raise 429

```python
# Loại timestamps ngoài window (sliding)
while window and window[0] < now - 60:
    window.popleft()

# Kiểm tra limit
if len(window) >= self.max_requests:
    raise HTTPException(429, ...)

window.append(now)  # ghi nhận request hiện tại
```

**Limit theo role:**
- `user` — 10 req/phút (`rate_limiter_user`)
- `admin` — 100 req/phút (`rate_limiter_admin`)

**Admin bypass limit:** Server check role từ JWT payload, nếu `role == "admin"` thì dùng `rate_limiter_admin` (100 req/phút) thay vì `rate_limiter_user` (10 req/phút).

**Response khi vượt limit (429):**
```json
{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": 10,
    "window_seconds": 60,
    "retry_after_seconds": 45
  }
}
```
Headers kèm theo: `X-RateLimit-Limit`, `X-RateLimit-Remaining: 0`, `Retry-After`.

---

### Exercise 4.4: Cost guard implementation

**Cách hoạt động của `CostGuard`:**

```python
# Trước khi gọi LLM
cost_guard.check_budget(user_id)       # raise 402 nếu vượt budget

# Sau khi gọi LLM xong
cost_guard.record_usage(user_id, input_tokens, output_tokens)
```

**2 lớp bảo vệ:**
1. **Per-user budget** — $1/ngày/user. Vượt → `402 Payment Required`
2. **Global budget** — $10/ngày toàn hệ thống. Vượt → `503 Service Unavailable`

**Logic tính cost (GPT-4o-mini pricing):**
```python
cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
```

**Reset:** Tự động reset mỗi ngày — mỗi record lưu kèm `day = "YYYY-MM-DD"`, khi ngày mới thì tạo record mới.

**Cảnh báo sớm:** Log warning khi user dùng ≥ 80% budget — kịp thời phát hiện trước khi bị block.

**Giải thích thiết kế:** Dùng `in-memory dict` cho demo, trong production thay bằng Redis để nhiều instance cùng track được. Key Redis: `budget:{user_id}:{YYYY-MM}` với TTL 32 ngày.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

**Sự khác biệt giữa `/health` và `/ready`:**

| | `/health` (Liveness) | `/ready` (Readiness) |
|---|---|---|
| Hỏi | "Process còn sống không?" | "Có sẵn sàng nhận request chưa?" |
| Dùng bởi | Platform → restart nếu fail | Load balancer → ngừng route traffic nếu 503 |
| Trả về 503 khi | Hiếm khi (process crash thì không còn respond được) | Đang startup, đang shutdown, Redis chưa connect |
| Timeout | Nên < 1 giây | Có thể check dependencies |

**Implementation trong `05-scaling-reliability/develop/app.py`:**

```python
@app.get("/health")
def health():
    # Kiểm tra memory, trả về uptime, version
    return {"status": "ok", "uptime_seconds": uptime, "checks": {"memory": ...}}

@app.get("/ready")
def ready():
    if not _is_ready:        # flag set bởi lifespan startup
        raise HTTPException(503, "Agent not ready")
    return {"ready": True, "in_flight_requests": _in_flight_requests}
```

**`_is_ready` flag hoạt động như thế nào:**
- Khởi động: `_is_ready = False` → `/ready` trả 503 → load balancer không route traffic vào
- Sau khi startup xong: `_is_ready = True` → `/ready` trả 200 → load balancer bắt đầu route
- Khi nhận SIGTERM: `_is_ready = False` → load balancer dừng route → drain in-flight requests → shutdown

---

### Exercise 5.2: Graceful shutdown

**Vấn đề với shutdown đột ngột:**
Nếu platform kill process ngay lập tức (SIGKILL), các request đang xử lý bị cắt ngang → client nhận lỗi, dữ liệu có thể corrupt.

**Cơ chế graceful shutdown trong code:**

```python
# 1. Middleware đếm request đang xử lý
@app.middleware("http")
async def track_requests(request, call_next):
    global _in_flight_requests
    _in_flight_requests += 1
    try:
        return await call_next(request)
    finally:
        _in_flight_requests -= 1

# 2. Lifespan shutdown: chờ hết in-flight requests
async def lifespan(app):
    yield
    _is_ready = False          # ngừng nhận request mới
    timeout, elapsed = 30, 0
    while _in_flight_requests > 0 and elapsed < timeout:
        time.sleep(1)
        elapsed += 1           # chờ tối đa 30 giây
```

**Luồng shutdown khi platform gửi SIGTERM:**
```
Platform gửi SIGTERM
    → uvicorn bắt signal, gọi lifespan shutdown
    → _is_ready = False (load balancer ngừng route vào instance này)
    → Chờ _in_flight_requests == 0 (tối đa 30s)
    → Đóng connections
    → Exit 0
```

---

### Exercise 5.3: Stateless design

**Anti-pattern — lưu state trong memory:**
```python
conversation_history = {}   # ❌ chỉ tồn tại trong instance này

@app.post("/ask")
def ask(user_id: str, question: str):
    history = conversation_history.get(user_id, [])
```

Khi scale ra 3 instances: request 1 đến Instance A (lưu history), request 2 đến Instance B (không có history) → mất context.

**Giải pháp — lưu state trong Redis:**
```python
def save_session(session_id: str, data: dict, ttl_seconds=3600):
    _redis.setex(f"session:{session_id}", ttl_seconds, json.dumps(data))

def load_session(session_id: str) -> dict:
    data = _redis.get(f"session:{session_id}")
    return json.loads(data) if data else {}
```

Mọi instance đều đọc/ghi cùng Redis → instance nào serve request cũng có đủ context. TTL 1 giờ tự động dọn session cũ.

**Response cho thấy bất kỳ instance nào cũng serve được:**
```json
{
  "session_id": "abc-123",
  "answer": "...",
  "served_by": "instance-a3f2b1",   ← mỗi request có thể khác instance
  "storage": "redis"
}
```

---

### Exercise 5.4: Load balancing

**Kiến trúc khi chạy `docker compose up --scale agent=3`:**

```
Client
  │
  ▼ :80
Nginx (round-robin)
  │
  ├──► Agent Instance 1 (:8000)
  ├──► Agent Instance 2 (:8000)  → tất cả đọc/ghi cùng Redis
  └──► Agent Instance 3 (:8000)
              │
           Redis
```

**Nginx phân tán traffic theo thuật toán round-robin** — request 1 → instance 1, request 2 → instance 2, request 3 → instance 3, request 4 → instance 1, ...

**Fault tolerance:** Nếu 1 instance die, Nginx detect qua health check và tự loại khỏi pool, traffic tự động chuyển sang 2 instance còn lại mà không gián đoạn.

---

### Exercise 5.5: Test stateless

**Script `test_stateless.py` kiểm tra:**
1. Tạo conversation với `session_id` qua nhiều request
2. Kill ngẫu nhiên 1 trong 3 agent instances
3. Tiếp tục gửi request với cùng `session_id`
4. Verify: conversation history vẫn còn nguyên vẹn

**Kết quả mong đợi:** Pass — vì history lưu trong Redis, không phụ thuộc vào instance nào đang sống.

**Kết quả nếu dùng in-memory (anti-pattern):** Fail — khi instance bị kill, toàn bộ `conversation_history` dict của instance đó mất theo.
