"""Daily budget protection for LLM API calls."""
import time
from fastapi import HTTPException
from app.config import settings

_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

PRICE_PER_1K_INPUT = 0.00015   # GPT-4o-mini input
PRICE_PER_1K_OUTPUT = 0.0006   # GPT-4o-mini output


def check_and_record_cost(input_tokens: int, output_tokens: int) -> None:
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _cost_reset_day:
        _daily_cost = 0.0
        _cost_reset_day = today
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget of ${settings.daily_budget_usd} exhausted. Try tomorrow.",
        )
    _daily_cost += (input_tokens / 1000) * PRICE_PER_1K_INPUT + \
                   (output_tokens / 1000) * PRICE_PER_1K_OUTPUT


def get_daily_cost() -> float:
    return round(_daily_cost, 4)
