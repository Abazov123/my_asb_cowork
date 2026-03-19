"""Command handlers for /start, /help, /status, /settings."""

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from d_brain.bot.keyboards import (
    get_help_inline_keyboard,
    get_main_keyboard,
    get_settings_keyboard,
    get_start_inline_keyboard,
)
from d_brain.bot.states import SettingsState
from d_brain.config import get_settings
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="commands")

# In-memory night notifications toggle (per-process, resets on restart)
_night_notifications_enabled: bool = True


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(
        "<b>d-brain</b> - твой голосовой дневник\n\n"
        "Отправляй мне:\n"
        "🎤 Голосовые сообщения\n"
        "💬 Текст\n"
        "📷 Фото\n"
        "↩️ Пересланные сообщения\n\n"
        "Всё будет сохранено и обработано.\n\n"
        "<b>Команды:</b>\n"
        "/status - статус сегодняшнего дня\n"
        "/process - обработать записи\n"
        "/do - выполнить произвольный запрос\n"
        "/weekly - недельный дайджест\n"
        "/done - завершить рефлексию недели\n"
        "/fix - добавить исправление транскрипции\n"
        "/help - справка",
        reply_markup=get_main_keyboard(),
    )
    await message.answer(
        "Быстрые действия:",
        reply_markup=get_start_inline_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(
        "<b>Как использовать d-brain:</b>\n\n"
        "1. Отправь голосовое — я транскрибирую и сохраню\n"
        "2. Отправь текст — сохраню как есть\n"
        "3. Отправь фото — сохраню в attachments\n"
        "4. Перешли сообщение — сохраню с источником\n\n"
        "Вечером используй /process для обработки:\n"
        "Мысли → Obsidian, Задачи → Todoist\n\n"
        "<b>Рефлексия недели:</b>\n"
        "Каждое воскресенье в 18:00 получишь дайджест + вопросы для рефлексии.\n"
        "Отвечай голосом или текстом, по одному или все сразу.\n"
        "Скажи «готово» или /done — бот обработает и сохранит рефлексию.\n\n"
        "<b>Исправление транскрипций:</b>\n"
        "<code>/fix Алабыжев → Алабужев (коллега)</code>\n"
        "Исправление применится к новым записям, задачам Todoist и daily-файлам.\n\n"
        "<b>Команды:</b>\n"
        "/status - сколько записей сегодня\n"
        "/process - обработать записи\n"
        "/do - выполнить произвольный запрос\n"
        "/weekly - недельный дайджест\n"
        "/done - завершить рефлексию недели\n"
        "/fix - добавить правило исправления транскрипции\n\n"
        "<i>Пример /do: перенеси просроченные задачи на понедельник</i>",
        reply_markup=get_main_keyboard(),
    )
    await message.answer(
        "Быстрые действия:",
        reply_markup=get_help_inline_keyboard(),
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Handle /status command."""
    user_id = message.from_user.id if message.from_user else 0
    settings = get_settings()
    storage = VaultStorage(settings.vault_path)

    # Log command
    session = SessionStore(settings.vault_path)
    session.append(user_id, "command", cmd="/status")

    today = date.today()
    content = storage.read_daily(today)

    if not content:
        await message.answer(f"📅 <b>{today}</b>\n\nЗаписей пока нет.")
        return

    lines = content.strip().split("\n")
    entries = [line for line in lines if line.startswith("## ")]

    voice_count = sum(1 for e in entries if "[voice]" in e)
    text_count = sum(1 for e in entries if "[text]" in e)
    photo_count = sum(1 for e in entries if "[photo]" in e)
    forward_count = sum(1 for e in entries if "[forward from:" in e)

    total = len(entries)

    # Get weekly stats from session
    week_stats = ""
    stats = session.get_stats(user_id, days=7)
    if stats:
        week_stats = "\n\n<b>За 7 дней:</b>"
        for entry_type, count in sorted(stats.items()):
            week_stats += f"\n• {entry_type}: {count}"

    # Check reflection status
    from d_brain.services.reflection import ReflectionService
    reflection = ReflectionService(settings.vault_path)
    week = reflection.get_pending_week()
    reflection_note = ""
    if week:
        reflection_note = f"\n\n🪞 <b>Рефлексия недели {week} активна</b> — пиши /done когда закончишь"

    await message.answer(
        f"📅 <b>{today}</b>\n\n"
        f"Всего записей: <b>{total}</b>\n"
        f"- 🎤 Голосовых: {voice_count}\n"
        f"- 💬 Текстовых: {text_count}\n"
        f"- 📷 Фото: {photo_count}\n"
        f"- ↩️ Пересланных: {forward_count}"
        f"{week_stats}"
        f"{reflection_note}"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    """Handle /settings command — show Settings menu."""
    settings = get_settings()
    await message.answer(
        f"<b>Настройки</b>\n\n"
        f"🏙️ Город: <b>{settings.location_city}</b>\n",
        reply_markup=get_settings_keyboard(_night_notifications_enabled),
    )


# --- Inline callback handlers for /start quick-access buttons ---

@router.callback_query(F.data == "cmd:process")
async def cb_process(callback: CallbackQuery, state: FSMContext) -> None:
    """Inline button: trigger /process."""
    from d_brain.bot.handlers.process import cmd_process
    await callback.answer()
    await cmd_process(callback.message)  # type: ignore[arg-type]


@router.callback_query(F.data == "cmd:do")
async def cb_do(callback: CallbackQuery, state: FSMContext) -> None:
    """Inline button: trigger /do (open session)."""
    from d_brain.bot.handlers.do import open_session
    await callback.answer()
    await open_session(callback.message, state)  # type: ignore[arg-type]


@router.callback_query(F.data == "cmd:weekly")
async def cb_weekly(callback: CallbackQuery) -> None:
    """Inline button: trigger /weekly."""
    from d_brain.bot.handlers.weekly import cmd_weekly
    await callback.answer()
    await cmd_weekly(callback.message)  # type: ignore[arg-type]


@router.callback_query(F.data == "cmd:settings")
async def cb_settings(callback: CallbackQuery) -> None:
    """Inline button: open Settings menu."""
    settings = get_settings()
    await callback.answer()
    await callback.message.answer(  # type: ignore[union-attr]
        f"<b>Настройки</b>\n\n"
        f"🏙️ Город: <b>{settings.location_city}</b>\n",
        reply_markup=get_settings_keyboard(_night_notifications_enabled),
    )


# --- Settings menu callbacks ---

@router.callback_query(F.data == "settings:toggle_night")
async def cb_toggle_night(callback: CallbackQuery) -> None:
    """Toggle night notifications setting."""
    global _night_notifications_enabled
    _night_notifications_enabled = not _night_notifications_enabled
    status = "включены" if _night_notifications_enabled else "выключены"
    await callback.answer(f"Ночные уведомления {status}")
    settings = get_settings()
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"<b>Настройки</b>\n\n"
        f"🏙️ Город: <b>{settings.location_city}</b>\n",
        reply_markup=get_settings_keyboard(_night_notifications_enabled),
    )


@router.callback_query(F.data == "settings:change_city")
async def cb_change_city_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt user to enter a new city name."""
    await callback.answer()
    await state.set_state(SettingsState.waiting_for_city)
    await callback.message.answer(  # type: ignore[union-attr]
        "Введи название города (например: <b>Санкт-Петербург</b>):"
    )


@router.message(SettingsState.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext) -> None:
    """Save new city name from user input."""
    city = (message.text or "").strip()
    if not city:
        await message.answer("Название города не может быть пустым. Попробуй ещё раз:")
        return
    await state.clear()
    # Persist to .env file by updating the cached settings object in-place
    settings = get_settings()
    object.__setattr__(settings, "location_city", city)
    await message.answer(
        f"✅ Город обновлён: <b>{city}</b>",
        reply_markup=get_settings_keyboard(_night_notifications_enabled),
    )
