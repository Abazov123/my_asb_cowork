#!/usr/bin/env python
"""Weekly digest script - generates and sends to Telegram."""

import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from d_brain.config import get_settings
from d_brain.services.git import VaultGit
from d_brain.services.processor import ClaudeProcessor
from d_brain.services.reflection import ReflectionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

REFLECTION_INVITE = (
    "\n\n🪞 <b>Рефлексия недели</b>\n\n"
    "Пока свежо — ответь на несколько вопросов. "
    "Можно голосовым, одним или несколькими сообщениями:\n\n"
    "1. Что запомнилось сильнее всего за эту неделю?\n"
    "2. Какой день был самым успешным и почему?\n"
    "3. Каких целей удалось достичь?\n"
    "4. Что принесло больше всего радости?\n"
    "5. Что принесло больше всего пользы?\n"
    "6. Какого опыта хотелось бы избежать в будущем?\n\n"
    "Когда закончишь — напиши <b>готово</b> или /done"
)


async def main() -> None:
    """Generate weekly digest and send to Telegram."""
    settings = get_settings()
    processor = ClaudeProcessor(settings.vault_path, settings.todoist_api_key)
    git = VaultGit(settings.vault_path)

    logger.info("Starting weekly digest generation...")

    result = processor.generate_weekly()

    if "error" in result:
        report = f"Error: {result['error']}"
        logger.error("Weekly digest failed: %s", result["error"])
    else:
        report = result.get("report", "No output")
        logger.info("Weekly digest generated successfully")
        # Commit any changes
        git.commit_and_push("chore: weekly digest")

    # Send to Telegram
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        user_id = settings.allowed_user_ids[0] if settings.allowed_user_ids else None
        if not user_id:
            logger.error("No allowed user IDs configured")
            return

        # Send weekly digest
        try:
            await bot.send_message(chat_id=user_id, text=report)
        except Exception:
            # Fallback: send without HTML parsing
            await bot.send_message(chat_id=user_id, text=report, parse_mode=None)

        logger.info("Weekly digest sent to user %s", user_id)

        # Only start reflection if digest was generated successfully
        if "error" not in result:
            # Start reflection: write flag file and send invitation
            today = date.today()
            year, week, _ = today.isocalendar()
            week_id = f"{year}-W{week:02d}"

            # Deadline: next Monday at 09:00
            days_until_monday = (7 - today.weekday()) % 7 or 7
            deadline = datetime.combine(
                today + timedelta(days=days_until_monday),
                datetime.min.time().replace(hour=9),
            )

            reflection = ReflectionService(settings.vault_path)
            reflection.start(week_id, deadline)
            logger.info("Reflection started for week %s, deadline %s", week_id, deadline)

            # Send reflection invitation as separate message
            try:
                await bot.send_message(chat_id=user_id, text=REFLECTION_INVITE)
            except Exception:
                await bot.send_message(chat_id=user_id, text=REFLECTION_INVITE, parse_mode=None)

            logger.info("Reflection invitation sent for week %s", week_id)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
