# Kiến Thức: Deploy AI Agent to Production

> Tổng hợp từ lab AICB-P1 · VinUniversity 2026 — Day 12

---

## Part 1 — Localhost vs Production

### Vấn đề cốt lõi: "It works on my machine"

Code chạy tốt trên laptop nhưng fail khi deploy vì:
- Hardcode secrets trực tiếp trong code
- Debug mode bật trong production
- Port cố định, không linh hoạt
- Không có health check để platform biết app còn sống không
- Không xử lý graceful shutdown — request đang chạy bị drop khi tắt

### Giải pháp: 12-Factor App

**Config từ environment variables:**
```python
# Sai
API_KEY = "sk-abc123"
DEBUG = True

# Đúng
import os
API_KEY = os.getenv("API_KEY")
DEBUG = os.getenv("ENVIRONMENT") != "production"
```

**Pydantic Settings (cách tốt nhất):**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    port: int = 8000
    agent_api_key: str
    redis_url: str = "redis://localhost:6379/0"
    environment: str = "production"

    class Config:
        env_file = ".env"

settings = Settings()
```

**Logging chuẩn production (JSON, không dùng print):**
```python
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
)
logger = logging.getLogger(__name__)

logger.info("Request received")   # thay vì print()
```

**Quy tắc file config:**
```
.env.example   ← commit (template, không có giá trị thật)
.env           ← KHÔNG commit (thêm vào .gitignore)
```

### So sánh Basic vs Production

| Feature | Basic (anti-pattern) | Production |
|---|---|---|
| Config | Hardcode trong code | Env vars |
| Logging | `print()` | JSON structured |
| Health check | Không có | `/health` endpoint |
| Shutdown | Đột ngột, drop requests | Graceful — chờ xong rồi tắt |
| Debug mode | Luôn bật | Tắt trong production |

---

## Part 2 — Docker Containerization

### Tại sao cần Docker?

Không phải ai cũng có cùng Python version, OS, hay dependencies. Docker đóng gói app + toàn bộ dependencies vào một container — chạy ở đâu cũng giống nhau.

### Single-stage vs Multi-stage Build

**Single-stage (~800MB, không nên dùng):**
```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

**Multi-stage (~160MB, dùng trong production):**
```dockerfile
# Stage 1: Build — cài dependencies
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime — chỉ copy artifacts cần thiết
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

# Chạy non-root để tăng bảo mật
RUN useradd -m appuser && chown -R appuser /app
USER appuser

ENV PATH=/root/.local/bin:$PATH
CMD ["python", "app.py"]
```

**Tại sao copy `requirements.txt` trước COPY toàn bộ code?**
Docker cache từng layer. Nếu code thay đổi nhưng requirements không đổi, Docker dùng cache layer `pip install` — build nhanh hơn nhiều.

### .dockerignore (bắt buộc có)
```
__pycache__/
*.pyc
.env
.git
*.md
tests/
```

### Docker Compose Stack
```yaml
services:
  agent:
    build: .
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy   # chờ Redis healthy mới start

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - agent
```

### Lệnh debug container
```bash
docker logs <container_id>           # xem logs
docker exec -it <container_id> sh    # vào trong container
docker images | grep my-agent        # so sánh image size
```

---

## Part 3 — Cloud Deployment

### Tại sao phải deploy lên cloud?

Laptop không chạy 24/7, không có public IP, không tự restart khi crash.

### So sánh các platform

| Platform | Độ khó | Free tier | Phù hợp |
|---|---|---|---|
| Railway | Dễ nhất | $5 credit | Prototype, học tập |
| Render | Trung bình | 750h/tháng | Side project |
| GCP Cloud Run | Phức tạp | 2M requests/tháng | Production thật |

### Railway (nhanh nhất)
```bash
npm i -g @railway/cli
railway login
railway init
railway variables set AGENT_API_KEY=secret
railway variables set REDIS_URL=redis://...
railway up
railway domain   # lấy public URL
```

```toml
# railway.toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python app.py"
healthcheckPath = "/health"
restartPolicyType = "on_failure"
```

### Render
```yaml
# render.yaml
services:
  - type: web
    name: ai-agent
    runtime: docker
    healthCheckPath: /health
    envVars:
      - key: AGENT_API_KEY
        generateValue: true   # Render tự tạo random secret
```

