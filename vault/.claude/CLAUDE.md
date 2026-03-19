---
type: note
title: Agent Second Brain
last_accessed: 2026-03-02
relevance: 0.76
tier: warm
---
# Agent Second Brain

Voice-first personal assistant for capturing thoughts and managing tasks via Telegram.

## EVERY SESSION BOOTSTRAP

**Before doing anything else, read these files in order:**

1. `vault/MEMORY.md` — curated long-term memory (preferences, decisions, context)
2. `vault/daily/YYYY-MM-DD.md` — today's entries
3. `vault/daily/YYYY-MM-DD.md` — yesterday's entries (for continuity)
4. `vault/goals/3-weekly.md` — this week's ONE Big Thing
5. `vault/.session/handoff.md` — session context and observations

**Don't ask permission, just do it.** This ensures context continuity across sessions.

### Memory-Aware Loading
Only auto-load active-tier daily files (today + yesterday). For questions about the past, search warm/cold tier dailies on demand using agent-memory skill.

---

## SESSION END PROTOCOL

**Before ending a significant session, write to today's daily:**

```markdown
## HH:MM [text]
Session summary: [what was discussed/decided/created]
- Key decision: [if any]
- Created: [[link]] [if any files created]
- Next action: [if any]
```

**Also update `vault/MEMORY.md` if:**
- New key decision was made
- User preference discovered
- Important fact learned
- Active context changed significantly

---

## Mission

Help user stay aligned with goals, capture valuable insights, and maintain clarity.

## Directory Structure

| Folder | Purpose |
|--------|---------|
| `daily/` | Raw daily entries (YYYY-MM-DD.md) |
| `goals/` | Goal cascade (3y → yearly → monthly → weekly) |
| `thoughts/` | Processed notes by category |
| `MOC/` | Maps of Content indexes |
| `attachments/` | Photos by date |

## Current Focus

See [[goals/3-weekly]] for this week's ONE Big Thing.
See [[goals/2-monthly]] for monthly priorities.

## Goals Hierarchy

```
goals/0-vision-3y.md    → 3-year vision by life areas
goals/1-yearly-2025.md  → Annual goals + quarterly breakdown
goals/2-monthly.md      → Current month's top 3 priorities
goals/3-weekly.md       → This week's focus + ONE Big Thing
```

## Entry Format

```markdown
## HH:MM [type]
Content
```

Types: `[voice]`, `[text]`, `[forward from: Name]`, `[photo]`

## Processing Workflow

Run daily processing via `/process` command or automatically at 21:00.

### 3-Phase Pipeline:
1. **CAPTURE** — Read daily/, classify entries → JSON (no MCP)
2. **EXECUTE** — Create Todoist tasks, save thoughts, build links → JSON (with MCP)
3. **REFLECT** — Generate HTML report, evolve MEMORY.md, capture observations → HTML (no MCP)

Each phase runs in a fresh Claude context for better quality. Fallback to monolith on capture error.

## Available Skills

| Skill | Purpose |
|-------|---------|
| `dbrain-processor` | Evening processing (23:00) — 3-phase pipeline: classify → execute → reflect |
| `morning-briefer` | Morning briefing (07:00) — weather, news, daily tasks |
| `todoist-ai` | Task management via MCP |
| `graph-builder` | Vault link analysis and building |
| `agent-memory` | Memory management — Ebbinghaus decay, tiered search, creative recall |
| `vault-health` | Vault health monitoring — health score, MOC generation, link repair |

## Available Agents

| Agent | Purpose |
|-------|---------|
| `weekly-digest` | Weekly review with goal progress |
| `goal-aligner` | Check task-goal alignment |
| `note-organizer` | Organize vault, fix links |
| `inbox-processor` | GTD-style inbox processing |

## Path-Specific Rules

See `.claude/rules/` for format requirements:
- `daily-format.md` — daily files format
- `thoughts-format.md` — thought notes format
- `goals-format.md` — goals format
- `telegram-report.md` — HTML report format

## Todoist Access

**Два способа доступа к Todoist (в порядке приоритета):**

1. **mcp-cli** (Bash) — стабильный CLI-прокси, используй в 3-phase pipeline:
   ```bash
   mcp-cli call todoist find-tasks-by-date '{"startDate": "today"}'
   mcp-cli call todoist add-tasks '{"tasks": [{"content": "...", "priority": 2}]}'
   ```

