"""
Economics Q&A Chatbot — Production
Kết hợp tất cả Day 12 concepts: 12-Factor, Docker, Security, Scaling & Reliability

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting (sliding window)
  ✅ Cost guard (daily budget)
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Stateless design — session history trong Redis
  ✅ Security headers
  ✅ CORS
"""
import time
import signal
import logging
import json
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import redis as redis_lib
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_and_record_cost, get_daily_cost
from utils.economics_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

_redis: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    try:
        get_redis().ping()
        logger.info(json.dumps({"event": "redis_connected"}))
    except Exception as e:
        logger.warning(json.dumps({"event": "redis_unavailable", "error": str(e)}))

    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))


# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Câu hỏi về kinh tế học")
    session_id: str | None = Field(None,
                                   description="Session ID để tiếp tục hội thoại. "
                                               "Bỏ trống để bắt đầu session mới.")


class ChatResponse(BaseModel):
    session_id: str
    question: str
    answer: str
    model: str
    timestamp: str


# ─────────────────────────────────────────────────────────
# Session helpers — Redis-backed, stateless design
# ─────────────────────────────────────────────────────────
SESSION_TTL = 3600       # 1 hour
MAX_HISTORY_TURNS = 10   # giữ tối đa 10 lượt để tránh context quá dài


def load_history(session_id: str) -> list[dict]:
    try:
        data = get_redis().get(f"session:{session_id}")
        return json.loads(data) if data else []
    except Exception:
        return []


def save_history(session_id: str, history: list[dict]) -> None:
    if len(history) > MAX_HISTORY_TURNS * 2:
        history = history[-(MAX_HISTORY_TURNS * 2):]
    try:
        get_redis().setex(f"session:{session_id}", SESSION_TTL, json.dumps(history))
    except Exception as e:
        logger.warning(json.dumps({"event": "session_save_failed", "error": str(e)}))


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "description": "Chatbot hỏi đáp kinh tế học — hỗ trợ tiếng Việt và tiếng Anh",
        "model": settings.llm_model,
        "endpoints": {
            "chat": "POST /chat (X-API-Key required) — multi-turn conversation",
            "health": "GET /health",
            "ready": "GET /ready",
            "metrics": "GET /metrics (X-API-Key required)",
            "docs": "GET /docs (development only)",
        },
    }


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(
    body: ChatRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Hỏi đáp kinh tế học với lịch sử hội thoại.

    **Authentication:** Header `X-API-Key: <your-key>`

    Gửi `session_id` từ response trước để tiếp tục cuộc hội thoại.
    Bỏ trống `session_id` để bắt đầu session mới.
    """
    check_rate_limit(_key[:8])

    session_id = body.session_id or str(uuid.uuid4())
    history = load_history(session_id)

    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(json.dumps({
        "event": "chat",
        "session_id": session_id[:8],
        "q_len": len(body.question),
        "history_turns": len(history) // 2,
        "client": str(request.client.host) if request.client else "unknown",
    }))

    answer = llm_ask(body.question, history)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(0, output_tokens)

    history.append({"role": "user", "content": body.question})
    history.append({"role": "assistant", "content": answer})
    save_history(session_id, history)

    return ChatResponse(
        session_id=session_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    try:
        get_redis().ping()
    except Exception:
        raise HTTPException(503, "Redis not available")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    daily_cost = get_daily_cost()
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": daily_cost,
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(daily_cost / settings.daily_budget_usd * 100, 1),
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))


signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
