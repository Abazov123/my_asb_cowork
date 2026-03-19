"""Handler for /improve and /concepts commands — interactive agent improvement review."""

import asyncio
import json
import logging
import re
import subprocess
from datetime import date
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from d_brain.config import get_settings

router = Router(name="improve")
logger = logging.getLogger(__name__)


class ImproveCB(CallbackData, prefix="improve"):
    action: str   # "accept" | "reject" | "later"
    note_id: str  # id from agent_notes.md, e.g. "n-20260313-001"


class ConceptCB(CallbackData, prefix="concept"):
    action: str   # "run" | "explain" | "later" | "cancel" | "done"
    note_id: str  # e.g. "n-20260313-001"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_proposals(vault_path: Path) -> list[dict]:
    """Ask Claude to read agent_notes.md and return top-5 unreviewed proposals as JSON."""
    notes_path = vault_path / "agent" / "agent_notes.md"
    if not notes_path.exists():
        return []

    notes_content = notes_path.read_text(encoding="utf-8")
    # Only look at [ ] items (unreviewed)
    if "[ ]" not in notes_content:
        return []

    prompt = (
        "Прочитай agent_notes.md и верни JSON-список топ-5 нерассмотренных предложений "
        "(только со статусом `[ ]`). Приоритет: 🔴 ошибки > ⚠️ проблемы > 🔄 паттерны > 💡 идеи.\n\n"
        "Формат — JSON массив, ТОЛЬКО JSON без markdown:\n"
        '[{"id":"n-20260313-001","title":"Краткое название","desc":"Описание","effort":"малый|средний|большой",'
        '"type":"error|issue|pattern|idea"}]\n\n'
        f"Содержимое agent_notes.md:\n{notes_content}"
    )

    try:
        result = subprocess.run(
            ["claude", "--print", "--dangerously-skip-permissions",
             "--model", "claude-haiku-4-5-20251001", "-p", prompt],
            capture_output=True, text=True, timeout=60,
            cwd=str(vault_path.parent), check=False,
        )
        if result.returncode != 0:
            logger.error("Claude proposals failed: %s", result.stderr[:200])
            return []
        output = result.stdout.strip()
        # Strip markdown fences if present
        if "```" in output:
            output = re.sub(r"```(?:json)?\s*", "", output).strip().rstrip("`").strip()
        return json.loads(output)
    except Exception as e:
        logger.error("Failed to get proposals: %s", e)
        return []


def _get_concepts(vault_path: Path) -> list[dict]:
    """Read agent_notes.md and return all [⏳] (concept-ready) items."""
    notes_path = vault_path / "agent" / "agent_notes.md"
    if not notes_path.exists():
        return []
    concepts = []
    content = notes_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        if "`[⏳]`" not in line:
            continue
        # Extract note_id
        m_id = re.search(r"<!-- id: ([\w-]+) -->", line)
        if not m_id:
            continue
        note_id = m_id.group(1)
        # Extract concept file path (appended by night_implement.sh)
        m_file = re.search(r"\| файл: (vault/agent/concepts/\S+\.md)", line)
        concept_file = m_file.group(1) if m_file else None
        # Extract title: text before the <!-- id: --> comment
        clean = re.sub(r"\s*<!--.*?-->.*$", "", line)             # strip id comment + tail
        clean = re.sub(r"^[-\s]*`\[⏳\]`\s*", "", clean)          # strip status prefix
        clean = re.sub(r"\s*\([^)]*https?://[^)]*\)\s*", "", clean)  # strip (url)
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)          # strip **bold**
        clean = clean.strip()
        if len(clean) > 80:
            clean = clean[:80].rsplit(" ", 1)[0] + "…"
        title = clean if clean else note_id
        concepts.append({
            "note_id": note_id,
            "title": title,
            "concept_file": concept_file,
        })
    return concepts


