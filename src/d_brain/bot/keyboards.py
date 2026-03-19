"""Reply keyboards for Telegram bot."""

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main reply keyboard with common commands."""
    builder = ReplyKeyboardBuilder()
    # First row: main commands
    builder.button(text="📊 Статус")
    builder.button(text="⚙️ Обработать")
    builder.button(text="📅 Неделя")
    # Second row: additional
    builder.button(text="✨ Запрос")
    builder.button(text="✏️ Правки")
    builder.button(text="❓ Помощь")
    # Third row: settings
    builder.button(text="⚙️ Настройки")
    builder.adjust(3, 3, 1)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def get_session_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard shown during an active Claude session."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Журнал")
    builder.button(text="🛑 Завершить сессию")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def get_edit_mode_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard shown during edit mode (collecting entries)."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Готово")
    builder.button(text="❌ Отмена")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def get_edit_confirm_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard shown after edit preview (confirm/cancel)."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="✅ Применить")
    builder.button(text="❌ Отменить")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)


def get_start_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for /start message with quick-access commands."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ Обработать", callback_data="cmd:process")
    builder.button(text="✨ Запрос", callback_data="cmd:do")
    builder.button(text="📅 Неделя", callback_data="cmd:weekly")
    builder.button(text="⚙️ Настройки", callback_data="cmd:settings")
    builder.adjust(3, 1)
    return builder.as_markup()


def get_help_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for /help message with quick-access commands."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⚙️ Обработать", callback_data="cmd:process")
    builder.button(text="✨ Запрос", callback_data="cmd:do")
    builder.button(text="📅 Неделя", callback_data="cmd:weekly")
    builder.adjust(3)
    return builder.as_markup()


def get_settings_keyboard(night_notifications: bool = True) -> InlineKeyboardMarkup:
    """Inline keyboard for Settings menu."""
    builder = InlineKeyboardBuilder()
    toggle_label = "🔔 Ночные уведомления: ВКЛ" if night_notifications else "🔕 Ночные уведомления: ВЫКЛ"
    builder.button(text=toggle_label, callback_data="settings:toggle_night")
    builder.button(text="🏙️ Сменить город", callback_data="settings:change_city")
    builder.adjust(1)
    return builder.as_markup()
