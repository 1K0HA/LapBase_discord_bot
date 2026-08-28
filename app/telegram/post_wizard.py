from __future__ import annotations

from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Config
from app.telegram.filters import AdminAuditMiddleware, MainAdminFilter


class PostForm(StatesGroup):
    photo = State()
    text = State()
    button_text = State()
    button_url = State()
    confirmation = State()


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https", "tg"} and bool(parsed.netloc or parsed.scheme == "tg")


def post_keyboard(button_text: str, button_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url)]]
    )


def preview_keyboard(button_text: str, button_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=button_url)],
            [
                InlineKeyboardButton(text="✅ Опубликовать", callback_data="post_publish"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="post_cancel"),
            ],
        ]
    )


def create_post_router(config: Config) -> Router:
    router = Router(name="post_wizard")
    router.message.filter(MainAdminFilter(config.telegram_admin_user_id))
    router.callback_query.filter(MainAdminFilter(config.telegram_admin_user_id))
    router.message.middleware(AdminAuditMiddleware())
    router.callback_query.middleware(AdminAuditMiddleware())

    @router.message(Command("post"))
    async def post_start(message: Message, state: FSMContext):
        await state.clear()
        await state.set_state(PostForm.photo)
        await message.answer(
            "Создание нового поста.\n\n1/4 — отправь картинку для публикации.\nДля отмены: /cancel"
        )

    @router.message(PostForm.photo)
    async def post_photo(message: Message, state: FSMContext):
        if not message.photo:
            await message.answer("Нужна именно картинка. Отправь изображение как фото, не как файл.")
            return
        await state.update_data(photo_file_id=message.photo[-1].file_id)
        await state.set_state(PostForm.text)
        await message.answer("2/4 — отправь текст поста. Максимум 1024 символа.")

    @router.message(PostForm.text)
    async def post_text(message: Message, state: FSMContext):
        text = (message.text or "").strip()
        if not text:
            await message.answer("Отправь текст поста обычным сообщением.")
            return
        if len(text) > 1024:
            await message.answer(f"Текст слишком длинный: {len(text)}. Максимум — 1024.")
            return
        await state.update_data(post_text=text)
        await state.set_state(PostForm.button_text)
        await message.answer("3/4 — отправь текст inline-кнопки.")

    @router.message(PostForm.button_text)
    async def post_button_text(message: Message, state: FSMContext):
        value = (message.text or "").strip()
        if not value:
            await message.answer("Название кнопки не может быть пустым.")
            return
        if len(value) > 64:
            await message.answer("Название кнопки слишком длинное. Используй до 64 символов.")
            return
        await state.update_data(button_text=value)
        await state.set_state(PostForm.button_url)
        await message.answer("4/4 — отправь ссылку кнопки (https://... или tg://...).")

    @router.message(PostForm.button_url)
    async def post_button_url(message: Message, state: FSMContext):
        url = (message.text or "").strip()
        if not is_valid_url(url):
            await message.answer("Некорректная ссылка. Используй https://..., http://... или tg://...")
            return
        await state.update_data(button_url=url)
        data = await state.get_data()
        await state.set_state(PostForm.confirmation)
        await message.answer_photo(
            photo=data["photo_file_id"],
            caption=data["post_text"],
            reply_markup=preview_keyboard(data["button_text"], url),
        )
        await message.answer("Это предпросмотр. Нажми «Опубликовать» или «Отмена».")

    @router.callback_query(PostForm.confirmation, F.data == "post_publish")
    async def publish_post(callback: CallbackQuery, bot: Bot, state: FSMContext):
        data = await state.get_data()
        try:
            await bot.send_photo(
                chat_id=config.telegram_channel_id,
                photo=data["photo_file_id"],
                caption=data["post_text"],
                reply_markup=post_keyboard(data["button_text"], data["button_url"]),
            )
        except Exception as exc:
            logger.exception("Ошибка ручной публикации /post")
            await callback.answer("Ошибка публикации", show_alert=True)
            if callback.message:
                await callback.message.answer(
                    "Публикация не выполнена. Подробности записаны в лог.\n"
                    f"Класс ошибки: {type(exc).__name__}"
                )
            return
        await state.clear()
        await callback.answer("Опубликовано")
        if callback.message:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                logger.debug("Не удалось убрать inline-кнопки после завершённого действия", exc_info=True)
            await callback.message.answer("✅ Пост опубликован.")

    @router.callback_query(PostForm.confirmation, F.data == "post_cancel")
    async def cancel_post_callback(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer("Отменено")
        if callback.message:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                logger.debug("Не удалось убрать inline-кнопки после завершённого действия", exc_info=True)
            await callback.message.answer("Создание поста отменено.")

    return router