def _parse_concept_doc(vault_path: Path, concept_file: str | None) -> dict:
    """Parse concept doc: returns brief_desc, auto_implementable, complexity_reason."""
    if not concept_file:
        return {"brief_desc": "", "auto_implementable": False, "complexity_reason": ""}
    doc_path = vault_path.parent / concept_file
    if not doc_path.exists():
        return {"brief_desc": "", "auto_implementable": False, "complexity_reason": ""}
    try:
        content = doc_path.read_text(encoding="utf-8")
        # Extract brief description from "## Что это" section
        m_desc = re.search(r"## Что это\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        brief_desc = m_desc.group(1).strip()[:250] if m_desc else ""
        # Check auto_implementable
        auto_implementable = "**Автоматически:** Да" in content
        # Extract complexity reason
        m_reason = re.search(r"\*\*Если нет — почему:\*\*\s*(.+?)(?=\n\n|\n#|\Z)", content, re.DOTALL)
        complexity_reason = m_reason.group(1).strip() if m_reason else ""
        return {
            "brief_desc": brief_desc,
            "auto_implementable": auto_implementable,
            "complexity_reason": complexity_reason,
        }
    except Exception as e:
        logger.error("Failed to parse concept doc %s: %s", concept_file, e)
        return {"brief_desc": "", "auto_implementable": False, "complexity_reason": ""}


def _verify_concept_implemented(vault_path: Path, concept_file: str) -> dict:
    """Check if concept is already implemented by reading the target file and asking Claude Haiku.

    Returns {"implemented": bool, "confidence": "high"|"medium"|"low", "reason": str}.
    """
    doc_path = vault_path.parent / concept_file
    if not doc_path.exists():
        return {"implemented": False, "confidence": "low", "reason": ""}
    try:
        content = doc_path.read_text(encoding="utf-8")
        # Find target file mentioned in concept doc
        m_file = re.search(r"src/d_brain/\S+\.py", content)
        if not m_file:
            m_file = re.search(r"vault/\.claude/\S+\.md", content)
        target_file = m_file.group(0) if m_file else None
        if not target_file:
            return {"implemented": False, "confidence": "low", "reason": ""}
        target_path = vault_path.parent / target_file
        if not target_path.exists():
            return {"implemented": False, "confidence": "low", "reason": ""}
        target_content = target_path.read_text(encoding="utf-8")
        # Extract implementation spec
        m_spec = re.search(r"## Как реализовать\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        spec = m_spec.group(1).strip()[:600] if m_spec else content[:400]
        prompt = (
            f"Проверь: реализовано ли это улучшение в коде?\n\n"
            f"Что должно быть реализовано:\n{spec}\n\n"
            f"Текущий код файла {target_file}:\n{target_content[:2500]}\n\n"
            f"Ответь ТОЛЬКО JSON без markdown:\n"
            f'{"implemented": true/false, "confidence": "high/medium/low", "reason": "одно предложение по-русски"}'
        )
        result = subprocess.run(
            ["claude", "--print", "--dangerously-skip-permissions",
             "--model", "claude-haiku-4-5-20251001", "-p", prompt],
            capture_output=True, text=True, timeout=25,
            cwd=str(vault_path.parent), check=False,
        )
        output = result.stdout.strip()
        if "```" in output:
            output = re.sub(r"```(?:json)?\s*", "", output).strip().rstrip("`").strip()
        data = json.loads(output)
        return {
            "implemented": bool(data.get("implemented")),
            "confidence": data.get("confidence", "low"),
            "reason": data.get("reason", ""),
        }
    except Exception as e:
        logger.debug("Verification skipped for %s: %s", concept_file, e)
        return {"implemented": False, "confidence": "low", "reason": ""}


async def _verify_and_notify(message: Message, vault_path: Path, concepts: list[dict]) -> None:
    """Background: verify each concept in parallel and notify user about already-implemented ones."""
    verifiable = [c for c in concepts if c.get("concept_file")]
    if not verifiable:
        return

    results = await asyncio.gather(
        *[asyncio.to_thread(_verify_concept_implemented, vault_path, c["concept_file"])
          for c in verifiable],
        return_exceptions=True,
    )

    found = []
    for c, result in zip(verifiable, results):
        if isinstance(result, Exception):
            continue
        if result.get("implemented") and result.get("confidence") in ("high", "medium"):
            found.append((c, result))

    if not found:
        return

    lines = []
    for c, result in found:
        icon = "🟢" if result["confidence"] == "high" else "🟡"
        lines.append(f"{icon} <b>{c['title']}</b>\n   {result['reason']}")

    text = (
        "🔍 <b>Авто-проверка нашла реализованные идеи:</b>\n\n"
        + "\n\n".join(lines)
        + "\n\n→ Нажми <b>✅ Уже готово</b> на соответствующей карточке выше."
    )
    try:
        await message.answer(text)
    except Exception as e:
        logger.error("Failed to send verification result: %s", e)


def _update_note_status(vault_path: Path, note_id: str, new_status: str) -> bool:
    """Find line with <!-- id: {note_id} --> and replace status prefix."""
    notes_path = vault_path / "agent" / "agent_notes.md"
    if not notes_path.exists():
        return False
    try:
        content = notes_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        updated = False
        for i, line in enumerate(lines):
            if f"<!-- id: {note_id} -->" in line:
                lines[i] = re.sub(r"`\[.*?\]`", f"`{new_status}`", line)
                updated = True
                break
        if updated:
            notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            logger.info("Updated note %s → %s", note_id, new_status)
        else:
            logger.warning("Note %s not found in agent_notes.md", note_id)
        return updated
    except Exception as e:
        logger.error("Failed to update note status: %s", e)
        return False


def _append_to_upgrade_history(
    vault_path: Path, title: str, what_changed: str, concept_file: str | None
) -> None:
    """Append implemented concept entry to vault/agent/upgrade_history.md."""
    history_path = vault_path / "agent" / "upgrade_history.md"
    today = date.today().isoformat()
    file_ref = f" ([концепт]({concept_file}))" if concept_file else ""
    if what_changed:
        entry = f"- {today} · **{title}** — {what_changed}{file_ref}\n"
    else:
        entry = f"- {today} · **{title}**{file_ref}\n"
    try:
        if history_path.exists():
            content = history_path.read_text(encoding="utf-8")
        else:
            content = "# История улучшений бота\n\n"
        history_path.write_text(content.rstrip("\n") + "\n" + entry, encoding="utf-8")
        logger.info("Appended to upgrade_history: %s", title)
    except Exception as e:
        logger.error("Failed to append to upgrade_history: %s", e)


def _count_statuses(vault_path: Path, note_ids: list[str]) -> dict[str, int]:
    """Count accept/reject/later decisions for given note IDs."""
    notes_path = vault_path / "agent" / "agent_notes.md"
    if not notes_path.exists():
        return {}
    content = notes_path.read_text(encoding="utf-8")
    counts = {"accept": 0, "reject": 0, "later": 0, "pending": 0}
    for note_id in note_ids:
        for line in content.splitlines():
            if f"<!-- id: {note_id} -->" in line:
                if "`[→]`" in line:
                    counts["accept"] += 1
                elif "`[❌]`" in line:
                    counts["reject"] += 1
                elif "`[⏳]`" in line:
                    counts["later"] += 1
                else:
                    counts["pending"] += 1
                break
    return counts


def _all_reviewed(vault_path: Path, note_ids: list[str]) -> bool:
    """Check if all given note IDs have been reviewed (no [ ] remaining)."""
    counts = _count_statuses(vault_path, note_ids)
    return counts.get("pending", 0) == 0


def _write_pattern_to_notes(vault_path: Path, pattern: str) -> None:
    """Append pattern analysis line to agent_notes.md."""
    notes_path = vault_path / "agent" / "agent_notes.md"
    try:
        content = notes_path.read_text(encoding="utf-8")
        marker = f"_reviewed: {date.today().isoformat()}_"
        content = content.rstrip() + f"\n\n---\n{marker}\n_{pattern}_\n"
        notes_path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.error("Failed to write pattern: %s", e)


def _append_to_memory(vault_path: Path, pattern: str) -> None:
    """Append preference pattern to vault/MEMORY.md."""
    memory_path = vault_path / "MEMORY.md"
    try:
        content = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
        section = "\n## Предпочтения по доработкам агента\n"
        entry = f"- {date.today().isoformat()}: {pattern}\n"
        if "## Предпочтения по доработкам агента" in content:
            content = content.replace(
                "## Предпочтения по доработкам агента\n",
                f"## Предпочтения по доработкам агента\n{entry}",
            )
        else:
            content = content.rstrip() + section + entry
        memory_path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.error("Failed to write to MEMORY.md: %s", e)


async def _finalize_improve_session(
    message: Message, vault_path: Path, note_ids: list[str]
) -> None:
    """Send summary and write learning pattern after all proposals reviewed."""
    counts = _count_statuses(vault_path, note_ids)
    summary = (
        f"📊 <b>Итог сессии /improve</b>\n\n"
        f"→ Внедрить: {counts['accept']} · "
        f"❌ Пропустить: {counts['reject']} · "
        f"⏳ Позже: {counts['later']}"
    )
    await message.answer(summary)

    notes_path = vault_path / "agent" / "agent_notes.md"
    notes_content = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""

    prompt = (
        f"Пользователь рассмотрел предложения по улучшению агента.\n"
        f"Принято: {counts['accept']}, отклонено: {counts['reject']}, отложено: {counts['later']}.\n"
        f"Вот текущий agent_notes.md:\n{notes_content[:3000]}\n\n"
        "Сформулируй ONE строку (до 120 символов) — паттерн предпочтений пользователя: "
        "какие типы улучшений он принимает, какие отклоняет, что это говорит о его приоритетах. "
        "Только строку, без JSON и markdown."
    )

    try:
        result = await asyncio.to_thread(
            lambda: subprocess.run(
                ["claude", "--print", "--dangerously-skip-permissions",
                 "--model", "claude-haiku-4-5-20251001", "-p", prompt],
                capture_output=True, text=True, timeout=45,
                cwd=str(vault_path.parent), check=False,
            )
        )
        pattern = result.stdout.strip()[:150] if result.returncode == 0 else ""
    except Exception:
        pattern = ""

    if pattern:
        await asyncio.to_thread(_write_pattern_to_notes, vault_path, pattern)
        await asyncio.to_thread(_append_to_memory, vault_path, pattern)
        await message.answer(f"🧠 <b>Паттерн записан:</b>\n<i>{pattern}</i>")


# ── Session state ─────────────────────────────────────────────────────────────

# Store active session note_ids per chat_id (in-memory, single user)
_active_sessions: dict[int, list[str]] = {}


# ── /improve handlers ─────────────────────────────────────────────────────────

@router.message(Command("improve"))
async def cmd_improve(message: Message) -> None:
    """Handle /improve — interactive agent improvement review."""
    settings = get_settings()
    vault_path = settings.vault_path

    msg = await message.answer("🔧 Анализирую agent_notes.md...")
    proposals = await asyncio.to_thread(_get_proposals, vault_path)

    try:
        await msg.delete()
    except Exception:
        pass

    if not proposals:
        await message.answer(
            "✅ <b>Нет нерассмотренных предложений.</b>\n\n"
            "Предложения накапливаются из:\n"
            "• 📰 Утренних новостей\n"
            "• 🔄 Дневной рефлексии\n"
            "• 🔴 Системных логов\n"
            "Загляни завтра после утреннего разбора!"
        )
        return

    chat_id = message.chat.id
    _active_sessions[chat_id] = [p["id"] for p in proposals]

    await message.answer(
        f"🔧 <b>Предложения по улучшению агента</b> — {len(proposals)} шт.\n"
        "Рассмотри каждое:"
    )

    for p in proposals:
        p_type = p.get("type", "idea")
        emoji = "🔴" if p_type == "error" else "⚠️" if p_type == "issue" else "🔄" if p_type == "pattern" else "💡"
        effort = p.get("effort", "неизвестно")
        text = (
            f"{emoji} <b>{p['title']}</b>\n"
            f"{p.get('desc', '')}\n"
            f"Усилия: {effort}"
        )
        note_id = p["id"]
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="→ Внедрить",
                callback_data=ImproveCB(action="accept", note_id=note_id).pack(),
            ),
            InlineKeyboardButton(
                text="❌ Пропустить",
                callback_data=ImproveCB(action="reject", note_id=note_id).pack(),
            ),
            InlineKeyboardButton(
                text="⏳ Позже",
                callback_data=ImproveCB(action="later", note_id=note_id).pack(),
            ),
        ]])
        await message.answer(text, reply_markup=kb)


