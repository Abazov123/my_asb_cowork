"""Voice message handler."""

import logging
from datetime import datetime

from aiogram import Bot, Router
from aiogram.types import Message

from d_brain.config import get_settings
from d_brain.services.corrections import CorrectionsService
from d_brain.services.reflection import ReflectionService
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage
from d_brain.services.transcription import (
    DeepgramTranscriber,
    Utterance,
    build_confidence_note,
    format_diarized,
    identify_user_speaker,
)

router = Router(name="voice")
logger = logging.getLogger(__name__)

TELEGRAM_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
TELEGRAM_MSG_LIMIT = 4000
DIARIZE_THRESHOLD_SECS = 300  # 5 minutes


async def send_chunked(message: Message, text: str) -> None:
    for i in range(0, len(text), TELEGRAM_MSG_LIMIT):
        await message.answer(text[i : i + TELEGRAM_MSG_LIMIT])


@router.message(lambda m: m.voice is not None)
async def handle_voice(message: Message, bot: Bot) -> None:
    """Handle voice messages."""
    if not message.voice or not message.from_user:
        return

    await message.chat.do(action="typing")

    settings = get_settings()
    storage = VaultStorage(settings.vault_path)
    transcriber = DeepgramTranscriber(settings.deepgram_api_key)

    try:
        # --- size guard ---
        file_size = message.voice.file_size or 0
        if file_size > TELEGRAM_MAX_FILE_BYTES:
            await message.answer(
                "⚠️ Файл слишком большой (>20 MB, ~20+ минут).\n"
                "Telegram Bot API не позволяет скачать такой файл.\n\n"
                "Загрузи через портал: https://brain.niksfok.ru:8443"
            )
            return

        file = await bot.get_file(message.voice.file_id)
        if not file.file_path:
            await message.answer("Failed to download voice message")
            return

        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await message.answer("Failed to download voice message")
            return

        audio_bytes = file_bytes.read()
        duration = message.voice.duration
        use_diarize = duration >= DIARIZE_THRESHOLD_SECS

        # --- transcription ---
        confidence_note = ""
        utterances: list[Utterance] = []

        if use_diarize:
            await message.chat.do(action="typing")
            utterances = await transcriber.transcribe_diarized(audio_bytes)

            if not utterances:
                await message.answer("Could not transcribe audio")
                return

            user_speaker, is_confident = identify_user_speaker(utterances)
            num_speakers = len({u.speaker for u in utterances})
            transcript = format_diarized(utterances, user_speaker)

            if not is_confident and num_speakers > 1:
                confidence_note = build_confidence_note(utterances, user_speaker)
        else:
            transcript = await transcriber.transcribe(audio_bytes)
            if not transcript:
                await message.answer("Could not transcribe audio")
                return
            num_speakers = 1

        # --- corrections ---
        corrections = CorrectionsService(settings.vault_path)
        corrected, applied = corrections.apply(transcript)

        # --- storage ---
        timestamp = datetime.fromtimestamp(message.date.timestamp())
        storage.append_to_daily(corrected, timestamp, "[voice]")

        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            "voice",
            text=corrected,
            duration=duration,
            msg_id=message.message_id,
        )

        # --- reflection ---
        reflection = ReflectionService(settings.vault_path)
        week = reflection.get_pending_week()
        extra = ""
        if week:
            reflection.append_entry(week, corrected, source="voice")
            extra = " (+ рефлексия недели)"

        # --- reply ---
        footer = f"✓ Сохранено{extra}"
        if applied:
            footer += f" · Исправлено: {', '.join(applied)}"

        if use_diarize:
            mins, secs = divmod(duration, 60)
            header = f"🎤 Встреча · {mins}:{secs:02d} мин · {num_speakers} спикер(а)\n"
            await send_chunked(message, header + corrected + confidence_note)
        else:
            await send_chunked(message, f"🎤 {corrected}")

        await message.answer(footer)
        logger.info("Voice message saved: %d chars%s", len(corrected), extra)

    except Exception as e:
        logger.exception("Error processing voice message")
        await message.answer(f"Error: {e}")
