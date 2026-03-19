"""Text message handler."""

import asyncio
import logging
import random
from datetime import date, datetime
from pathlib import Path

from aiogram import Router
from aiogram.types import Message

from d_brain.config import get_settings
from d_brain.services.reflection import ReflectionService
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage
from d_brain.services.transcription import DeepgramTranscriber
from d_brain.services.webpage import (
    extract_urls,
    has_urls,
    scrape_webpage,
    summarize_content,
    synthesize_articles,
)
from d_brain.services.youtube import extract_video_id, process_youtube

router = Router(name="text")
logger = logging.getLogger(__name__)

_DONE_KEYWORDS = {"готово", "done", "finish", "закончил", "закончила", "все"}
_TG_LIMIT = 4000


def _log_error_to_notes(vault_path: Path, source: str, error: Exception) -> None:
    """Append runtime error as unreviewed 🔴 note to agent_notes.md."""
    notes_path = vault_path / "agent" / "agent_notes.md"
    if not notes_path.exists():
        return
    try:
        today = date.today().strftime("%Y%m%d")
        note_id = f"n-{today}-err-{random.randint(100, 999)}"
        error_text = str(error)[:200].replace("\n", " ")
        line = f"- `[ ]` 🔴 **[{source}]** Ошибка: {error_text} <!-- id: {note_id} -->\n"
        content = notes_path.read_text(encoding="utf-8")
        notes_path.write_text(content.rstrip("\n") + "\n" + line, encoding="utf-8")
        logger.info("Error note added: %s", note_id)
    except Exception as e:
        logger.error("Failed to log error note: %s", e)


async def _send_chunked(message: Message, text: str) -> None:
    for i in range(0, len(text), _TG_LIMIT):
        await message.answer(text[i : i + _TG_LIMIT])


@router.message(lambda m: m.text is not None and not m.text.startswith("/"))
async def handle_text(message: Message) -> None:
    """Handle text messages (excluding commands)."""
    if not message.text or not message.from_user:
        return

    settings = get_settings()

    # --- YouTube URL detected ---
    video_id = extract_video_id(message.text)
    if video_id and settings.youtube_api_key:
        await _handle_youtube(message, video_id, settings)
        return

    # --- Any message containing URLs ---
    if has_urls(message.text):
        await _handle_urls(message, settings)
        return

    # --- Plain text ---
    storage = VaultStorage(settings.vault_path)
    timestamp = datetime.fromtimestamp(message.date.timestamp())
    storage.append_to_daily(message.text, timestamp, "[text]")

    session = SessionStore(settings.vault_path)
    session.append(
        message.from_user.id,
        "text",
        text=message.text,
        msg_id=message.message_id,
    )

    reflection = ReflectionService(settings.vault_path)
    week = reflection.get_pending_week()

    if week and message.text.strip().lower() in _DONE_KEYWORDS:
        from d_brain.bot.handlers.done import _run_finalize
        if reflection.has_content(week):
            await _run_finalize(message)
        else:
            await message.answer(
                "📭 Рефлексия пока пустая — сначала ответь на вопросы, потом «готово»."
            )
        return

    extra = ""
    if week:
        reflection.append_entry(week, message.text, source="text")
        extra = " (+ рефлексия недели)"

    await message.answer(f"✓ Сохранено{extra}")
    logger.info("Text message saved: %d chars%s", len(message.text), extra)


async def _handle_youtube(message: Message, video_id: str, settings) -> None:  # type: ignore[type-arg]
    """Process YouTube URL: subtitles/transcription + top comments + summary."""
    wait_msg = await message.answer("⏳ Обрабатываю видео…")

    try:
        transcriber = DeepgramTranscriber(settings.deepgram_api_key)
        result = await process_youtube(video_id, settings.youtube_api_key, transcriber)

        title = result["title"]
        channel = result["channel"]
        duration = result["duration"]
        transcript = result["transcript"]
        source = result["transcript_source"]
        comments = result["comments"]

        # Source label
        source_label = {
            "subtitles_ru": "субтитры RU",
            "subtitles_en": "субтитры EN",
            "deepgram": "Deepgram",
        }.get(source, source)

        # Header
        header_parts = [f"▶️ {title}"] if title else ["▶️ YouTube"]
        meta_parts = []
        if channel:
            meta_parts.append(channel)
        if duration:
            meta_parts.append(duration)
        meta_parts.append(source_label)
        if meta_parts:
            header_parts.append(" · ".join(meta_parts))
        header = "\n".join(header_parts)

        # Comments block
        comments_block = ""
        if comments:
            top = comments[:12]
            lines = [f"• {c}" for c in top]
            comments_block = "\n\n━━━━━━━━━━\n💬 Топ комментарии:\n" + "\n".join(lines)

        # Full vault entry
        vault_text = header + "\n\n" + transcript + comments_block

        # Save to vault
        storage = VaultStorage(settings.vault_path)
        timestamp = datetime.fromtimestamp(message.date.timestamp())
        storage.append_to_daily(vault_text, timestamp, "[youtube]")

        session = SessionStore(settings.vault_path)
        session.append(
            message.from_user.id,
            "youtube",
            text=vault_text,
            msg_id=message.message_id,
        )

        reflection = ReflectionService(settings.vault_path)
        week = reflection.get_pending_week()
        extra = ""
        if week:
            reflection.append_entry(week, vault_text, source="youtube")
            extra = " (+ рефлексия недели)"

        # Summarize transcript via claude CLI (haiku)
        summary = await summarize_content(title, transcript, comments, "")

        # Delete wait message and send result
        await wait_msg.delete()
        await _send_chunked(message, header + "\n\n" + transcript)
        if comments_block:
            await _send_chunked(message, comments_block.strip())
        if summary:
            await message.answer(f"💡 Ключевое:\n{summary}\n\n✓ Записал{extra}")
        else:
            await message.answer(f"✓ Записал{extra}")

        logger.info(
            "YouTube saved: %s, transcript=%d chars, comments=%d",
            video_id, len(transcript), len(comments),
        )

    except Exception as exc:
        logger.exception("YouTube processing error")
        await wait_msg.delete()
        await message.answer(f"❌ Не удалось обработать видео: {exc}")
        await asyncio.to_thread(_log_error_to_notes, settings.vault_path, "YouTube", exc)


