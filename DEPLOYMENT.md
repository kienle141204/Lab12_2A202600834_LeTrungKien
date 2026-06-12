# Deployment Information

## Public URL
https://economics-chatbot-production-9bb8.up.railway.app

## Platform
Railway

## Architecture
- **App service**: FastAPI + Uvicorn (economics-chatbot)
- **Redis service**: Session storage + rate limiting
- **LLM**: OpenAI GPT-4o-mini
- **Auth**: API Key (`X-API-Key` header)

## Test Commands

### Health Check (liveness probe)
```bash
curl https://economics-chatbot-production-9bb8.up.railway.app/health
# Expected: {"status":"ok","environment":"production","uptime_seconds":...}
```

### Readiness Probe (checks Redis)
```bash
curl https://economics-chatbot-production-9bb8.up.railway.app/ready
# Expected: {"ready":true}
```

### Authentication required (no key → 401)
```bash
curl -X POST https://economics-chatbot-production-9bb8.up.railway.app/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'
# Expected: 401 {"detail":"Invalid or missing API key..."}
```

### Chat — Q&A kinh tế học
```bash
curl -X POST https://economics-chatbot-production-9bb8.up.railway.app/chat \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"question": "GDP la gi?"}'
# Expected: 200 {"session_id":"...","answer":"...","model":"gpt-4o-mini",...}
```

### Multi-turn conversation (dùng session_id)
```bash
curl -X POST https://economics-chatbot-production-9bb8.up.railway.app/chat \
  -H "X-API-Key: dev-key-change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"question": "vi du cu the?", "session_id": "<session_id_tu_response_truoc>"}'
# Expected: 200 — chatbot nhớ context từ câu hỏi trước
```

### Metrics (protected)
```bash
curl https://economics-chatbot-production-9bb8.up.railway.app/metrics \
  -H "X-API-Key: dev-key-change-me-in-production"
# Expected: {"uptime_seconds":...,"daily_cost_usd":...,"budget_used_pct":...}
```

## Environment Variables Set

| Variable | Value | Purpose |
|---|---|---|
| `PORT` | auto | Injected by Railway |
| `OPENAI_API_KEY` | sk-proj-... | OpenAI API access |
| `AGENT_API_KEY` | dev-key-change-me-in-production | API authentication |
| `JWT_SECRET` | dev-jwt-secret-... | JWT signing |
| `ENVIRONMENT` | production | App mode |
| `LLM_MODEL` | gpt-4o-mini | OpenAI model |
| `REDIS_URL` | redis://default:...@redis.railway.internal:6379 | Internal Redis (Railway) |

## Production Readiness Checklist

- [x] 12-Factor config — all config from environment variables
- [x] Structured JSON logging
- [x] Multi-stage Docker build (non-root user)
- [x] API Key authentication (`X-API-Key` header)
- [x] Rate limiting — sliding window, 10 req/min
- [x] Cost guard — daily budget $5.00 USD
- [x] Input validation — Pydantic, max 2000 chars
- [x] `/health` liveness probe → 200
- [x] `/ready` readiness probe → 200 (Redis connected)
- [x] Graceful shutdown — SIGTERM handler
- [x] Stateless design — Redis-backed session storage
- [x] Security headers — `X-Content-Type-Options`, `X-Frame-Options`
- [x] CORS configured
- [x] Deployed to Railway cloud

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
