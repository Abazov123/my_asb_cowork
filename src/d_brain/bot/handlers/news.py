"""Handler for /news command — show today's AI news with summaries."""

import json
import logging
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from d_brain.config import get_settings

router = Router(name="news")
logger = logging.getLogger(__name__)


class NewsCB(CallbackData, prefix="news"):
    idx: int  # index in articles list


@router.message(Command("news"))
async def cmd_news(message: Message) -> None:
    """Handle /news command — display today's article cards."""
    settings = get_settings()
    news_path = settings.vault_path / ".session" / "morning-news.json"

    if not news_path.exists():
        await message.answer("📰 Новостей на сегодня нет. Запустится утром следующего дня.")
        return

    try:
        data = json.loads(news_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to read morning-news.json: %s", e)
        await message.answer("❌ Ошибка чтения новостей.")
        return

    articles = data.get("articles", [])
    if not articles:
        await message.answer("📰 Список новостей пуст.")
        return

    date_str = data.get("date", "сегодня")
    await message.answer(f"📰 <b>Новости на {date_str}</b> — {len(articles)} статей")

    for i, art in enumerate(articles):
        title = art.get("title", "Без названия")
        source = art.get("source", "")
        url = art.get("url", "")

        text = f"<b>{title}</b>"
        if source:
            text += f"\n<i>{source}</i>"

        buttons = []
        buttons.append(InlineKeyboardButton(
            text="📖 Изложение",
            callback_data=NewsCB(idx=i).pack(),
        ))
        if url:
            buttons.append(InlineKeyboardButton(text="🔗 Оригинал", url=url))

        kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
        await message.answer(text, reply_markup=kb)


@router.callback_query(NewsCB.filter())
async def _on_news_read(query: CallbackQuery, callback_data: NewsCB) -> None:
    """Handle 'Изложение' button — show article summary."""
    settings = get_settings()
    news_path = settings.vault_path / ".session" / "morning-news.json"

    try:
        data = json.loads(news_path.read_text(encoding="utf-8"))
        articles = data.get("articles", [])
        idx = callback_data.idx
        if idx < 0 or idx >= len(articles):
            await query.answer("❌ Статья не найдена.")
            return
        art = articles[idx]
    except Exception as e:
        logger.error("Failed to read article for news callback: %s", e)
        await query.answer("❌ Ошибка чтения статьи.")
        return

    title = art.get("title", "Без названия")
    summary = art.get("summary") or "_Изложение не готово._"
    url = art.get("url", "")

    text = f"📰 <b>{title}</b>\n\n{summary}"
    if url:
        text += f'\n\n<a href="{url}">Читать оригинал →</a>'

    await query.message.edit_text(text, reply_markup=None)
    await query.answer()