### Nguyên tắc khi deploy

1. **Không bao giờ** push `.env` lên GitHub
2. Set env vars **trực tiếp trên platform** (dashboard hoặc CLI)
3. Luôn cấu hình `healthcheckPath` để platform biết khi nào restart
4. Xem logs từ dashboard khi có lỗi

---

## Part 4 — API Security

### Vấn đề: Public URL = Ai cũng gọi được = Hết tiền

3 lớp bảo vệ bắt buộc, theo đúng thứ tự:

```
Request → [Auth] → [Rate Limit] → [Cost Guard] → Business Logic
```

### Lớp 1: Authentication (API Key)

```python
# app/auth.py
from fastapi import Header, HTTPException
from .config import settings

def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
```

Test:
```bash
curl http://localhost/ask                             # → 401
curl -H "X-API-Key: wrong" http://localhost/ask      # → 401
curl -H "X-API-Key: correct" http://localhost/ask    # → 200
```

### Lớp 2: Rate Limiting (Sliding Window)

```python
# app/rate_limiter.py
import redis, time
from fastapi import HTTPException

r = redis.from_url(settings.redis_url)
RATE_LIMIT = 10  # requests per minute

def check_rate_limit(user_id: str):
    key = f"rate:{user_id}"
    now = time.time()
    window = 60

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)  # xóa entries cũ
    pipe.zadd(key, {str(now): now})              # thêm request mới
    pipe.zcard(key)                              # đếm trong window
    pipe.expire(key, window)
    results = pipe.execute()

    if results[2] > RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": "60"},
            detail="Rate limit exceeded"
        )
```

### Lớp 3: Cost Guard (Budget tháng)

```python
# app/cost_guard.py
from datetime import datetime

MONTHLY_BUDGET_USD = 10.0

def check_budget(user_id: str, estimated_cost: float = 0.001):
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"

    current = float(r.get(key) or 0)
    if current + estimated_cost > MONTHLY_BUDGET_USD:
        raise HTTPException(402, "Monthly budget exceeded")

    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # reset sau 32 ngày
```

### Wiring vào FastAPI

```python
@app.post("/ask")
def ask(
    body: ChatRequest,
    user_id: str = Depends(verify_api_key),
    _rl: None = Depends(check_rate_limit),
    _bg: None = Depends(check_budget),
):
    # Business logic ở đây
    ...
```

### HTTP Status Codes cần nhớ

| Code | Ý nghĩa | Khi nào trả về |
|---|---|---|
| 401 | Unauthorized | Không có / sai API key |
| 429 | Too Many Requests | Vượt rate limit |
| 402 | Payment Required | Vượt budget tháng |
| 503 | Service Unavailable | App chưa ready |

---

## Part 5 — Scaling & Reliability

### Vấn đề: 1 instance không đủ

Khi có nhiều users đồng thời:
- 1 instance → bottleneck, single point of failure
- Scale ra nhiều instances → nhưng nếu state trong memory, mỗi instance có data khác nhau → **bug**

### Health Checks (bắt buộc)

Hai endpoints khác nhau, không được lẫn lộn:

```python
@app.get("/health")   # LIVENESS — "Process còn sống không?"
def health():
    # Trả 200 nếu process OK, dù dependencies có lỗi
    # Platform dùng để quyết định có restart container không
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1)
    }

@app.get("/ready")    # READINESS — "Sẵn sàng nhận traffic chưa?"
def ready():
    # Trả 503 khi đang khởi động hoặc dependencies lỗi
    # Load balancer dùng để quyết định có route traffic vào không
    try:
        r.ping()  # check Redis
        return {"ready": True}
    except Exception:
        raise HTTPException(503, "Redis not available")
```

**Tại sao cần 2 endpoints riêng?**
- Liveness fail → restart container
- Readiness fail → ngừng gửi traffic, nhưng KHÔNG restart

### Graceful Shutdown

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")
    yield
    # Shutdown — uvicorn chờ requests in-flight xong mới thoát
    logger.info("Shutting down gracefully...")

app = FastAPI(lifespan=lifespan)

