---
type: note
description: Reads vault/agent/agent_notes.md, analyzes last 7 days entries, proposes top improvements
last_accessed: 2026-03-13
relevance: 0.93
tier: active
name: agent-improver
---

# Agent Improver

Analyzes accumulated agent notes and produces a prioritized list of improvements.

## When to use

- Called by `/improve` bot command (via Claude subprocess)
- Called by Sunday `improve_agent.sh` timer for weekly reminder
- Can be called manually for ad-hoc analysis

## Input

Read `vault/agent/agent_notes.md` — all entries with `[ ]` status (unreviewed).

## Algorithm

1. **Parse** all `[ ]` entries from agent_notes.md
2. **Group by type** (priority order):
   - 🔴 `[лог]` / `[error]` — system errors (highest priority)
   - ⚠️ `[рефлексия]` / `[issue]` — user-reported problems
   - 🔄 `[паттерн]` / `[pattern]` — agent patterns and friction
   - 💡 `[новости]` / `[idea]` — ideas from news sources
3. **Deduplicate** similar entries (same root cause → merge)
4. **Select top 3-5** actionable improvements
5. **For each improvement**: identify specific file to change + how

## Output — JSON array (no markdown, no code fences)

```
[
  {
    "id": "e-20260313-001",
    "title": "ValueError при длинных голосовых",
    "desc": "Добавить chunking в voice handler для сообщений >1MB",
    "effort": "малый",
    "type": "error"
  },
  {
    "id": "n-20260313-002",
    "title": "RAG pipeline для vault search",
    "desc": "Использовать embeddings для поиска по vault вместо grep",
    "effort": "большой",
    "type": "idea"
  }
]
```

Valid type values: `error`, `issue`, `pattern`, `idea`
Valid effort values: `малый` (< 1h), `средний` (1-4h), `большой` (> 4h)

## After analysis

Append marker to processed section in agent_notes.md:
```
<!-- analyzed: YYYY-MM-DD -->
```
