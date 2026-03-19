---
type: note
title: Phase 3: REFLECT
last_accessed: 2026-03-02
relevance: 0.76
tier: warm
---
# Phase 3: REFLECT

Read execute results. Generate HTML report. Update MEMORY. Write observations. Log to daily.

## Input
- `.session/capture.json` — from Phase 1
- `.session/execute.json` — from Phase 2
- `MEMORY.md` — long-term memory
- `.session/handoff.md` — session context
- `.graph/health-history.json` — vault health trend (if exists)

## Task

### 1. Generate HTML report

Use the template from SKILL.md. Include:

- ONE Big Thing (from capture.json)
- Thoughts saved (from execute.json)
- Tasks created (with IDs)
- Process goals status
- Workload by day
- Vault Health score (from latest health-history.json entry, if exists)
- Top 3 priorities
- Observations (if any)

### 2. Log actions to daily

Append to `daily/{DATE}.md`:

```markdown
## HH:MM [text]
d-brain processing

**Tasks created:** N
- "Task content" (id: XXXX, priority, due)

**Thoughts saved:** M
- [[path/to/thought|Title]] — category

**Links created:** K
- [[from]] ↔ [[to]]
```

### 3. Evolve MEMORY.md

Check if any information from today deserves long-term memory:
- New key decisions
- Changes in Active Context
- New patterns/insights

Rules:
- New info REPLACES outdated (don't append duplicates)
- Only write significant changes

### 4. Capture observations

If problems occurred during processing, append to `.session/handoff.md` under `## Observations`:

```markdown
- [friction] 2026-03-02: mcp timeout on todoist — retried 3x
- [pattern] 2026-03-02: daily had only 2 entries — low activity day
```

### 5. Update handoff.md

Update session context:
- Last Session: what was processed
- Key Decisions: if any
- In Progress: incomplete items

## Output Format

Return RAW HTML report (no markdown, no code blocks). Goes directly to Telegram.

Follow the HTML template exactly:
- Only use: `<b>`, `<i>`, `<code>`, `<s>`, `<u>`, `<a>`
- NO: `<div>`, `<br>`, `<table>`, markdown syntax
- Max 4096 characters

### Vault Health section (add to report if data exists):

```html
<b>📊 Vault Health:</b> {score}/100
Orphans: {N} | Broken: {M} | Avg links: {X}
```


### 6. Update agent_notes.md

Scan all input for signals to improve the agent. Write to `vault/agent/agent_notes.md`.

Create the file with header if it doesn't exist:
```
# Agent Notes — идеи и проблемы для улучшения
```

For each finding, append to today's date section (create if needed: `## YYYY-MM-DD`):

**Раздел "⚠️ Проблемы из рефлексии"** — if user mentioned:
- Bot couldn't find something, failed to respond, gave wrong result
- Format: `- \`[ ]\` **[рефлексия]** description <!-- id: r-YYYYMMDD-NNN -->`

**Раздел "🔄 Идеи агента"** — if user mentioned:
- Would be convenient to automate, want a new command, should remember X
- Also: patterns you noticed (repetitive actions, friction points)
- Format: `- \`[ ]\` **[паттерн]** description <!-- id: a-YYYYMMDD-NNN -->`

**Раздел "🔴 Системные ошибки"** — if LOG_ERRORS is not empty:
- Add brief one-line error summary (only new errors, check if today's date already has entry)
- Format: `- \`[ ]\` **[лог]** error description <!-- id: e-YYYYMMDD-NNN -->`

Rules:
- Only add entries if there's real signal (don't add empty sections)
- NNN = 3-digit sequence within same date (001, 002, ...)
- If agent_notes.md doesn't have today's date section yet — create it

## CRITICAL

- Output is RAW HTML only
- No markdown syntax anywhere
- All HTML tags must be properly closed