async def _handle_urls(message: Message, settings) -> None:  # type: ignore[type-arg]
    """Handle message containing one or more URLs: scrape each sequentially."""
    import re as _re

    raw_text = message.text.strip()
    urls = extract_urls(raw_text)
    user_note = _re.sub(r"https?://\S+", "", raw_text).strip()
    plural = len(urls) > 1

    current_label = [f"⏳ Читаю {len(urls)} ссылки…" if plural else "⏳ Читаю статью…"]
    status_msg = await message.answer(current_label[0])
    loop_start = asyncio.get_event_loop().time()

    async def _progress_updater() -> None:
        while True:
            await asyncio.sleep(30)
            elapsed = int(asyncio.get_event_loop().time() - loop_start)
            try:
                await status_msg.edit_text(f"{current_label[0]} ({elapsed}с)")
            except Exception:
                pass

    updater = asyncio.create_task(_progress_updater())

    storage = VaultStorage(settings.vault_path)
    session = SessionStore(settings.vault_path)
    reflection = ReflectionService(settings.vault_path)
    timestamp = datetime.fromtimestamp(message.date.timestamp())
    week = reflection.get_pending_week()

    collected: list[dict] = []

    try:
        for i, url in enumerate(urls):
            domain = url.split("/")[2] if url.count("/") >= 2 else url
            current_label[0] = (
                f"⏳ Читаю {i + 1}/{len(urls)}: {domain}" if plural
                else f"⏳ Читаю: {domain}"
            )
            try:
                await status_msg.edit_text(current_label[0])
            except Exception:
                pass

            try:
                result = await scrape_webpage(url)
                title = result["title"]
                text = result["text"]
                comments = result["comments"]

                if not text:
                    storage.append_to_daily(url, timestamp, "[url]")
                    collected.append({"url": url, "failed": True})
                    logger.warning("No text extracted from %s", url)
                    continue

                header = f"🌐 {title}" if title else f"🌐 {url}"
                comments_block = ""
                if comments:
                    lines = [f"• {c}" for c in comments[:12]]
                    comments_block = "\n\n━━━━━━━━━━\n💬 Топ комментарии:\n" + "\n".join(lines)
                note_block = f"\n\n📝 Заметка: {user_note}" if user_note else ""
                vault_text = f"{header}\n{url}{note_block}\n\n---\n\n{text}{comments_block}"

                storage.append_to_daily(vault_text, timestamp, "[url]")
                session.append(
                    message.from_user.id,
                    "url",
                    text=vault_text,
                    msg_id=message.message_id,
                )
                if week:
                    reflection.append_entry(week, vault_text, source="url")

                collected.append({"title": title, "url": url, "text": text, "comments": comments})
                logger.info("Webpage saved: url=%s, text=%d chars, comments=%d", url, len(text), len(comments))

            except Exception:
                logger.exception("Webpage scraping error for %s", url)
                collected.append({"url": url, "failed": True})

        # ── Build response ──
        ok = [a for a in collected if not a.get("failed")]
        failed_urls = [a["url"] for a in collected if a.get("failed")]
        extra = " (+ рефлексия недели)" if week else ""

        if not ok:
            await status_msg.edit_text("⚠️ Ничего не удалось прочитать.")
            return

        if len(ok) == 1:
            a = ok[0]
            current_label[0] = "⏳ Суммаризирую…"
            try:
                await status_msg.edit_text(current_label[0])
            except Exception:
                pass
            summary = await summarize_content(a["title"], a["text"], a["comments"], "")
            label = a.get("title") or a["url"]
            if summary:
                reply = f"📰 {label}\n\n{summary}\n\n✓ Записал{extra}"
            else:
                reply = f"✓ Записал{extra}: 📰 {label}"
        else:
            current_label[0] = "⏳ Синтезирую…"
            try:
                await status_msg.edit_text(current_label[0])
            except Exception:
                pass
            synthesis = await synthesize_articles(ok, "")
            titles_block = "\n".join(f"• {a.get('title') or a['url']}" for a in ok)
            reply = f"📚 Прочитал {len(ok)} публикации:\n{titles_block}\n\n💡 Синтез:\n{synthesis}\n\n✓ Записал{extra}"
            if failed_urls:
                reply += "\n\n❌ Не удалось: " + ", ".join(failed_urls)

        try:
            await status_msg.edit_text(reply)
        except Exception:
            await status_msg.edit_text(reply, parse_mode=None)

    finally:
        updater.cancel()
