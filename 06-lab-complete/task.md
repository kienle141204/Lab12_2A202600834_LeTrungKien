# Task List — 06 Lab Complete

Capstone project: chạy và deploy production agent hoàn chỉnh.

---

## Task 1 — Setup môi trường

- [ ] Copy file cấu hình:
  ```powershell
  cp .env.example .env
  ```
- [ ] Mở `.env`, thay giá trị `AGENT_API_KEY` thành một key tự chọn (ví dụ: `my-prod-key-2024`)
- [ ] Copy `utils/mock_llm.py` vào thư mục `06-lab-complete/` (vì `main.py` import từ đó):
  ```powershell
  mkdir utils
  cp ..\utils\mock_llm.py utils\mock_llm.py
  ```

---

## Task 2 — Chạy local với Docker Compose

- [ ] Build và khởi động stack:
  ```powershell
  docker compose up --build
  ```
- [ ] Kiểm tra agent + redis đang chạy:
  ```powershell
  docker compose ps
  ```

---

## Task 3 — Test các endpoints

Mở terminal thứ 2, test lần lượt:

- [ ] Health check (liveness probe):
  ```powershell
  curl http://localhost/health
  # Expected: {"status":"ok", "uptime_seconds":...}
  ```
- [ ] Readiness probe:
  ```powershell
  curl http://localhost/ready
  # Expected: {"ready":true}
  ```
- [ ] Gọi agent KHÔNG có API key (phải fail):
  ```powershell
  curl -X POST http://localhost/ask `
    -H "Content-Type: application/json" `
    -d '{"question": "Hello"}'
  # Expected: 401 Unauthorized
  ```
- [ ] Gọi agent CÓ API key (phải thành công):
  ```powershell
  curl -X POST http://localhost/ask `
    -H "X-API-Key: my-prod-key-2024" `
    -H "Content-Type: application/json" `
    -d '{"question": "What is deployment?"}'
  # Expected: 200 với answer
  ```
- [ ] Test rate limit — gửi 25 request liên tiếp, từ request 21 trở đi phải nhận 429:
  ```powershell
  for ($i=1; $i -le 25; $i++) {
    curl -s -X POST http://localhost/ask `
      -H "X-API-Key: my-prod-key-2024" `
      -H "Content-Type: application/json" `
      -d '{"question": "test"}' | Select-String "status|detail"
  }
  ```
- [ ] Xem metrics (cũng cần API key):
  ```powershell
  curl -H "X-API-Key: my-prod-key-2024" http://localhost/metrics
  ```

---

## Task 4 — Chạy Production Readiness Checker

- [ ] Chạy script kiểm tra từ thư mục `06-lab-complete/`:
  ```powershell
  python check_production_ready.py
  ```
- [ ] Mục tiêu: đạt **100%** (20/20 checks passed)
- [ ] Nếu có ❌, sửa theo hướng dẫn script báo

---

## Task 5 — Deploy lên cloud

Chọn **một** trong hai:

### Option A: Railway
- [ ] Đã có Railway account và đã thêm thẻ thanh toán
- [ ] Chạy từ thư mục `06-lab-complete/`:
  ```powershell
  railway login
  railway init
  railway variables set AGENT_API_KEY=my-prod-key-2024
  railway up
  railway domain
  ```
- [ ] Nhận public URL, test endpoint `/health` và `/ask`

### Option B: Render (không cần thẻ)
- [ ] Push repo lên GitHub (nếu chưa có)
- [ ] Vào [render.com](https://render.com) → New → Blueprint
- [ ] Connect repo → Render tự đọc `render.yaml`
- [ ] Set environment variable `AGENT_API_KEY` trên dashboard
- [ ] Deploy → lấy URL và test

---

## Task 6 — Verify trên cloud

Sau khi có public URL:

- [ ] Test health endpoint trên cloud:
  ```powershell
  curl https://<your-url>/health
  ```
- [ ] Test ask endpoint trên cloud với API key:
  ```powershell
  curl -X POST https://<your-url>/ask `
    -H "X-API-Key: my-prod-key-2024" `
    -H "Content-Type: application/json" `
    -d '{"question": "Am I production ready?"}'
  ```
- [ ] Ghi lại public URL để nộp bài

---

## Checklist nộp bài

Theo yêu cầu `DAY12_DELIVERY_CHECKLIST.md`:

- [ ] Dockerfile multi-stage, image < 500 MB
- [ ] docker-compose.yml chạy được (agent + redis)
- [ ] `/health` và `/ready` trả về đúng
- [ ] API Key authentication hoạt động (401 khi thiếu key)
- [ ] Rate limiting hoạt động (429 khi vượt giới hạn)
- [ ] `check_production_ready.py` đạt 100%
- [ ] Public URL từ Railway hoặc Render
- [ ] Không commit file `.env` lên Git

---

## Ghi chú

| File | Mục đích |
|---|---|
| `app/main.py` | Entry point — toàn bộ logic (auth, rate limit, cost guard đã inline) |
| `app/config.py` | Đọc config từ env vars (12-Factor) |
| `utils/mock_llm.py` | Mock LLM — không cần OpenAI API key |
| `check_production_ready.py` | Tự động kiểm tra 20 điều kiện production |
| `.env.example` | Template — copy thành `.env` và điền giá trị |
