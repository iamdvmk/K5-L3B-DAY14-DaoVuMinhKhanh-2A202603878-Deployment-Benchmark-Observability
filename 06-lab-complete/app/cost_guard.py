"""Cost guard (tiêu chí 8) — cộng dồn chi phí theo ngày trong Redis."""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _day_key() -> str:
    return "cost:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")


def current_spend() -> float:
    return float(r.get(_day_key()) or 0.0)


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → 402."""
    spent = current_spend()
    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget exceeded (${spent:.6f} / ${settings.daily_budget_usd})",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng ngày, trả về chi phí request."""
    cost = input_tokens / 1000 * PRICE_INPUT_PER_1K + output_tokens / 1000 * PRICE_OUTPUT_PER_1K
    key = _day_key()
    pipe = r.pipeline()
    pipe.incrbyfloat(key, cost)
    pipe.expire(key, 2 * 24 * 3600)
    pipe.execute()
    return cost