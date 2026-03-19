"""Handler for /do command and interactive Claude sessions."""

from __future__ import annotations

import asyncio
import html
import logging
import subprocess
from typing import AsyncIterator

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from d_brain.bot.formatters import format_process_report, sanitize_telegram_html
from d_brain.bot.keyboards import get_main_keyboard, get_session_keyboard
from d_brain.bot.states import AgentSessionState, DoCommandState
from d_brain.config import get_settings
from d_brain.services.claude_session import SESSIONS, ClaudeSession
from d_brain.services.processor import ClaudeProcessor
from d_brain.services.transcription import DeepgramTranscriber

router = Router(name="do")
logger = logging.getLogger(__name__)

_SESSION_STATES = (AgentSessionState.in_session,)


# ─── Session management ──────────────────────────────────────────────────────

async def open_session(message: Message, state: FSMContext) -> None:
    """Open a new interactive Claude session (or replace existing one)."""
    user_id = message.from_user.id if message.from_user else 0
    settings = get_settings()

    # Close existing session if any
    old = SESSIONS.pop(user_id, None)
    if old:
        await old.stop()

    session = ClaudeSession(
        settings.vault_path,
        settings.vault_path.parent / "mcp-config.json",
        settings.todoist_api_key,
    )
    await session.start()
    SESSIONS[user_id] = session
    await state.set_state(AgentSessionState.in_session)
    await message.answer(
        "🤖 <b>Сессия с Claude открыта</b>\n\n"
        "Отправь команду — текстом или голосом.",
        reply_markup=get_session_keyboard(),
    )


# ─── Prompt extraction helper ────────────────────────────────────────────────

async def _extract_prompt(message: Message, bot: Bot) -> str | None:
    """Extract text prompt from a voice or text message."""
    if message.voice:
        await message.chat.do(action="typing")
        settings = get_settings()
        transcriber = DeepgramTranscriber(settings.deepgram_api_key)
        try:
            file = await bot.get_file(message.voice.file_id)
            if not file.file_path:
                await message.answer("❌ Не удалось скачать голосовое")
                return None
            file_bytes = await bot.download_file(file.file_path)
            if not file_bytes:
                await message.answer("❌ Не удалось скачать голосовое")
                return None
            audio_bytes = file_bytes.read()
            prompt = await transcriber.transcribe(audio_bytes)
        except Exception as e:
            logger.exception("Failed to transcribe voice in session")
            await message.answer(f"❌ Не удалось транскрибировать: {html.escape(str(e))}")
            return None
        if not prompt:
            await message.answer("❌ Не удалось распознать речь")
            return None
        await message.answer(f"🎤 <i>{html.escape(prompt)}</i>")
        return prompt

    if message.text:
        return message.text

    await message.answer("❌ Отправь текст или голосовое сообщение")
    return None


# ─── Streaming helper ────────────────────────────────────────────────────────

def _build_status_text(
    text_parts: list[str],
    tools_used: list[str],
    done: bool,
) -> str:
    """Build Telegram message text from accumulated stream data."""
    tools_line = ""
    if tools_used:
        seen: dict[str, None] = {}
        for t in tools_used:
            seen[t] = None
        unique = list(seen.keys())[-5:]
        tools_line = "🔧 " + " · ".join(unique) + "\n─────────────────\n"

    body = "".join(text_parts)
    max_body = 3800 - len(tools_line)
    if len(body) > max_body:
        body = body[-max_body:]

    suffix = "\n\n✅ <i>Готово — жди следующую команду или нажми 🛑</i>" if done else ""
    sanitized_body = sanitize_telegram_html(body) if body else ""
    result = tools_line + sanitized_body + suffix
    return result or "⏳ Claude думает..."


async def _do_stream(
    message: Message,
    session: ClaudeSession,
    state: FSMContext,
    events: AsyncIterator,
    status_msg: Message,
) -> None:
    """Core streaming loop: read events and update Telegram in real-time."""
    text_parts: list[str] = []
    tools_used: list[str] = []
    last_edit = 0.0

    async def _refresh(done: bool = False) -> None:
        nonlocal last_edit
        now = asyncio.get_event_loop().time()
        if not done and now - last_edit < 2.5:
            return
        last_edit = now
        txt = _build_status_text(text_parts, tools_used, done)
        try:
            await status_msg.edit_text(txt)
        except Exception:
            pass

    async for event in events:
        if not isinstance(event, dict):
            continue

        etype = event.get("type")

        # Raw API streaming deltas (may or may not appear depending on CLI version)
        if etype == "stream_event":
            inner = event.get("event", {})
            if inner.get("type") == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    text_parts.append(delta.get("text", ""))
                    await _refresh()

        # --include-partial-messages: repeated assistant events with accumulated text
        elif etype == "assistant":
            content = event.get("message", {}).get("content", [])
            accumulated = ""
            for block in content:
                if block.get("type") == "text":
                    accumulated += block.get("text", "")
                elif block.get("type") == "tool_use":
                    tools_used.append(block.get("name", "tool"))
            if accumulated:
                # Replace, not append — each event contains full text so far
                text_parts.clear()
                text_parts.append(accumulated)
            await _refresh()

        # End of turn
        elif etype == "result":
            await _refresh(done=True)
            if session.is_alive:
                await state.set_state(AgentSessionState.in_session)
            return

    # Stream ended without result
    await _refresh(done=True)
    if session.is_alive:
        await state.set_state(AgentSessionState.in_session)