@router.callback_query(ImproveCB.filter())
async def _on_improve(query: CallbackQuery, callback_data: ImproveCB) -> None:
    """Handle improve decision buttons."""
    settings = get_settings()
    vault_path = settings.vault_path
    action = callback_data.action
    note_id = callback_data.note_id

    status_map = {"accept": "[→]", "reject": "[❌]", "later": "[⏳]"}
    label_map = {"accept": "→ принято к внедрению", "reject": "❌ пропущено", "later": "⏳ отложено"}

    await asyncio.to_thread(_update_note_status, vault_path, note_id, status_map[action])

    original_text = query.message.text or query.message.html_text or ""
    new_text = original_text + f"\n\n{label_map[action]}"
    try:
        await query.message.edit_text(new_text, reply_markup=None)
    except Exception:
        pass
    await query.answer(label_map[action])

    chat_id = query.message.chat.id
    note_ids = _active_sessions.get(chat_id, [])
    if note_ids and _all_reviewed(vault_path, note_ids):
        del _active_sessions[chat_id]
        await _finalize_improve_session(query.message, vault_path, note_ids)


# ── /concepts handlers ────────────────────────────────────────────────────────

@router.message(Command("concepts"))
async def cmd_concepts(message: Message) -> None:
    """Handle /concepts — interactive review of concept-ready ideas."""
    settings = get_settings()
    vault_path = settings.vault_path

    concepts = await asyncio.to_thread(_get_concepts, vault_path)

    if not concepts:
        await message.answer(
            "✅ <b>Нет идей на рассмотрении.</b>\n\n"
            "Концепты появляются когда ночной агент находит сложную идею,\n"
            "которую нельзя реализовать автоматически.\n\n"
            "Используй /improve чтобы добавить новые идеи в очередь."
        )
        return

    await message.answer(
        f"💡 <b>Идеи на рассмотрении</b> — {len(concepts)} шт.\n"
        "Выбери что сделать с каждой:"
    )

    for c in concepts:
        note_id = c["note_id"]
        title = c["title"]
        concept_file = c.get("concept_file")

        info = await asyncio.to_thread(_parse_concept_doc, vault_path, concept_file)
        auto = info["auto_implementable"]

        file_line = f"\n📄 <code>{concept_file}</code>" if concept_file else ""
        desc_line = f"\n\n{info['brief_desc']}" if info["brief_desc"] else ""
        text = f"💡 <b>Идея на рассмотрении</b>\n\n<b>{title}</b>{desc_line}{file_line}"

        if auto:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚀 Внедрить сейчас",
                        callback_data=ConceptCB(action="run", note_id=note_id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="⏳ Отложить",
                        callback_data=ConceptCB(action="later", note_id=note_id).pack(),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Уже готово",
                        callback_data=ConceptCB(action="done", note_id=note_id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="❌ Отменить",
                        callback_data=ConceptCB(action="cancel", note_id=note_id).pack(),
                    ),
                ],
            ])
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ℹ️ Почему сложно",
                        callback_data=ConceptCB(action="explain", note_id=note_id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="⏳ Отложить",
                        callback_data=ConceptCB(action="later", note_id=note_id).pack(),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Уже готово",
                        callback_data=ConceptCB(action="done", note_id=note_id).pack(),
                    ),
                    InlineKeyboardButton(
                        text="❌ Отменить",
                        callback_data=ConceptCB(action="cancel", note_id=note_id).pack(),
                    ),
                ],
            ])
        await message.answer(text, reply_markup=kb)

    # Background auto-verification — runs after cards are shown
    asyncio.create_task(_verify_and_notify(message, vault_path, concepts))


