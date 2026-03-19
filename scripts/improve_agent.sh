#!/bin/bash
# improve_agent.sh — weekly reminder to run /improve in Telegram
# Called by d-brain-improve.timer every Sunday at 10:00

set -e
source "$(dirname "$0")/common.sh"
init
cd "$VAULT_DIR"

# Count unreviewed items in agent_notes.md
NOTES_FILE="$VAULT_DIR/agent/agent_notes.md"
COUNT=0
if [ -f "$NOTES_FILE" ]; then
    COUNT=$(grep -c '`\[ \]`' "$NOTES_FILE" 2>/dev/null || echo 0)
fi

if [ "$COUNT" -eq 0 ]; then
    # Nothing to review — send brief info
    MSG="🔧 <b>Улучшение агента</b> — воскресная проверка

✅ Нерассмотренных предложений нет.
Предложения накапливаются в течение недели из новостей, рефлексий и логов."
else
    MSG="🔧 <b>Время улучшить агента!</b>

📝 Накоплено <b>${COUNT}</b> нерассмотренных предложений в agent_notes.md.

Отправь /improve чтобы просмотреть каждое и принять решение:
→ Внедрить · ❌ Пропустить · ⏳ Отложить"
fi

send_telegram "$MSG"
