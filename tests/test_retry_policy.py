from __future__ import annotations

from app.services.retry_policy import classify_retry


class _ApiError(Exception):
    pass


def _make_exception(module: str, name: str, status_code: int | None = None) -> Exception:
    cls = type(name, (_ApiError,), {"__module__": module})
    exc = cls("boom")
    if status_code is not None:
        exc.status_code = status_code
    return exc


def test_timeout_is_retryable():
    assert classify_retry(TimeoutError("timeout")).retryable is True


def test_telegram_bad_request_is_not_retryable():
    exc = _make_exception("aiogram.exceptions", "TelegramBadRequest")
    assert classify_retry(exc).retryable is False


def test_telegram_network_error_is_retryable():
    exc = _make_exception("aiogram.exceptions", "TelegramNetworkError")
    assert classify_retry(exc).retryable is True


def test_groq_429_is_retryable():
    exc = _make_exception("groq", "APIStatusError", 429)
    assert classify_retry(exc).retryable is True


def test_groq_400_is_not_retryable():
    exc = _make_exception("groq", "BadRequestError", 400)
    assert classify_retry(exc).retryable is False


def test_unknown_value_error_is_not_retryable():
    assert classify_retry(ValueError("bad input")).retryable is False
