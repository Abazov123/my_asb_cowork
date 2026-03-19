---
type: note
title: Phase 1: CAPTURE
last_accessed: 2026-03-02
relevance: 0.76
tier: warm
---
# Phase 1: CAPTURE

Read daily entries, classify them, and output structured JSON.

## Input
- `daily/{DATE}.md` — today's entries
- `goals/3-weekly.md` — current week focus
- `goals/2-monthly.md` — monthly priorities
- `goals/1-yearly-2026.md` — yearly goals

## Task

1. Read `daily/{DATE}.md`
2. For each entry (## HH:MM [type] block), classify:
   - **task** — actionable item → will become Todoist task
   - **idea** → will be saved to thoughts/ideas/
   - **reflection** → thoughts/reflections/
   - **learning** → thoughts/learnings/
   - **project** → thoughts/projects/
   - **skip** — already processed or not actionable
3. Detect entity mentions (people, projects)
4. Align with goals (which goal does this serve?)

## Output Format

Print ONLY valid JSON (no markdown, no explanation):

```json
{
  "date": "2026-03-02",
  "one_big_thing": "Current ONE Big Thing from goals/3-weekly.md",
  "entries": [
    {
      "time": "10:30",
      "type": "voice",
      "content": "Original entry text",
      "classification": "task",
      "task_content": "Follow-up: send report",
      "task_priority": 2,
      "task_due": "tomorrow",
      "entities": [],
      "goal_alignment": "ONE Big Thing"
    },
    {
      "time": "14:00",
      "type": "text",
      "content": "AI agents need layered memory",
      "classification": "idea",
      "title": "AI agents need layered memory with decay scoring",
      "description": "Pattern from analysis. Active memories decay if unused.",
      "category": "ideas",
      "tags": ["ai", "agents", "memory"],
      "entities": [],
      "goal_alignment": "yearly/AI Development"
    }
  ],
  "stats": {
    "total_entries": 5,
    "tasks": 2,
    "thoughts": 2,
    "skipped": 0
  }
}
```

## Classification Rules

### Task indicators
- "нужно", "надо", "сделать", "позвонить", "отправить", "подготовить"
- Deadline mentions (завтра, в пятницу, до конца недели)
- Follow-up mentions

### Thought indicators
- Insights, patterns, observations
- "понял что", "интересно что", "заметил"
- No clear action required

### Process goal formulation
When creating task_content, prefer PROCESS over OUTCOME:
- WRONG: "Закрыть сделку"
- RIGHT: "Отправить follow-up: KPI отчёт за февраль"

### Prose-as-title for thoughts
When creating thought titles, use CLAIMS not topic labels:
- WRONG: "Agent Memory System" (topic label)
- RIGHT: "AI agents need layered memory with decay scoring" (specific claim)
Test: "Since [[title]], ..." should read naturally.

## Important
- Mark entries with `<!-- ✓ processed -->` as "skip"
- Output ONLY JSON — no explanation, no markdown wrapping
