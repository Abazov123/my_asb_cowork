---
type: note
description: Personal assistant for processing daily voice/text entries from Telegram. Classifies content, creates Todoist tasks aligned with goals, saves thoughts to Obsidian with wiki-links, generates HTML reports. 3-phase pipeline (CAPTURE/EXECUTE/REFLECT). Triggers on /process command or daily 23:00 cron.
last_accessed: 2026-03-02
relevance: 0.76
tier: warm
name: second-brain-processor
depends_on: [graph-builder, todoist-ai, agent-memory, vault-health]
---

## Context: Evening Only (23:00)
**This skill runs at 23:00 for EVENING processing of daily entries.**
NOT to be confused with morning-briefer skill (which runs at 07:00).

Report starts with: (emoji) EVENING REPORT — NOT with Доброе утро.


# Second Brain Processor

Process daily entries → tasks (Todoist) + thoughts (Obsidian) + HTML report (Telegram).

## CRITICAL: Output Format

**ALWAYS return RAW HTML. No exceptions. No markdown. Ever.**

Your final output goes directly to Telegram with `parse_mode=HTML`.

Rules:
1. ALWAYS return HTML report — even if entries already processed
2. ALWAYS use the template below — no free-form text
3. NEVER use markdown syntax (**, ##, ```, -)
4. NEVER explain what you did in plain text — put it in HTML report

WRONG:
```html
<b>Title</b>
```

CORRECT:
<b>Title</b>

## Todoist via mcp-cli

**ВСЕГДА используй mcp-cli для Todoist.** Вызывай через Bash tool.

### Базовые команды:

```bash
# Задачи на сегодня (проверка workload)
mcp-cli call todoist find-tasks-by-date '{"startDate": "today"}'

# Задачи на неделю
mcp-cli call todoist find-tasks-by-date '{"startDate": "today", "daysCount": 7}'

# Создать задачу
mcp-cli call todoist add-tasks '{"tasks": [{"content": "Task", "dueString": "tomorrow", "priority": 2}]}'

# Найти задачи по label
mcp-cli call todoist find-tasks '{"labels": ["process-goal"]}'

# Завершить задачи
mcp-cli call todoist complete-tasks '{"ids": ["task_id"]}'

# Обзор
mcp-cli call todoist get-overview '{}'
```

### Приоритеты:
- 1 = p1 (highest)
- 2 = p2 (high)
- 3 = p3 (medium)
- 4 = p4 (default)

## CRITICAL: mcp-cli Usage

**СНАЧАЛА ВЫЗОВИ КОМАНДУ. ПОТОМ ДУМАЙ.**

### Обязательный алгоритм:

```
1. ВЫЗОВИ: mcp-cli call todoist find-tasks-by-date '{"startDate": "today"}'
   ↓
   Получил результат? → Продолжай
   ↓
   Ошибка? → Читай файлы 30 секунд, потом ВЫЗОВИ СНОВА
   ↓
   3 ошибки подряд? → Покажи ТОЧНЫЙ текст ошибки
```

### ЗАПРЕЩЕНО:
- ❌ Писать "Todoist недоступен"
- ❌ Писать "mcp-cli не работает"
- ❌ Предлагать "добавь вручную"
- ❌ Решать что не работает БЕЗ вызова команды

### ОБЯЗАТЕЛЬНО:
- ✅ ВЫЗВАТЬ команду через Bash
- ✅ Если ошибка — подождать, вызвать снова
- ✅ 3 retry перед любыми выводами
- ✅ Показать task ID если создан

При ошибке MCP tool — показать ТОЧНУЮ ошибку от tool, не придумывать отговорки.

## Processing Flow

1. Load context — Read goals/3-weekly.md (ONE Big Thing), goals/2-monthly.md
2. Check workload — find-tasks-by-date for 7 days
3. **Check process goals** — find-tasks with labels: ["process-goal"]
4. Read daily — daily/YYYY-MM-DD.md
5. Process entries — Classify → task or thought
6. Build links — Connect notes with [[wiki-links]]
7. **Log actions to daily** — append action log entry
8. **Evolve MEMORY.md** — update long-term memory if needed
9. **Capture observations** — record friction/patterns/ideas to handoff.md
10. Generate HTML report — RAW HTML for Telegram

### 3-Phase Pipeline (process.sh)
When invoked via process.sh, this skill runs in 3 phases:
- **Phase 1: CAPTURE** — classify entries → JSON (phases/capture.md)
- **Phase 2: EXECUTE** — create tasks, save thoughts → JSON (phases/execute.md)
- **Phase 3: REFLECT** — HTML report + MEMORY update (phases/reflect.md)

## Process Goals Check (Step 3)

**ОБЯЗАТЕЛЬНО выполни при каждом /process:**

### 1. Проверь существующие process goals
Используй mcp__todoist__find-tasks с labels: ["process-goal"]

### 2. Если отсутствуют — создай
Читай goals/ и генерируй process commitments:

| Goal Level | Source | Process Pattern |
|------------|--------|-----------------|
| Weekly ONE Big Thing | goals/3-weekly.md | 2h deep work ежедневно |
| Monthly Top 3 | goals/2-monthly.md | 1 action/день на приоритет |
| Yearly Focus | goals/1-yearly-*.md | 30 мин/день на стратегию |

Создавай recurring tasks с label "process-goal" (max 5-7 активных).

### 3. Включи в отчёт

```html
<b>📋 Process Goals:</b>
• 2h deep work → ✅ активен
• 1 outreach/день → ⚠️ просрочен
{N} активных | {M} требуют внимания
```

See: references/process-goals.md for patterns and examples.

## Logging to daily/ (Step 7)

**После ЛЮБЫХ изменений в vault — СРАЗУ пиши в `daily/YYYY-MM-DD.md`:**

Format:
```
## HH:MM [text]
{Description of actions}

**Created/Updated:**
- [[path/to/file|Name]] — description
```

What to log:
- Files created in thoughts/
- Tasks created in Todoist (with task ID)
- Links built between notes

Example:
```
## 14:30 [text]
Daily processing complete

**Created tasks:** 3
- "Follow-up client" (id: 8501234567, p2, tomorrow)
- "Prepare proposal" (id: 8501234568, p2, friday)

**Saved thoughts:** 1
- [[thoughts/ideas/product-launch|Product Launch]] — new idea
```

## Evolve MEMORY.md (Step 8)

**GOAL:** Keep MEMORY.md current. Don't append — EVOLVE.

### When to update:
- ✅ Key decisions with impact (pivot, tool choice, architecture change)
- ✅ New patterns/insights (learnings)
- ✅ Changes in Active Context (new ONE Big Thing, Hot Projects)

### When NOT to update:
- ❌ Daily trivia (meetings, calls without impact)
- ❌ Temporary notes (stay in daily/)
- ❌ Duplicates of what's already there

### How to update (evolve, not append):

| Situation | Action |
|-----------|--------|
| New contradicts old | REPLACE old information |
| New complements old | Add to existing section |
| Info is outdated | Delete or archive |

Use Edit tool for precise changes.

### In report (if updated):

```html
<b>🧠 MEMORY.md updated:</b>
• Active Context → Hot Projects changed
• Key Decisions → +1 new decision
```

## Entry Format

## HH:MM [type]
Content

Types: [voice], [text], [forward from: Name], [photo]

## Classification

task → Todoist (see references/todoist.md)
idea/reflection/learning → thoughts/ (see references/classification.md)

## Vault Search Before Advice

When an entry contains a question, advice request, or decision about priorities/plans:
1. Run Grep on vault/journal/ and vault/agent/ for key words from the entry
2. If user's own notes found — include them FIRST with source reference
3. Format: `📚 Из твоих записей: «...» (journal/YYYY-MM-DD.md)` then `🤖 Мои мысли: ...`
4. If nothing found — answer normally without forcing it

This keeps AI suggestions grounded in the user's own thinking, not replacing it.

## Priority Rules

p1 — Client deadline, urgent
p2 — Aligns with ONE Big Thing or monthly priority
p3 — Aligns with yearly goal
p4 — Operational, no goal alignment

## Thought Categories

💡 idea → thoughts/ideas/
🪞 reflection → thoughts/reflections/
🎯 project → thoughts/projects/
📚 learning → thoughts/learnings/

## HTML Report Template

Output RAW HTML (no markdown, no code blocks):

📊 <b>Обработка за {DATE}</b>

<b>🎯 Текущий фокус:</b>
{ONE_BIG_THING}

<b>📓 Сохранено мыслей:</b> {N}
• {emoji} {title} → {category}/

<b>✅ Создано задач:</b> {M}
• {task} <i>({priority}, {due})</i>

<b>📋 Process Goals:</b>
• {process goal 1} → {status}
• {process goal 2} → {status}
{N} активных | {M} требуют внимания

<b>📅 Загрузка на неделю:</b>
Пн: {n} | Вт: {n} | Ср: {n} | Чт: {n} | Пт: {n} | Сб: {n} | Вс: {n}

<b>⚠️ Требует внимания:</b>
• {overdue or stale goals}

<b>🔗 Новые связи:</b>
• [[Note A]] ↔ [[Note B]]

<b>⚡ Топ-3 приоритета:</b>
1. {task}
2. {task}
3. {task}

<b>📈 Прогресс:</b>
• {goal}: {%} {emoji}

<b>🧠 MEMORY.md:</b>
• {section} → {change description}
<i>(if updated)</i>

---
<i>Обработано за {duration}</i>

## If Already Processed

If all entries have `<!-- ✓ processed -->` marker, return status report:

📊 <b>Статус за {DATE}</b>

<b>🎯 Текущий фокус:</b>
{ONE_BIG_THING}

<b>📋 Process Goals:</b>
• {process goal 1} → {status}
• {process goal 2} → {status}
{N} активных | {M} требуют внимания

<b>📅 Загрузка на неделю:</b>
Пн: {n} | Вт: {n} | Ср: {n} | Чт: {n} | Пт: {n} | Сб: {n} | Вс: {n}

<b>⚠️ Требует внимания:</b>
• {overdue count} просроченных
• {today count} на сегодня

<b>⚡ Топ-3 приоритета:</b>
1. {task}
2. {task}
3. {task}

---
<i>Записи уже обработаны ранее</i>

## Allowed HTML Tags

<b> — bold (headers)
<i> — italic (metadata)
<code> — commands, paths
<s> — strikethrough
<u> — underline
<a href="url">text</a> — links

## FORBIDDEN in Output

NO markdown: **, ##, -, *, backticks
NO code blocks (triple backticks)
NO tables
NO unsupported tags: div, span, br, p, table

Max length: 4096 characters.

## Capture Observations (Step 9)

**Record friction signals, patterns, and ideas for system improvement.**

After processing, check — were there problems or observations?

| Type | When |
|------|------|
| `[friction]` | MCP errors, timeouts, empty daily, broken links |
| `[pattern]` | Recurring pattern (tasks always overdue, daily empty on weekends) |
| `[idea]` | Improvement idea for pipeline, schema, report |

Append to `.session/handoff.md` under `## Observations`:

```markdown
- [friction] YYYY-MM-DD: MCP timeout 3x on todoist — retry saved
- [pattern] YYYY-MM-DD: daily without entries 2 days — weekend?
- [idea] YYYY-MM-DD: add vault health score to report
```

Rules:
- One line per observation (specific, not abstract)
- Date required
- Don't repeat already recorded observations
- When observations ≥10 → signal for system improvement session

In report (if recorded):

```html
<b>👁 Observations:</b>
• [friction] MCP timeout 3x
```

## Vault Health in Report

If `.graph/health-history.json` exists, add to report:

```html
<b>📊 Vault Health:</b> {score}/100
Orphans: {N} | Broken: {M} | Avg links: {X}
```

## References

Read these files as needed:
- references/about.md — User profile, decision filters
- references/classification.md — Entry classification rules
- references/todoist.md — Task creation details
- references/goals.md — Goal alignment logic
- references/process-goals.md — Process vs outcome goals, transformation patterns
- references/links.md — Wiki-links building
- references/rules.md — Mandatory processing rules
- references/report-template.md — Full HTML report spec