2. **MCP tools** (прямые) — используй при интерактивной работе (/do, /process):
   - `mcp__todoist__add-tasks`
   - `mcp__todoist__find-tasks`
   - `mcp__todoist__find-tasks-by-date`
   - `mcp__todoist__complete-tasks`
   - `mcp__todoist__update-tasks`

## CRITICAL: Tool Usage Policy

**ТЫ ОБЯЗАН вызывать Todoist — через mcp-cli ИЛИ MCP tools.**

ЗАПРЕЩЁННЫЕ ПАТТЕРНЫ (НИКОГДА не делай это):
- "Todoist недоступен"
- "mcp-cli не работает"
- "Добавь вручную: ..."
- Любые инструкции для ручного выполнения

ПРАВИЛЬНЫЙ ПАТТЕРН:
1. Вызвать mcp-cli или MCP tool
2. Ошибка? Retry 3x с паузами (10 сек, 20 сек)
3. Включить результат в HTML отчёт

При ошибке — показать ТОЧНУЮ ошибку, не придумывать отговорки.

## Report Format

Reports use Telegram HTML:
- `<b>bold</b>` for headers
- `<i>italic</i>` for metadata
- Only allowed tags: b, i, code, pre, a

## Quick Commands

| Command | Action |
|---------|--------|
| `/process` | Run daily processing |
| `/do` | Execute arbitrary request |
| `/weekly` | Generate weekly digest |
| `/align` | Check goal alignment |
| `/organize` | Organize vault |
| `/graph` | Analyze vault links |

## /do Command Context

When invoked via /do, Claude receives arbitrary user requests. Common patterns:

**Task Management:**
- "перенеси просроченные задачи на понедельник"
- "покажи задачи на сегодня"
- "добавь задачу: позвонить клиенту"
- "что срочного на этой неделе?"

**Vault Queries:**
- "найди заметки про AI"
- "что я записал сегодня?"
- "покажи итоги недели"

**Combined:**
- "создай задачу из первой записи сегодня"
- "перенеси всё с сегодня на завтра"

## Todoist Tools Available

**Via mcp-cli (Bash) — preferred in scripts:**
```bash
mcp-cli call todoist <tool-name> '<json-args>'
```

**Via MCP (interactive) — mcp__todoist__*:**
- `add-tasks` — создать задачи
- `find-tasks` — найти задачи по тексту
- `find-tasks-by-date` — задачи за период
- `update-tasks` — изменить задачи
- `complete-tasks` — завершить задачи
- `user-info` — информация о пользователе

**Filesystem:**
- Read/write vault files
- Access daily/, goals/, thoughts/

## Customization

For personal overrides: create `CLAUDE.local.md`

## Agent Memory

Memory system with automatic Ebbinghaus decay, tiered search, and creative recall.
- `python3 .claude/skills/agent-memory/scripts/memory-engine.py scan .` — analyze vault
- `memory-engine.py decay .` — update relevance scores (runs daily in process.sh)
- `memory-engine.py touch <file>` — reset file to active on meaningful read
- `memory-engine.py creative 5 .` — random cold/archive cards for brainstorming

Tiers: `core` (manual, never forgets) → `active` (≤7d) → `warm` (≤21d) → `cold` (≤60d) → `archive`

## Vault Health

Monitoring knowledge graph quality:
- `uv run .claude/skills/vault-health/scripts/generate_moc.py` — regenerate MOC indexes
- `bash .claude/skills/vault-health/scripts/backlinks.sh "path"` — find incoming links
- `uv run .claude/skills/vault-health/scripts/fix_links.py` — find and fix broken links

Health score tracked in `.graph/health-history.json`. Observations logged in `.session/handoff.md`.

## Graph Builder

Analyze and maintain vault link structure. Use `/graph` command or invoke `graph-builder` skill.

**Commands:**
- `/graph analyze` — Full vault statistics
- `/graph orphans` — List unconnected notes
- `/graph suggest` — Get link suggestions
- `/graph add` — Apply suggested links

**Scripts:**
- `uv run .claude/skills/graph-builder/scripts/analyze.py` — Graph analysis
- `uv run .claude/skills/graph-builder/scripts/add_links.py` — Link suggestions

See `skills/graph-builder/` for full documentation.

## Learnings (from experience)

1. **Don't rewrite working code** without reason (KISS, DRY, YAGNI)
2. **Don't add checks** that weren't there — let the agent decide
3. **Don't propose solutions** without studying git log/diff first
4. **Don't break architecture** (process.sh → Claude → skill is correct)
5. **Problems are usually simple** (e.g., sed one-liner for HTML fix)

---

*System Version: 3.0*
*Updated: 2026-03-02*
