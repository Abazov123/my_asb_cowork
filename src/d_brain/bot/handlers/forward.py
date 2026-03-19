"""Forwarded message handler."""

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

from aiogram import Router
from aiogram.types import Message

from d_brain.config import get_settings
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="forward")
logger = logging.getLogger(__name__)


async def _generate_summary(text: str, source: str, vault_path: Path) -> dict | None:
    """Generate 3-point summary via Claude Haiku. Returns None on timeout/failure."""
    if len(text) < 80:
        return None
    prompt = (
        f"Статья/текст от «{source}». Выдели 3 ключевых тезиса и 1 практическую идею для личного бота-помощника.\n"
        f"Верни ТОЛЬКО JSON без markdown: {{\"points\": [\"...\",\"...\",\"...\"], \"idea\": \"...\"}}\n\n"
        f"Текст:\n{text[:1500]}"
    )
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: subprocess.run(
                    ["claude", "--print", "--dangerously-skip-permissions",
                     "--model", "claude-haiku-4-5-20251001", "-p", prompt],
                    capture_output=True, text=True, timeout=20,
                    cwd=str(vault_path.parent), check=False,
                )
            ),
            timeout=22,
        )
        output = result.stdout.strip()
        if "```" in output:
            output = re.sub(r"```(?:json)?\s*", "", output).strip().rstrip("`").strip()
        data = json.loads(output)
        if isinstance(data.get("points"), list) and data.get("idea"):
            return data
    except Exception as e:
        logger.debug("Summary generation skipped: %s", e)
    return None


@router.message(lambda m: m.forward_origin is not None)
async def handle_forward(message: Message) -> None:
    """Handle forwarded messages."""
    if not message.from_user:
        return

    settings = get_settings()
    storage = VaultStorage(settings.vault_path)

    # Determine source name
    source_name = "Unknown"
    origin = message.forward_origin

    if hasattr(origin, "sender_user") and origin.sender_user:
        user = origin.sender_user
        source_name = user.full_name
    elif hasattr(origin, "sender_user_name") and origin.sender_user_name:
        source_name = origin.sender_user_name
    elif hasattr(origin, "chat") and origin.chat:
        chat = origin.chat
        source_name = f"@{chat.username}" if chat.username else chat.title or "Channel"
    elif hasattr(origin, "sender_name") and origin.sender_name:
        source_name = origin.sender_name

    content = message.text or message.caption or "[media]"
    msg_type = f"[forward from: {source_name}]"

    timestamp = datetime.fromtimestamp(message.date.timestamp())
    storage.append_to_daily(content, timestamp, msg_type)

    # Log to session
    session = SessionStore(settings.vault_path)
    session.append(
        message.from_user.id,
        "forward",
        text=content,
        source=source_name,
        msg_id=message.message_id,
    )

    # Generate structured summary for text content
    summary = None
    if content != "[media]":
        summary = await _generate_summary(content, source_name, settings.vault_path)
        if summary:
            summary_block = (
                "📋 Резюме:\n" +
                "\n".join(f"• {p}" for p in summary["points"]) +
                f"\n💡 {summary['idea']}"
            )
            storage.append_to_daily(summary_block, timestamp, "[summary]")

    if summary and summary.get("points"):
        points_text = "\n".join(f"• {p}" for p in summary["points"])
        await message.answer(
            f"✓ Сохранено (от {source_name})\n\n{points_text}\n💡 {summary['idea']}"
        )
    else:
        await message.answer(f"✓ Сохранено (от {source_name})")

    logger.info("Forwarded message saved from: %s", source_name)
