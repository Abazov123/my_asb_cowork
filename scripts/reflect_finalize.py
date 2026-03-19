#!/usr/bin/env python
"""Finalize weekly reflection — called by /done or Monday 09:00 systemd timer.

Reads pending reflection file, calls Claude to structure it and append
a reflection section to the weekly summary, then clears the flag.
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from d_brain.config import get_settings
from d_brain.services.reflection import ReflectionService
from d_brain.services.git import VaultGit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 1200  # 20 minutes


def finalize_reflection(settings, week: str, reflection_path: Path, summary_path: Path) -> str:
    """Call Claude to process reflection and append to summary.

    Returns:
        Output string to send to user.
    """
    mcp_config = settings.vault_path.parent / "mcp-config.json"

    prompt = f"""Сегодня я завершаю недельную рефлексию за {week}.

ФАЙЛЫ:
- Сырые ответы рефлексии: {reflection_path}
- Недельный дайджест: {summary_path}

ЗАДАЧА:
1. Прочитай файл рефлексии {reflection_path}
2. Прочитай недельный дайджест {summary_path}
3. Структурируй ответы пользователя по 6 вопросам рефлексии:
   1. Что запомнилось сильнее всего?
   2. Самый успешный день?
   3. Достигнутые цели?
   4. Что принесло больше всего радости?
   5. Что принесло больше всего пользы?
   6. Какого опыта хотелось бы избежать?
4. Сформулируй 2-3 конкретные рекомендации для следующей недели
   на основе рефлексии и целей из vault/goals/3-weekly.md
5. ДОЗАПИШИ в конец файла {summary_path} следующий раздел в Markdown формате:

## 🪞 Рефлексия недели

[структурированные ответы по 6 вопросам]

### 💡 Рекомендации на следующую неделю
[2-3 рекомендации]

CRITICAL OUTPUT FORMAT:
- Return ONLY raw HTML for Telegram (parse_mode=HTML)
- Start with ✅ <b>Рефлексия недели {week} сохранена</b>
- Кратко перечисли ключевые инсайты (3-5 пунктов)
- Allowed tags: <b>, <i>, <code>, <s>, <u>"""

    env = os.environ.copy()
    if settings.todoist_api_key:
        env["TODOIST_API_KEY"] = settings.todoist_api_key

    result = subprocess.run(
        [
            "claude",
            "--print",
            "--model", "claude-sonnet-4-6",
            "--dangerously-skip-permissions",
            "--mcp-config",
            str(mcp_config),
            "-p",
            prompt,
        ],
        cwd=str(settings.vault_path.parent),
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT,
        check=False,
        env=env,
    )

    if result.returncode != 0:
        err = result.stderr or "Claude processing failed"
        logger.error("Claude failed: %s", err)
        return f"❌ Ошибка обработки рефлексии: {err[:300]}"

    # Clean output using the same logic as processor.py
    import re
    output = result.stdout.strip()
    if "\n---\n" in output or output.startswith("---\n"):
        lines = output.split("\n")
        seps = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
        if len(seps) >= 2:
            output = "\n".join(lines[seps[0] + 1 : seps[-1]]).strip()
        elif len(seps) == 1:
            idx = seps[0]
            before = "\n".join(lines[:idx]).strip()
            after = "\n".join(lines[idx + 1 :]).strip()
            if re.match(r"^[📅📊✅❌<🧠📝✨💡🎯🪞]", before):
                output = before
            else:
                output = after

    # Strip preamble phrases
    preamble_patterns = [
        r"^Вот сырой HTML для Telegram[:\s]*",
        r"^Вот HTML для Telegram[:\s]*",
        r"^Вот готовый HTML[:\s]*",
        r"^HTML для Telegram[:\s]*",
    ]
    for pattern in preamble_patterns:
        output = re.sub(pattern, "", output, flags=re.IGNORECASE).strip()

    return output


async def main() -> None:
    """Main entry point."""
    settings = get_settings()
    reflection = ReflectionService(settings.vault_path)

    week = reflection.get_pending_week()
    if not week:
        logger.info("No pending reflection — nothing to do.")
        print("No pending reflection.")
        return

    if not reflection.has_content(week):
        logger.info("Reflection for %s is empty — skipping.", week)
        print(f"Reflection for {week} is empty.")
        return

    reflection_path = reflection.get_reflection_path(week)
    summary_path = reflection.get_summary_path(week)

    if not summary_path.exists():
        logger.warning("Weekly summary %s not found — will create standalone reflection.", summary_path)

    logger.info("Finalizing reflection for week %s", week)
    output = finalize_reflection(settings, week, reflection_path, summary_path)

    # Clear flag file
    reflection.clear(week)
    logger.info("Reflection flag cleared.")

    # Commit to git
    git = VaultGit(settings.vault_path)
    try:
        git.commit_and_push(f"chore: reflection {week}")
    except Exception as e:
        logger.warning("Git commit failed: %s", e)

    # Send result to Telegram
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        user_id = settings.allowed_user_ids[0] if settings.allowed_user_ids else None
        if not user_id:
            logger.error("No allowed_user_ids configured")
            print(output)
            return

        try:
            await bot.send_message(chat_id=user_id, text=output)
        except Exception:
            await bot.send_message(chat_id=user_id, text=output, parse_mode=None)

        logger.info("Reflection result sent to user %s", user_id)
        print(output)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
