"""Production AI Agent — Part 6 Final Project."""
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# ── Structured logging: mỗi dòng là 1 JSON object ──
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.handlers = [_handler]
logger.setLevel(settings.log_level)
logger.propagate = False


def log(event: str, **fields):
    logger.info(event, extra={"extra_fields": fields})


# ── Graceful shutdown: uvicorn tự bắt SIGTERM, ngừng nhận request mới,
#    chờ request đang chạy xong rồi mới chạy phần sau `yield` ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("startup", environment=settings.environment, port=settings.port)
    yield
    log("shutdown", detail="SIGTERM received, in-flight requests drained")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error", extra={"extra_fields": {"path": request.url.path}})
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    log("request", method=request.method, path=request.url.path,
        status=response.status_code, ms=round((time.perf_counter() - start) * 1000, 1))
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Trả lỗi rõ ràng, không lộ stack trace
    return JSONResponse(status_code=422, content={"detail": "Invalid request body: "
                        "expected JSON {\"question\": \"...\"} (1-2000 chars)"})


@app.get("/health")
def health():
    """Liveness: process còn sống là 200, KHÔNG phụ thuộc Redis."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: chỉ nhận traffic khi Redis kết nối được."""
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"status": "not ready", "redis": "down"})
    return {"status": "ready", "redis": "up"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)        # 429
    check_budget()                   # 402
    answer = llm_ask(body.question)
    input_tokens = len(body.question.split()) * 2
    output_tokens = len(answer.split()) * 2
    cost = record_cost(input_tokens, output_tokens)
    log("ask", user_id=body.user_id, input_tokens=input_tokens,
        output_tokens=output_tokens, cost_usd=round(cost, 8))
    return {"question": body.question, "answer": answer}