@router.callback_query(ConceptCB.filter())
async def _on_concept(query: CallbackQuery, callback_data: ConceptCB) -> None:
    """Handle concept decision buttons."""
    settings = get_settings()
    vault_path = settings.vault_path
    action = callback_data.action
    note_id = callback_data.note_id

    original_text = query.message.text or query.message.html_text or ""

    # Load concept info once for actions that need it
    if action in ("run", "done", "explain"):
        concepts = await asyncio.to_thread(_get_concepts, vault_path)
        concept_entry = next((c for c in concepts if c["note_id"] == note_id), None)
        concept_file = concept_entry["concept_file"] if concept_entry else None
        title = concept_entry["title"] if concept_entry else note_id
    else:
        concept_file = None
        title = note_id

    if action == "cancel":
        await asyncio.to_thread(_update_note_status, vault_path, note_id, "[❌]")
        try:
            await query.message.edit_text(
                original_text + "\n\n❌ <b>Идея отменена.</b>",
                reply_markup=None,
            )
        except Exception:
            pass
        await query.answer("Идея отменена")

    elif action == "later":
        try:
            await query.message.edit_text(
                original_text + "\n\n⏳ <b>Отложено.</b> Найдёшь в /concepts когда будешь готов.",
                reply_markup=None,
            )
        except Exception:
            pass
        await query.answer("Отложено")

    elif action == "done":
        await asyncio.to_thread(_update_note_status, vault_path, note_id, "[✅]")
        await asyncio.to_thread(
            _append_to_upgrade_history, vault_path, title, "реализовано вручную", concept_file
        )
        try:
            await query.message.edit_text(
                original_text + "\n\n✅ <b>Отмечено как реализованное.</b>\nДобавлено в историю улучшений.",
                reply_markup=None,
            )
        except Exception:
            pass
        await query.answer("Отмечено как готово")

    elif action == "explain":
        info = await asyncio.to_thread(_parse_concept_doc, vault_path, concept_file)
        reason = info.get("complexity_reason", "")
        file_code = (
            f"\n\nЧтобы реализовать вручную, открой в терминале:\n<code>claude {concept_file}</code>"
            if concept_file else ""
        )
        explain_text = (
            f"ℹ️ <b>Почему это нельзя реализовать автоматически:</b>\n\n{reason}{file_code}"
            if reason else
            f"ℹ️ Эта идея слишком сложна для автоматической реализации.{file_code}"
        )
        try:
            await query.message.edit_text(
                explain_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Уже готово",
                            callback_data=ConceptCB(action="done", note_id=note_id).pack(),
                        ),
                        InlineKeyboardButton(
                            text="⏳ Отложить",
                            callback_data=ConceptCB(action="later", note_id=note_id).pack(),
                        ),
                        InlineKeyboardButton(
                            text="❌ Отменить",
                            callback_data=ConceptCB(action="cancel", note_id=note_id).pack(),
                        ),
                    ]
                ]),
            )
        except Exception:
            pass
        await query.answer()

    elif action == "run":
        try:
            await query.message.edit_text(
                f"🔨 <b>Запускаю внедрение...</b>\n\n<b>{title}</b>",
                reply_markup=None,
            )
        except Exception:
            pass
        await query.answer("Запускаю...")

        if not concept_file:
            await query.message.answer("⚠️ Не найден файл концепта. Попробуй /concepts снова.")
            return

        project_dir = vault_path.parent
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash", "scripts/night_implement_single.sh", note_id, concept_file,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            result_str = stdout.decode().strip()
        except asyncio.TimeoutError:
            result_str = "FAILED: превышено время ожидания (5 минут)"
        except Exception as e:
            result_str = f"FAILED: ошибка запуска — {e}"

        if result_str.startswith("DONE:"):
            what = result_str[5:].strip()
            await asyncio.to_thread(_update_note_status, vault_path, note_id, "[✅]")
            await asyncio.to_thread(
                _append_to_upgrade_history, vault_path, title, what, concept_file
            )
            try:
                await query.message.edit_text(
                    f"✅ <b>Готово!</b>\n{what}",
                    reply_markup=None,
                )
            except Exception:
                await query.message.answer(f"✅ <b>Готово!</b>\n{what}")
        else:
            reason = result_str[7:].strip() if result_str.startswith("FAILED:") else result_str
            file_code = (
                f"\n\nЧтобы реализовать вручную:\n<code>claude {concept_file}</code>"
                if concept_file else ""
            )
            try:
                await query.message.edit_text(
                    f"⚠️ <b>Не получилось:</b>\n{reason}{file_code}",
                    reply_markup=None,
                )
            except Exception:
                await query.message.answer(f"⚠️ <b>Не получилось:</b>\n{reason}{file_code}")
