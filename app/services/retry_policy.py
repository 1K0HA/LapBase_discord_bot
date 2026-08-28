from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Решение о повторной попытке без привязки worker к конкретной SDK."""

    retryable: bool
    reason: str


def _status_code(exc: BaseException) -> int | None:
    value = getattr(exc, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status", None)
    if isinstance(value, int):
        return value
    return None


def classify_retry(exc: BaseException) -> RetryDecision:
    """Повторяет только временные сетевые/серверные ошибки и rate limit."""
    if isinstance(exc, asyncio.CancelledError):
        return RetryDecision(False, "операция отменена")
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return RetryDecision(True, "временная сетевая ошибка")

    module = type(exc).__module__
    name = type(exc).__name__
    status = _status_code(exc)

    if module.startswith("groq"):
        if name in {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"}:
            return RetryDecision(True, f"временная ошибка Groq: {name}")
        if status in {408, 409, 429} or (status is not None and status >= 500):
            return RetryDecision(True, f"временный HTTP {status} от Groq")
        return RetryDecision(False, f"неповторяемая ошибка Groq: {name}")

    if module.startswith("aiogram"):
        if name in {"TelegramNetworkError", "TelegramRetryAfter", "TelegramServerError"}:
            return RetryDecision(True, f"временная ошибка Telegram: {name}")
        return RetryDecision(False, f"неповторяемая ошибка Telegram: {name}")

    if module.startswith("discord"):
        if status == 429 or (status is not None and status >= 500):
            return RetryDecision(True, f"временный HTTP {status} от Discord")
        if name in {"GatewayNotFound", "ConnectionClosed"}:
            return RetryDecision(True, f"временная ошибка Discord: {name}")
        return RetryDecision(False, f"неповторяемая ошибка Discord: {name}")

    if module.startswith("asyncpg"):
        transient_tokens = ("Connection", "CannotConnect", "TooManyConnections", "PostgresConnection")
        if any(token in name for token in transient_tokens):
            return RetryDecision(True, f"временная ошибка PostgreSQL: {name}")
        return RetryDecision(False, f"неповторяемая ошибка PostgreSQL: {name}")

    if isinstance(exc, OSError):
        return RetryDecision(True, "временная ошибка ввода-вывода")

    return RetryDecision(False, f"ошибка логики/валидации: {name}")
