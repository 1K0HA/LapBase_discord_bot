from __future__ import annotations

import html
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.config import Config
from app.runtime import RuntimeManager
from app.services.backup import BackupService
from app.services.logs import tail_lines
from app.storage.repositories import Repository
from app.telegram.filters import AdminAuditMiddleware, MainAdminFilter

logger = logging.getLogger(__name__)

USER_START_RU = (
    "LapBase Bot\n\n"
    "У этого бота нет отдельного функционала для обычных пользователей.\n"
    "Весь пользовательский функционал доступен только через LapBaseApp."
)
USER_START_EN = (
    "LapBase Bot\n\n"
    "This bot has no separate functionality for regular users.\n"
    "All user-facing features are available only through LapBaseApp."
)

ADMIN_HELP = """Команды LapBase:\n/start — запустить ядро / панель\n/stop — остановить ядро\n/restart — перезапустить\n/pause /resume — очередь\n/status /health /stats\n/queue /failed\n/retry <discord_id>\n/delete <discord_id>\n/republish <discord_id>\n/sync\n/logs [N]\n/backup\n/post — ручная публикация\n/cancel — отмена\n/help"""


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="admin_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel"),
            ]
        ]
    )


def app_keyboard(url: str | None) -> InlineKeyboardMarkup | None:
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть LapBaseApp / Open LapBaseApp", web_app=WebAppInfo(url=url))]
        ]
    )


