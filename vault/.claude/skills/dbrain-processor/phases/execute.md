---
type: note
title: Phase 2: EXECUTE
last_accessed: 2026-03-02
relevance: 0.76
tier: warm
---
# Phase 2: EXECUTE

Read capture.json from Phase 1. Create Todoist tasks, save thoughts, build links.

## Input
- `.session/capture.json` — output from Phase 1

## Todoist via mcp-cli

**ALWAYS use mcp-cli for Todoist.** Call via Bash tool.

### Commands:

```bash
# Today's tasks (check workload)
mcp-cli call todoist find-tasks-by-date '{"startDate": "today"}'

# Tasks for 7 days
mcp-cli call todoist find-tasks-by-date '{"startDate": "today", "daysCount": 7}'

# Create task
mcp-cli call todoist add-tasks '{"tasks": [{"content": "Task", "dueString": "tomorrow", "priority": 2}]}'

# Find tasks by label
mcp-cli call todoist find-tasks '{"labels": ["process-goal"]}'

# Complete tasks
mcp-cli call todoist complete-tasks '{"ids": ["task_id"]}'
```

### Priorities:
- 1 = p1 (highest)
- 2 = p2 (high)
- 3 = p3 (medium)
- 4 = p4 (default)

## Task

### 1. Create Todoist tasks

For each entry with `classification: "task"`:

```bash
mcp-cli call todoist add-tasks '{"tasks": [{"content": "...", "dueString": "...", "priority": N}]}'
```

Record created task IDs.

### 2. Check process goals

```bash
mcp-cli call todoist find-tasks '{"labels": ["process-goal"]}'
```

If missing or stale → create from goals.

### 3. Save thoughts

For each entry with classification idea/reflection/learning/project:
- Create file in `thoughts/{category}/YYYY-MM-DD-slug.md`
- Include frontmatter with description field (retrieval filter, ~150 chars)
- Add wiki-links to related entities
- Add typed relationships in Related section:
  ```markdown
  ## Related
  - [[thoughts/ideas/some-note|Title]] — context: discussed during processing
  ```

### 4. Build links

For all created/updated files:
- Search for related notes in vault
- Add wiki-links with context phrases

### 5. Check workload

```bash
mcp-cli call todoist find-tasks-by-date '{"startDate": "today", "daysCount": 7}'
```

## mcp-cli retry algorithm

```
1. Call mcp-cli
2. Error? Wait 10 sec, read vault files
3. Call again
4. Error? Wait 20 sec
5. Third call — GUARANTEED to work
```

NEVER say "mcp-cli unavailable". Always retry 3x.

## Output Format

Print ONLY valid JSON:

```json
{
  "tasks_created": [
    {"id": "8501234567", "content": "Follow-up task", "priority": 2, "due": "tomorrow"}
  ],
  "thoughts_saved": [
    {"path": "thoughts/ideas/2026-03-02-layered-memory.md", "title": "AI agents need layered memory", "category": "ideas"}
  ],
  "links_created": [
    {"from": "thoughts/ideas/2026-03-02-layered-memory.md", "to": "goals/3-weekly.md", "context": "supports weekly focus"}
  ],
  "process_goals": {
    "active": 5,
    "overdue": 1,
    "created": 0
  },
  "workload": {
    "mon": 3, "tue": 2, "wed": 4, "thu": 1, "fri": 2, "sat": 0, "sun": 0
  },
  "observations": []
}
```
