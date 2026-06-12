# Deployment Information

## Public URL
https://lab11-production-c560.up.railway.app

## Platform
Railway

## Test Commands

### Health Check
```bash
curl https://lab11-production-c560.up.railway.app/health
# Expected: {"status":"ok","uptime_seconds":...,"platform":"Railway","timestamp":"..."}
```

### Authentication required (no key)
```bash
curl -X POST https://lab11-production-c560.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401 {"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

### API Test (with authentication)
```bash
curl -X POST https://lab11-production-c560.up.railway.app/ask \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Am I on the cloud?"}'
# Expected: 200 {"question":"...","answer":"...","platform":"Railway"}
```

## Environment Variables Set
- `PORT` — injected automatically by Railway
- `AGENT_API_KEY` — API key for authentication
- `ENVIRONMENT` — production
- `REDIS_URL` — Redis connection string (if using Redis add-on)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