def create_admin_router(config: Config) -> Router:
    root = Router(name="telegram_root")
    admin = Router(name="telegram_admin")
    admin.message.filter(MainAdminFilter(config.telegram_admin_user_id))
    admin.callback_query.filter(MainAdminFilter(config.telegram_admin_user_id))
    admin.message.middleware(AdminAuditMiddleware())
    admin.callback_query.middleware(AdminAuditMiddleware())

    @root.message(CommandStart())
    async def public_start(message: Message, runtime: RuntimeManager, state: FSMContext):
        await state.clear()
        if message.from_user and message.from_user.id == config.telegram_admin_user_id:
            logger.info("admin_id=%s command=/start", message.from_user.id)
            mode = await runtime.repo.get_mode()
            if mode == "stopped" or not runtime.discord_connected:
                await runtime.start_from_admin()
                mode = "running"
            await message.answer(f"LapBase Admin\nРежим: {mode}\n\n{ADMIN_HELP}")
            return
        await message.answer(
            USER_START_RU + "\n\n==========\n\n" + USER_START_EN,
            reply_markup=app_keyboard(config.lapbase_app_url),
        )

    async def request_confirmation(message: Message, repo: Repository, action: str, payload: dict, text: str):
        await repo.set_confirmation(config.telegram_admin_user_id, action, payload)
        await message.answer(text, reply_markup=confirm_keyboard())

    @admin.message(Command("help"))
    async def help_cmd(message: Message):
        await message.answer(ADMIN_HELP)

    @admin.message(Command("status"))
    async def status_cmd(message: Message, repo: Repository):
        counts = await repo.queue_counts()
        mode = await repo.get_mode()
        await message.answer(
            f"Режим: {mode}\n"
            f"queued: {counts.get('queued', 0)}\n"
            f"processing: {counts.get('processing', 0)}\n"
            f"retrying: {counts.get('retrying', 0)}\n"
            f"failed: {counts.get('failed', 0)}\n"
            f"published: {counts.get('published', 0)}"
        )

    @admin.message(Command("health"))
    async def health_cmd(message: Message, runtime: RuntimeManager, translator, db, repo: Repository, bot: Bot):
        tg_ok = True
        try:
            await bot.get_me()
        except Exception:
            tg_ok = False
        db_ok = await db.health()
        groq_ok = await translator.health()
        mode = await repo.get_mode()
        last = await repo.last_success()
        last_text = "нет"
        if last:
            last_text = f"{last['discord_message_id']} @ {last['published_at']}"
        await message.answer(
            "LapBase Health\n"
            f"Discord: {'OK' if runtime.discord_connected else 'OFF'}\n"
            f"Telegram: {'OK' if tg_ok else 'ERROR'}\n"
            f"Groq: {'OK' if groq_ok else 'ERROR'}\n"
            f"Supabase: {'OK' if db_ok else 'ERROR'}\n"
            f"Mode: {mode}\n"
            f"Последний успешный: {last_text}"
        )

    @admin.message(Command("queue"))
    async def queue_cmd(message: Message, repo: Repository):
        counts = await repo.queue_counts()
        waiting = counts.get("queued", 0) + counts.get("processing", 0) + counts.get("retrying", 0)
        await message.answer(f"В очереди/обработке: {waiting}\n{counts}")

    @admin.message(Command("failed"))
    async def failed_cmd(message: Message, repo: Repository):
        rows = await repo.failed(10)
        if not rows:
            await message.answer("failed записей нет.")
            return
        parts = []
        for row in rows:
            err = (row.get("last_error") or "")[:180]
            parts.append(f"{row['discord_message_id']} | retries={row['retry_count']} | {err}")
        await message.answer("Последние failed:\n" + "\n".join(parts))

    @admin.message(Command("stats"))
    async def stats_cmd(message: Message, repo: Repository):
        stats = await repo.stats_24h()
        await message.answer(
            "Статистика 24ч:\n"
            f"received: {stats.get('received', 0)}\n"
            f"published: {stats.get('published', 0)}\n"
            f"failed: {stats.get('failed', 0)}\n"
            f"retry: {stats.get('retry', 0)}\n"
            f"edited: {stats.get('edited', 0)}\n"
            f"deleted: {stats.get('deleted', 0)}"
        )

    @admin.message(Command("pause"))
    async def pause_cmd(message: Message, runtime: RuntimeManager):
        await runtime.pause()
        await message.answer("⏸ Очередь приостановлена. Discord и админ-бот остаются онлайн.")

    @admin.message(Command("resume"))
    async def resume_cmd(message: Message, runtime: RuntimeManager):
        await runtime.resume()
        await message.answer("▶️ Очередь продолжена.")

    @admin.message(Command("stop"))
    async def stop_cmd(message: Message, repo: Repository):
        await request_confirmation(message, repo, "stop", {}, "Остановить рабочее ядро LapBase?")

    @admin.message(Command("restart"))
    async def restart_cmd(message: Message, repo: Repository):
        await request_confirmation(message, repo, "restart", {}, "Перезапустить рабочее ядро LapBase?")

    @admin.message(Command("retry"))
    async def retry_cmd(message: Message, command: CommandObject, repo: Repository, runtime: RuntimeManager):
        try:
            message_id = int((command.args or "").strip())
        except ValueError:
            await message.answer("Использование: /retry <discord_message_id>")
            return
        ok = await repo.enqueue_retry(message_id)
        if ok:
            runtime.wake_worker()
        await message.answer("Поставлено в очередь." if ok else "Нужная failed-запись не найдена.")

    @admin.message(Command("delete"))
    async def delete_cmd(message: Message, command: CommandObject, repo: Repository):
        try:
            message_id = int((command.args or "").strip())
        except ValueError:
            await message.answer("Использование: /delete <discord_message_id>")
            return
        if not await repo.get_post(message_id):
            await message.answer("Discord ID не найден в Supabase.")
            return
        await request_confirmation(
            message, repo, "delete", {"message_id": message_id}, f"Удалить Telegram-публикацию для Discord ID {message_id}?"
        )

    @admin.message(Command("republish"))
    async def republish_cmd(message: Message, command: CommandObject, repo: Repository):
        try:
            message_id = int((command.args or "").strip())
        except ValueError:
            await message.answer("Использование: /republish <discord_message_id>")
            return
        if not await repo.get_post(message_id):
            await message.answer("Discord ID не найден в Supabase.")
            return
        await request_confirmation(
            message, repo, "republish", {"message_id": message_id}, f"Повторно обработать Discord ID {message_id}?"
        )

    @admin.message(Command("sync"))
    async def sync_cmd(message: Message, runtime: RuntimeManager):
        try:
            count = await runtime.sync_now()
            await message.answer(f"Sync завершён. Найдено пропущенных: {count}")
        except Exception as exc:
            await message.answer(f"Sync error: {type(exc).__name__}: {exc}")

    @admin.message(Command("logs"))
    async def logs_cmd(message: Message, command: CommandObject):
        raw = (command.args or "").strip()
        try:
            n = int(raw) if raw else 50
        except ValueError:
            await message.answer("Использование: /logs [N], максимум 200")
            return
        n = max(1, min(n, 200))
        lines = tail_lines(config.logs_dir / "lapbase.log", n)
        text = "".join(lines) or "Лог пуст."
        chunks = [text[i : i + 3500] for i in range(0, len(text), 3500)]
        for chunk in chunks:
            await message.answer(f"<pre>{html.escape(chunk)}</pre>", parse_mode="HTML")

    @admin.message(Command("backup"))
    async def backup_cmd(message: Message, backup_service: BackupService):
        try:
            path = await backup_service.create_backup()
            await message.answer(f"✅ Backup создан: {path.name}")
        except Exception as exc:
            await message.answer(f"❌ Backup error: {type(exc).__name__}: {exc}")

    @admin.message(Command("cleardb"))
    async def cleardb_cmd(message: Message, repo: Repository):
        await request_confirmation(
            message,
            repo,
            "cleardb",
            {},
            "ПОЛНОСТЬЮ очистить данные LapBase в Supabase?\n\n"
            "Будут удалены:\n"
            "• история опубликованных постов\n"
            "• связи Discord → Telegram\n"
            "• статистика\n"
            "• подтверждения\n"
            "• системное состояние\n\n"
            "Схема таблиц останется. Старые Telegram-посты физически НЕ удаляются из канала, "
            "но LapBase забудет их ID.",
        )

    @admin.message(Command("cancel"))
    async def cancel_cmd(message: Message, state: FSMContext, repo: Repository):
        had_state = await state.get_state() is not None
        await state.clear()
        pending = await repo.get_confirmation(config.telegram_admin_user_id)
        await repo.clear_confirmation(config.telegram_admin_user_id)
        if had_state or pending:
            await message.answer("Действие отменено.")
        else:
            await message.answer("Сейчас нет активного действия.")

    @admin.callback_query(F.data == "admin_cancel")
    async def cancel_callback(callback: CallbackQuery, repo: Repository):
        await repo.clear_confirmation(config.telegram_admin_user_id)
        await callback.answer("Отменено")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

    @admin.callback_query(F.data == "admin_confirm")
    async def confirm_callback(callback: CallbackQuery, repo: Repository, runtime: RuntimeManager):
        pending = await repo.get_confirmation(config.telegram_admin_user_id)
        if not pending:
            await callback.answer("Нет ожидающего действия", show_alert=True)
            return
        action = pending["action"]
        payload = pending["payload"] or {}
        await repo.clear_confirmation(config.telegram_admin_user_id)
        try:
            if action == "stop":
                await runtime.stop_core()
                text = "⏹ Рабочее ядро остановлено. Админ-бот остаётся онлайн."
            elif action == "restart":
                await runtime.restart()
                text = "🔄 Рабочее ядро перезапущено."
            elif action == "delete":
                ok = await repo.enqueue_manual_delete(int(payload["message_id"]))
                if ok:
                    runtime.wake_worker()
                text = "Удаление поставлено в очередь." if ok else "Запись не найдена."
            elif action == "republish":
                ok = await repo.enqueue_republish(int(payload["message_id"]))
                if ok:
                    runtime.wake_worker()
                text = "Повторная обработка поставлена в очередь." if ok else "Запись не найдена."
            elif action == "cleardb":
                result = await repo.clear_database()
                text = (
                    "✅ Данные LapBase полностью очищены.\n"
                    f"posts: {result['posts']}\n"
                    f"stats_events: {result['stats_events']}\n"
                    f"admin_confirmations: {result['admin_confirmations']}\n"
                    f"system_state: {result['system_state']}\n\n"
                    "Схема БД сохранена. Старые сообщения в Telegram-канале не удалялись."
                )
            else:
                text = f"Неизвестное действие: {action}"
            logger.info("Admin action confirmed: %s payload=%s", action, payload)
            await callback.answer("Выполнено")
            if callback.message:
                await callback.message.edit_reply_markup(reply_markup=None)
                await callback.message.answer(text)
        except Exception as exc:
            logger.exception("Admin action failed: %s", action)
            await callback.answer("Ошибка", show_alert=True)
            if callback.message:
                await callback.message.answer(f"{type(exc).__name__}: {exc}")

    root.include_router(admin)
    return root


async def setup_bot_commands(bot: Bot, config: Config) -> None:
    await bot.set_my_commands(
        [BotCommand(command="start", description="Open LapBaseApp / информация")],
        scope=BotCommandScopeDefault(),
    )
    commands = [
        BotCommand(command="start", description="Админ-панель / запуск ядра"),
        BotCommand(command="status", description="Статус LapBase"),
        BotCommand(command="health", description="Состояние компонентов"),
        BotCommand(command="post", description="Ручная публикация в Telegram"),
        BotCommand(command="pause", description="Приостановить очередь"),
        BotCommand(command="resume", description="Продолжить очередь"),
        BotCommand(command="sync", description="Синхронизация за 24 часа"),
        BotCommand(command="logs", description="Показать логи"),
        BotCommand(command="backup", description="Создать резервную копию БД"),
        BotCommand(command="cleardb", description="Полностью очистить данные БД"),
        BotCommand(command="help", description="Список команд администратора"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=config.telegram_admin_user_id))
    except Exception:
        logger.exception("Could not set admin-scoped bot commands")
