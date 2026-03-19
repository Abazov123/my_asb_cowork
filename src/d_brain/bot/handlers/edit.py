"""Handler for edit mode — batch corrections with preview via Claude."""

import asyncio
import logging

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from d_brain.bot.formatters import format_process_report
from d_brain.bot.keyboards import (
    get_edit_confirm_keyboard,
    get_edit_mode_keyboard,
    get_main_keyboard,
)
from d_brain.bot.states import EditModeState
from d_brain.config import get_settings
from d_brain.services.corrections import CorrectionsService
from d_brain.services.processor import ClaudeProcessor
from d_brain.services.transcription import DeepgramTranscriber

router = Router(name="edit")
logger = logging.getLogger(__name__)


async def _safe_edit_or_send(
    status_msg: Message, message: Message, text: str, **kwargs
) -> None:
    """Try to edit status_msg; if that fails, send a new message instead."""
    try:
        await status_msg.edit_text(text, **kwargs)
    except Exception:
        try:
            await message.answer(text, **kwargs)
        except Exception:
            # Last resort: strip formatting
            await message.answer(text, parse_mode=None)


async def _run_claude_with_progress(
    processor: ClaudeProcessor,
    prompt: str,
    user_id: int,
    status_msg: Message,
    label: str,
) -> dict:
    """Run Claude prompt in background thread with periodic progress updates."""
    task = asyncio.create_task(
        asyncio.to_thread(processor.execute_prompt, prompt, user_id)
    )
    elapsed = 0
    while not task.done():
        await asyncio.sleep(15)
        elapsed += 15
        if not task.done():
            try:
                await status_msg.edit_text(
                    f"⏳ {label}... ({elapsed // 60}m {elapsed % 60:02d}s)"
                )
            except Exception:
                pass
    return await task


async def enter_edit_mode(message: Message, state: FSMContext) -> None:
    """Activate edit mode — start collecting correction entries."""
    await state.set_state(EditModeState.collecting)
    await state.update_data(edit_entries=[])
    await message.answer(
        "✏️ <b>Режим правок</b>\n\n"
        "Отправляй голосовые или текстовые сообщения "
        "с описанием того, что нужно исправить.\n\n"
        "Когда закончишь — нажми <b>Готово</b>.",
        reply_markup=get_edit_mode_keyboard(),
    )


@router.message(EditModeState.collecting)
async def handle_edit_input(message: Message, bot: Bot, state: FSMContext) -> None:
    """Handle voice/text input during edit mode."""
    # Control buttons
    if message.text == "✅ Готово":
        await _preview_edits(message, state)
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer(
            "🚫 Режим правок отменён.",
            reply_markup=get_main_keyboard(),
        )
        return

    entry = None

    if message.voice:
        await message.chat.do(action="typing")
        settings = get_settings()
        transcriber = DeepgramTranscriber(settings.deepgram_api_key)
        try:
            file = await bot.get_file(message.voice.file_id)
            if not file.file_path:
                await message.answer("❌ Не удалось скачать голосовое")
                return

            file_bytes = await bot.download_file(file.file_path)
            if not file_bytes:
                await message.answer("❌ Не удалось скачать голосовое")
                return

            audio_bytes = file_bytes.read()
            transcript = await transcriber.transcribe(audio_bytes)
            if not transcript:
                await message.answer("❌ Не удалось распознать речь")
                return

            corrections = CorrectionsService(settings.vault_path)
            corrected, applied = corrections.apply(transcript)
            entry = corrected
            correction_note = ""
            if applied:
                fixes = ", ".join(applied)
                correction_note = f"\n<i>Коррекции: {fixes}</i>"
            await message.answer(f"🎤 <i>{corrected}</i>{correction_note}")
        except Exception as e:
            logger.exception("Failed to transcribe voice in edit mode")
            await message.answer(f"❌ Ошибка транскрипции: {e}")
            return

    elif message.text:
        entry = message.text

    if not entry:
        await message.answer("❌ Отправь текст или голосовое сообщение")
        return

    data = await state.get_data()
    entries = data.get("edit_entries", [])
    entries.append(entry)
    await state.update_data(edit_entries=entries)

    await message.answer(
        f"📝 Записано правок: <b>{len(entries)}</b>. "
        "Продолжай или нажми <b>Готово</b>."
    )


