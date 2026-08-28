from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message


class MainAdminFilter(BaseFilter):
    def __init__(self, admin_id: int) -> None:
        self.admin_id = admin_id

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return bool(event.from_user and event.from_user.id == self.admin_id)


class AdminAuditMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        import logging
        logger = logging.getLogger("lapbase.admin_audit")
        user = getattr(event, "from_user", None)
        if isinstance(event, Message):
            text = (event.text or "").strip()
            if text.startswith("/"):
                logger.info("admin_id=%s command=%s", getattr(user, "id", None), text[:300])
        elif isinstance(event, CallbackQuery):
            logger.info("admin_id=%s callback=%s", getattr(user, "id", None), (event.data or "")[:300])
        return await handler(event, data)
