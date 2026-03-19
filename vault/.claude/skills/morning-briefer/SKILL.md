---
type: note
description: Generates a personalized morning briefing with task recommendations based on Todoist tasks, recent reflections, goals, weather and AI news.
last_accessed: 2026-02-26
relevance: 0.7
tier: warm
name: morning-briefer
---

# Morning Briefer

Analyze context → generate actionable morning briefing → send as HTML to Telegram.

## CRITICAL: Output Format

**ALWAYS return RAW HTML. No markdown. Ever.**

Output goes directly to Telegram with `parse_mode=HTML`.
Allowed tags: `<b>`, `<i>`, `<code>`, newlines.
NEVER use: `**`, `##`, ` ``` `, `- **`, or any markdown.

## Input Context (provided in prompt)

- `=WEATHER=` — weather at user's current location (city name is included at the start of the line)
- `=AI_NEWS=` — raw headlines from HuggingFace, OpenAI, TechCrunch, VentureBeat
- `=TODAY=` — date and weekday
- Vault files: MEMORY.md, goals/3-weekly.md, goals/2-monthly.md, daily/*.md

## MCP Tools Required

- `mcp__todoist__find-tasks` — get all active tasks
- `mcp__todoist__find-tasks-by-date` — get tasks due today

## News Curation Rules

From the raw `=AI_NEWS=` headlines, select **2-3 most relevant** to user's interests:

### INCLUDE — user cares about:
- New AI models released (GPT, Claude, Gemini, Llama, Mistral, etc.)
- Benchmarks beaten or new leaderboard results
- Agent workflows, multi-agent systems, autonomous AI tools
- New tools/frameworks worth trying (LangChain, CrewAI, AutoGen, etc.)
- AI coding assistants, productivity AI
- Local AI / open source model updates
- Practical "how to" from HuggingFace blog

### EXCLUDE — user explicitly doesn't want:
- War, military, weapons
- Politics, elections, government
- Crypto, NFT, blockchain
- General business/funding news (unless directly AI-product relevant)
- Celebrity/entertainment
- Lawsuits, regulations (unless directly changes AI tool access)

### Format each news item as:
`• <b>[Source]</b> {short summary in Russian, 1 sentence} — <i>{why relevant to user}</i>`

If no clearly relevant news — write 1 item: `• Сегодня без громких AI-новостей — хороший день для глубокой работы.`

## Algorithm

1. **Read context** — MEMORY.md, goals/3-weekly.md, goals/2-monthly.md
2. **Read reflections** — daily/YYYY-MM-DD.md for last 2 days
3. **Get Todoist tasks** — find-tasks-by-date for today + overdue (find-tasks)
4. **Curate news** — pick 2-3 relevant AI headlines from =AI_NEWS=
5. **Analyze** — what's urgent, what aligns with goals, what's unresolved
6. **Consider context** — weekday rhythm, weather energy impact
7. **Generate briefing** — see template below

## Weekday Logic

| Day | Recommended focus |
|-----|------------------|
| Mon | Planning week, important meetings, big tasks |
| Tue–Thu | Deep work, execution |
| Fri | Closing open loops, planning next week |
| Sat–Sun | Rest, reflection, creative work, personal projects |

## Output Template

<b>☀️ Доброе утро! {weekday}, {date}</b>

<b>🌤 {city from =WEATHER= line}:</b> {weather + 1 sentence energy tip based on weather}

<b>🤖 AI сегодня:</b>
• <b>[Source]</b> {summary} — <i>{why relevant}</i>
• <b>[Source]</b> {summary} — <i>{why relevant}</i>

<b>🎯 Фокус дня</b>
{1-2 sentences: what to concentrate on today, based on goals + weekday + reflections}

<b>✅ На сегодня ({count} задач)</b>
<b>Срочное:</b>
• {overdue/today p1-p2 tasks, max 3}

<b>Из целей:</b>
• {tasks aligned with weekly/monthly goals, max 2}

<i>⚠️ {count} просроченных задач — коротко что висит</i>

<b>💭 Из рефлексии</b>
{1-2 sentences: unresolved thoughts, what was on mind yesterday}

<b>💡 Совет дня</b>
{1 concrete actionable tip — specific, not generic}

## Rules

- Max 5 tasks total in briefing
- Tone: friendly, direct, energetic — like a smart colleague
- No fluff — every sentence adds value
- Weather bad → suggest indoor focused work
- Weather good → suggest active breaks between work blocks
