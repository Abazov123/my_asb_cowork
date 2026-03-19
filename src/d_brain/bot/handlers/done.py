"""Handler for /done command — finalize weekly reflection."""

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.config import get_settings
from d_brain.services.reflection import ReflectionService

router = Router(name="done")
logger = logging.getLogger(__name__)



async def _run_finalize(message: Message) -> None:
    """Run reflect_finalize.py and send result to user."""
    import subprocess
    import sys
    from pathlib import Path

    settings = get_settings()
    project_dir = settings.vault_path.parent
    script = project_dir / "scripts" / "reflect_finalize.py"

    status_msg = await message.answer("⏳ Обрабатываю рефлексию...")

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(script)],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

        if result.returncode != 0:
            err = result.stderr or "Неизвестная ошибка"
            await status_msg.edit_text(f"❌ Ошибка финализации рефлексии:\n<code>{err[:500]}</code>")
            return

        # reflect_finalize.py already sent the result to Telegram and committed to git
        try:
            await status_msg.delete()
        except Exception:
            pass

    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ Финализация рефлексии заняла слишком много времени.")
    except Exception as e:
        logger.exception("Error during reflection finalization")
        await status_msg.edit_text(f"❌ Ошибка: {e}")


@router.message(Command("done"))
async def cmd_done(message: Message) -> None:
    """Handle /done — finalize reflection immediately."""
    settings = get_settings()
    reflection = ReflectionService(settings.vault_path)

    week = reflection.get_pending_week()
    if not week:
        await message.answer("ℹ️ Нет активной рефлексии недели.")
        return

    if not reflection.has_content(week):
        await message.answer(
            "📭 Рефлексия пока пустая — отправь голосовое или текстовое сообщение "
            "с ответами на вопросы, потом снова /done."
        )
        return

    await _run_finalize(message)
