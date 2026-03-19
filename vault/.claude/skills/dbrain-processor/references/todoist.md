---
type: note
title: Todoist Integration
last_accessed: 2026-01-01
relevance: 1.0
tier: core
---
# Todoist Integration

<!--
  КАК НАСТРОИТЬ: Откройте Todoist и скопируйте названия/ID проектов.
  Замените примеры ниже на свои. Удалите этот комментарий после настройки.
-->

## Project Structure

| Project | ID | Notes |
|---------|-----|-------|
| Inbox | [your-inbox-id] | Default fallback |
| Work | [your-work-id] | Work tasks |
| Personal | [your-personal-id] | Personal tasks |

## Available MCP Tools

### Reading Tasks
- `get-overview` — all projects with hierarchy
- `find-tasks` — search by text, project, section
- `find-tasks-by-date` — tasks by date range

### Writing Tasks
- `add-tasks` — create new tasks
- `complete-tasks` — mark as done
- `update-tasks` — modify existing

## Pre-Creation Checklist

### 1. Check Workload (REQUIRED)
```
find-tasks-by-date:
  startDate: "today"
  daysCount: 7
  limit: 50
```
Build workload map. If day has 3+ tasks — shift to next free day.

### 2. Check Duplicates (REQUIRED)
```
find-tasks:
  searchText: "key words from new task"
```
If similar exists → mark as duplicate, don't create.

## Project Detection Rules

### Work ([your-work-id])
Keywords: [имена коллег], [названия проектов], рабочий, встреча, офис

### Personal ([your-personal-id])
Keywords: досуг, здоровье, спорт, хобби, книга, личное развитие

### Inbox fallback
Use when no clear project match. Better Inbox than wrong project.

## Priority Rules

| Situation | Priority |
|-----------|----------|
| Work + deadline / urgent | p1 |
| Work + strategic alignment | p2 |
| Work + regular operations | p3 |
| Personal | p4 |

## Date Mapping

| Russian | dueString |
|---------|-----------|
| сегодня | today |
| завтра | tomorrow |
| в понедельник | monday |
| на этой неделе | friday |
| на следующей неделе | next monday |
| через неделю | in 7 days |
| не указано | in 3 days |

## Task Title Style

Direct, specific, actionable.

Good: "Отправить презентацию [имя]", "Записаться к врачу"
Bad: "Подумать о презентации", "Что-то по работе"

## Workload Balancing

If target day has 3+ tasks:
1. Find next day with fewer
2. Use that day instead
3. Mention: "сдвинуто на [day] (перегрузка)"

## Error Handling

CRITICAL: Never suggest "добавь вручную".
If add-tasks fails: include EXACT error, continue, don't mark as processed.