# Uvicorn xử lý SIGTERM tự động
uvicorn.run(app, timeout_graceful_shutdown=30)
```

Khi platform muốn stop container:
1. Gửi SIGTERM
2. Uvicorn ngừng nhận request mới
3. Chờ tối đa 30s cho requests đang chạy xong
4. Thoát sạch

### Stateless Design (quan trọng nhất khi scale)

```python
# SAI — state trong memory
conversation_history = {}   # instance 1 có, instance 2 không có

@app.post("/chat")
def chat(user_id: str, question: str):
    history = conversation_history.get(user_id, [])  # bug khi scale!


# ĐÚNG — state trong Redis
@app.post("/chat")
def chat(body: ChatRequest):
    session_id = body.session_id or str(uuid.uuid4())

    # Load từ Redis — bất kỳ instance nào cũng đọc được
    data = r.get(f"session:{session_id}")
    session = json.loads(data) if data else {"history": []}

    session["history"].append({"role": "user", "content": body.question})
    answer = ask(body.question)
    session["history"].append({"role": "assistant", "content": answer})

    # Lưu lại Redis với TTL 1 giờ
    r.setex(f"session:{session_id}", 3600, json.dumps(session))

    return {"session_id": session_id, "answer": answer}
```

### Load Balancing với Nginx

```nginx
upstream agent_pool {
    server agent:8000;   # Docker Compose tự resolve nhiều containers cùng tên
}

server {
    listen 80;
    location / {
        proxy_pass http://agent_pool;
        proxy_set_header Host $host;
    }
}
```

```bash
# Scale lên 3 instances — Nginx tự phân tán traffic
docker compose up --scale agent=3
```

Kết quả: mỗi request được xử lý bởi instance khác nhau, nhưng session vẫn liên tục vì Redis là shared state.

---

## Tổng Hợp: Production Readiness Checklist

```
□ Step 1 — Config
  □ Không hardcode secret nào
  □ Tất cả config từ env vars (pydantic-settings)
  □ .env trong .gitignore, .env.example được commit
  □ JSON structured logging

□ Step 2 — Docker
  □ Multi-stage build (image < 200MB)
  □ .dockerignore tồn tại
  □ Container chạy non-root user
  □ docker-compose.yml với healthcheck

□ Step 3 — Deployment
  □ Deploy lên ít nhất 1 cloud platform
  □ Public URL hoạt động
  □ Env vars set trên platform, không trong code
  □ Health check path được cấu hình

□ Step 4 — Security
  □ 401 khi không có / sai API key
  □ 429 khi vượt rate limit (có Retry-After header)
  □ 402 khi vượt budget tháng
  □ Middleware order: Auth → Rate Limit → Cost → Logic

□ Step 5 — Scale & Reliability
  □ /health endpoint (liveness)
  □ /ready endpoint (readiness, trả 503 khi chưa sẵn sàng)
  □ Graceful shutdown (timeout_graceful_shutdown=30)
  □ State trong Redis, không trong memory
  □ Load balancer (Nginx) + chạy 3+ instances
```

---

## Kiến Trúc Production Hoàn Chỉnh

```
Client
  │
  ▼
Nginx :80  (load balancer, SSL termination)
  │
  ├── Agent Instance 1 :8000
  ├── Agent Instance 2 :8000
  └── Agent Instance 3 :8000
           │
           ▼
         Redis :6379
    (session, rate limit, cost tracking)
```

Mỗi component có vai trò rõ ràng:
- **Nginx**: nhận traffic từ ngoài, phân tán vào các agent, không biết business logic
- **Agent**: xử lý request, không giữ state, scale ngang dễ dàng
- **Redis**: single source of truth cho mọi state — session, rate limit window, budget

---

## Lỗi Thường Gặp

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `422 Unprocessable Content` | Sai format request (query param vs body) | Đọc kỹ signature của endpoint |
| `401 Unauthorized` | Thiếu hoặc sai header `X-API-Key` | Thêm `-H "X-API-Key: ..."` |
| `503 Service Unavailable` | App chưa ready (Redis chưa connect) | Chờ dependencies khởi động |
| `env file not found` | docker-compose yêu cầu file `.env.local` không tồn tại | Tạo file rỗng: `echo. > .env.local` |
| Container exit ngay | Build thành công nhưng runtime error | `docker logs <id>` để xem lỗi |
| Session mất khi scale | State trong memory thay vì Redis | Chuyển sang Redis-backed session |