async def _preview_edits(message: Message, state: FSMContext) -> None:
    """Generate a preview plan of changes and ask for confirmation."""
    data = await state.get_data()
    entries = data.get("edit_entries", [])

    if not entries:
        await state.clear()
        await message.answer(
            "📭 Нет записанных правок.",
            reply_markup=get_main_keyboard(),
        )
        return

    status_msg = await message.answer("⏳ Составляю план правок...")

    numbered = "\n".join(f"{i + 1}. {e}" for i, e in enumerate(entries))
    preview_prompt = (
        "Пользователь хочет внести следующие правки:\n\n"
        f"{numbered}\n\n"
        "НЕ ВЫПОЛНЯЙ ПРАВКИ. Только составь план:\n"
        "- Какие задачи в Todoist будут изменены (найди их через mcp__todoist__find-tasks)\n"
        "- Какие файлы в vault будут отредактированы\n"
        "- Какие правила коррекции будут добавлены в corrections.md\n\n"
        "Для каждого пункта покажи: текущее значение → новое значение.\n"
        "Если не нашёл совпадений — укажи это.\n\n"
        "Формат: HTML для Telegram. Начни с 📋 <b>План правок</b>"
    )

    settings = get_settings()
    processor = ClaudeProcessor(settings.vault_path, settings.todoist_api_key)
    user_id = message.from_user.id if message.from_user else 0

    report = await _run_claude_with_progress(
        processor, preview_prompt, user_id, status_msg, "Составляю план правок"
    )

    if "error" in report:
        await state.clear()
        formatted = format_process_report(report)
        await _safe_edit_or_send(status_msg, message, formatted)
        await message.answer("↩️ Возврат в главное меню.", reply_markup=get_main_keyboard())
        return

    # Save the apply prompt for confirmation step
    apply_prompt = (
        "Пользователь хочет внести следующие правки:\n\n"
        f"{numbered}\n\n"
        "ВЫПОЛНИ ВСЕ ПРАВКИ. Для каждой:\n"
        "- Если нужно изменить/переименовать задачу в Todoist — найди и обнови через mcp__todoist__*\n"
        "- Если нужно перенести задачу на другой день — обнови due date через Todoist MCP\n"
        "- Если нужно исправить текст в daily-файлах — отредактируй файлы в vault/daily/\n"
        "- Если это общее правило замены слова — добавь в vault/corrections.md\n\n"
        "По каждой правке укажи что было сделано.\n"
        "Формат: HTML для Telegram. Начни с ✅ <b>Правки применены</b>"
    )

    await state.set_state(EditModeState.confirming)
    await state.update_data(edit_prompt=apply_prompt)

    formatted = format_process_report(report)
    await _safe_edit_or_send(status_msg, message, formatted)

    await message.answer(
        "Применить эти правки?",
        reply_markup=get_edit_confirm_keyboard(),
    )


@router.message(EditModeState.confirming)
async def handle_edit_confirm(message: Message, state: FSMContext) -> None:
    """Handle confirmation after preview."""
    if message.text == "❌ Отменить":
        await state.clear()
        await message.answer(
            "🚫 Правки отменены.",
            reply_markup=get_main_keyboard(),
        )
        return

    if message.text != "✅ Применить":
        await message.answer(
            "Нажми <b>Применить</b> или <b>Отменить</b>.",
            reply_markup=get_edit_confirm_keyboard(),
        )
        return

    data = await state.get_data()
    apply_prompt = data.get("edit_prompt", "")
    await state.clear()

    if not apply_prompt:
        await message.answer(
            "❌ Нет данных для применения.",
            reply_markup=get_main_keyboard(),
        )
        return

    status_msg = await message.answer(
        "⏳ Применяю правки...",
        reply_markup=get_main_keyboard(),
    )

    settings = get_settings()
    processor = ClaudeProcessor(settings.vault_path, settings.todoist_api_key)
    user_id = message.from_user.id if message.from_user else 0

    report = await _run_claude_with_progress(
        processor, apply_prompt, user_id, status_msg, "Применяю правки"
    )

    formatted = format_process_report(report)
    await _safe_edit_or_send(status_msg, message, formatted, reply_markup=get_main_keyboard())