# ─── Session keyboard button handlers ────────────────────────────────────────

@router.message(*_SESSION_STATES, F.text == "🛑 Завершить сессию")
async def btn_stop_session(message: Message, state: FSMContext) -> None:
    """Handle 'Stop session' keyboard button."""
    user_id = message.from_user.id if message.from_user else 0
    session = SESSIONS.pop(user_id, None)
    if session:
        await session.stop()
    await state.clear()
    await message.answer("🛑 Сессия завершена.", reply_markup=get_main_keyboard())


@router.message(*_SESSION_STATES, F.text == "📋 Журнал")
async def btn_journal(message: Message) -> None:
    """Handle 'Journal' keyboard button — show recent bot logs."""
    await _send_journal(message)


# ─── /stop command ───────────────────────────────────────────────────────────

@router.message(AgentSessionState.in_session, Command("stop"))
async def cmd_stop_session(message: Message, state: FSMContext) -> None:
    """End the active Claude session."""
    user_id = message.from_user.id if message.from_user else 0
    session = SESSIONS.pop(user_id, None)
    if session:
        await session.stop()
    await state.clear()
    await message.answer("🛑 Сессия завершена.", reply_markup=get_main_keyboard())


# ─── Session input handler ───────────────────────────────────────────────────

@router.message(AgentSessionState.in_session)
async def handle_session_input(message: Message, bot: Bot, state: FSMContext) -> None:
    """Handle text/voice input during an active Claude session."""
    user_id = message.from_user.id if message.from_user else 0
    session = SESSIONS.get(user_id)

    if not session or not session.is_alive:
        SESSIONS.pop(user_id, None)
        await state.clear()
        await message.answer(
            "⚠️ Сессия прервалась. Нажми «✨ Запрос» снова.",
            reply_markup=get_main_keyboard(),
        )
        return

    prompt = await _extract_prompt(message, bot)
    if not prompt:
        return

    status_msg = await message.answer("⏳ Claude думает...")
    try:
        await _do_stream(message, session, state, session.send(prompt), status_msg)
    except Exception:
        logger.exception("Unexpected error in Claude session stream")
        if session.is_alive:
            await state.set_state(AgentSessionState.in_session)
        try:
            await status_msg.edit_text("❌ Ошибка в сессии. Попробуй снова или нажми 🛑")
        except Exception:
            pass


# ─── Journal helper ──────────────────────────────────────────────────────────

async def _send_journal(message: Message, lines: int = 40) -> None:
    """Fetch and send recent bot journal entries."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["journalctl", "-u", "d-brain-bot", f"-n{lines}", "--no-pager", "--output=short"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        if not output:
            await message.answer("📋 Журнал пуст.")
            return
        if len(output) > 3800:
            output = "...\n" + output[-3800:]
        await message.answer(f"<pre>{html.escape(output)}</pre>")
    except Exception as e:
        await message.answer(f"❌ Не удалось получить журнал: {html.escape(str(e))}")


# ─── /do command (backward compat) ──────────────────────────────────────────

@router.message(Command("do"))
async def cmd_do(message: Message, command: CommandObject, state: FSMContext) -> None:
    """Handle /do: one-shot with args, session without args."""
    user_id = message.from_user.id if message.from_user else 0
    if command.args:
        await process_request(message, command.args, user_id)
        return
    await open_session(message, state)


@router.message(DoCommandState.waiting_for_input)
async def handle_do_input(message: Message, bot: Bot, state: FSMContext) -> None:
    """Handle voice/text input after /do command (legacy one-shot mode)."""
    await state.clear()

    prompt = None
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
            prompt = await transcriber.transcribe(audio_bytes)
        except Exception as e:
            logger.exception("Failed to transcribe voice for /do")
            await message.answer(f"❌ Не удалось транскрибировать: {e}")
            return
        if not prompt:
            await message.answer("❌ Не удалось распознать речь")
            return
        await message.answer(f"🎤 <i>{prompt}</i>")
    elif message.text:
        prompt = message.text
    else:
        await message.answer("❌ Отправь текст или голосовое сообщение")
        return

    user_id = message.from_user.id if message.from_user else 0
    await process_request(message, prompt, user_id)


async def process_request(message: Message, prompt: str, user_id: int = 0) -> None:
    """Process a one-shot Claude request (no persistent session)."""
    status_msg = await message.answer("⏳ Выполняю...")
    settings = get_settings()
    processor = ClaudeProcessor(settings.vault_path, settings.todoist_api_key)

    async def run_with_progress() -> dict:
        task = asyncio.create_task(
            asyncio.to_thread(processor.execute_prompt, prompt, user_id)
        )
        elapsed = 0
        while not task.done():
            await asyncio.sleep(30)
            elapsed += 30
            if not task.done():
                try:
                    await status_msg.edit_text(
                        f"⏳ Выполняю... ({elapsed // 60}m {elapsed % 60}s)"
                    )
                except Exception:
                    pass
        return await task

    report = await run_with_progress()
    formatted = format_process_report(report)
    try:
        await status_msg.edit_text(formatted)
    except Exception:
        await status_msg.edit_text(formatted, parse_mode=None)
