#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"
init

DAY_MONTH=$(date +"%d %B")

# Get a fun fact about today via Claude
FACT=$(claude --print --dangerously-skip-permissions --model claude-haiku-4-5-20251001 \
    -p "Today is ${TODAY}. Find ONE interesting fact about this calendar date (${DAY_MONTH}) — a historical event, birthday of a famous person, or curious fact. 
Rules: 
- Answer in Russian
- Max 2 sentences
- No intro like 'Today is...' — just the fact itself
- Use HTML: <b>name</b> for names/titles if needed
- No markdown" \
    2>/dev/null | head -5) || FACT=""

# Fallback if Claude fails
if [ -z "$FACT" ]; then
    FACT="Каждый день — это новая возможность."
fi

MESSAGE="🕗 <b>Время рефлексии!</b>

📅 <i>${DAY_MONTH}:</i> ${FACT}

До подведения итогов осталось 3 часа (в 23:00).

Расскажи мне:
• Как прошёл день?
• Что сделал, что не успел?
• Какие мысли или идеи?
• Что чувствуешь?

Чем больше расскажешь — тем точнее будет итоговый отчёт и задачи на завтра 💬"

send_telegram "$MESSAGE"

echo "Reminder sent at $(date)"
