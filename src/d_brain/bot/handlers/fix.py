"""Handler for /fix command — add transcription correction rules."""

import asyncio
import logging
import re

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from d_brain.bot.formatters import format_process_report
from d_brain.config import get_settings
from d_brain.services.corrections import CorrectionsService
from d_brain.services.processor import ClaudeProcessor

router = Router(name="fix")
logger = logging.getLogger(__name__)

# Matches: "wrong → correct" or "wrong -> correct", optionally with (context)
_RULE_RE = re.compile(
    r"^(.+?)\s+[→\->]+\s+(.+?)(?:\s+\((.+?)\))?\s*$",
    re.UNICODE,
)


def _parse_rule(args: str) -> tuple[str, str, str] | None:
    """Parse '/fix wrong → correct (context)' arguments.

    Returns:
        (wrong, correct, context) or None if parsing fails.
    """
    m = _RULE_RE.match(args.strip())
    if not m:
        return None
    wrong = m.group(1).strip()
    correct = m.group(2).strip()
    context = (m.group(3) or "").strip()
    return wrong, correct, context


@router.message(Command("fix"))
async def cmd_fix(message: Message, command: CommandObject) -> None:
    """Handle /fix wrong → correct (context).

    Adds the correction rule and applies it retroactively to Todoist + recent daily files.
    """
    if not command.args:
        await message.answer(
            "📝 <b>Формат:</b>\n"
            "<code>/fix неправильно → правильно</code>\n"
            "<code>/fix неправильно → правильно (контекст)</code>\n\n"
            "<b>Примеры:</b>\n"
            "• <code>/fix Алабыжев → Алабужев (коллега Дима)</code>\n"
            "• <code>/fix Excel → XL (подразделение Loomni)</code>\n\n"
            "Исправление будет применено к новым транскрипциям, "
            "задачам Todoist и daily-файлам за последние 7 дней."
        )
        return

    parsed = _parse_rule(command.args)
    if not parsed:
        await message.answer(
            "❌ Не удалось разобрать правило.\n"
            "Используй стрелку: <code>/fix неправильно → правильно</code>"
        )
        return

    wrong, correct, context = parsed
    settings = get_settings()
    corrections = CorrectionsService(settings.vault_path)

    # Check for exact duplicate
    existing = corrections.load()
    for rule in existing:
        if rule["wrong"].lower() == wrong.lower():
            await message.answer(
                f"ℹ️ Правило для <b>{wrong}</b> уже существует:\n"
                f"<code>{rule['wrong']} → {rule['correct']}</code>"
                + (f" ({rule['context']})" if rule["context"] else "")
                + "\n\nЧтобы обновить — сначала удали старое через /do"
            )
            return

    # Save to corrections.md
    corrections.add(wrong, correct, context)

    ctx_note = f" ({context})" if context else ""
    await message.answer(
        f"✅ Правило добавлено:\n<code>{wrong} → {correct}{ctx_note}</code>\n\n"
        "⏳ Применяю ретроспективно к Todoist и daily-файлам..."
    )

    # Retroactive application via Claude
    processor = ClaudeProcessor(settings.vault_path, settings.todoist_api_key)
    retro_prompt = (
        f"Исправь транскрипционную ошибку везде где она встречается.\n\n"
        f"ПРАВИЛО: «{wrong}» → «{correct}»"
        + (f"\nКОНТЕКСТ: {context}" if context else "")
        + "\n\nЗАДАЧА:\n"
        "1. Найди задачи в Todoist, где встречается слово «{wrong}» и исправь их.\n"
        "2. Пройдись по daily-файлам за последние 7 дней в vault/daily/ "
        "и замени «{wrong}» на «{correct}» во всех вхождениях.\n"
        "3. Верни краткий отчёт: сколько задач исправлено, сколько daily-файлов.\n\n"
        "CRITICAL OUTPUT FORMAT: Raw HTML для Telegram. "
        "Начни с ✅ <b>Ретроспективное исправление</b>."
    ).format(wrong=wrong, correct=correct)

    report = await asyncio.to_thread(processor.execute_prompt, retro_prompt)
    formatted = format_process_report(report)
    try:
        await message.answer(formatted)
    except Exception:
        await message.answer(formatted, parse_mode=None)
