#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"
init
init_mcp

WEEKDAY=$(LC_TIME=ru_RU.UTF-8 date +%A 2>/dev/null || date +%A)

echo "=== Morning briefing for $TODAY ==="

# ── FREE RAM: stop bot during heavy processing ──
BOT_WAS_RUNNING=false
if systemctl is-active --quiet d-brain-bot; then
    BOT_WAS_RUNNING=true
    echo "=== Pausing bot to free RAM ==="
    sudo systemctl stop d-brain-bot || true
fi
trap '
    if [ "$BOT_WAS_RUNNING" = true ]; then
        echo "=== Restarting bot ==="
        sudo systemctl start d-brain-bot || true
    fi
' EXIT

# Fetch weather + news
CONTEXT=$(python3 "$PROJECT_DIR/scripts/fetch_context.py" 2>/dev/null) || CONTEXT="=WEATHER=\nнедоступно\n=AI_NEWS=\nнедоступно"
CURRENT_CITY="${LOCATION_CITY:-Москва}"
# Fetch full article content + summaries in background (completes during Claude run)
"$PROJECT_DIR/.venv/bin/python3" "$PROJECT_DIR/scripts/fetch_news_full.py" 2>>"$PROJECT_DIR/logs/fetch_news.log" &
NEWS_PID=$!

echo "=== Context fetched ==="
echo "$CONTEXT"

# Pull latest vault changes
echo "=== Pulling latest vault changes ==="
cd "$PROJECT_DIR"
git pull --rebase --autostash || echo "Git pull failed (non-critical)"

cd "$VAULT_DIR"
REPORT=$(claude --print --dangerously-skip-permissions --model claude-sonnet-4-6 \
    --mcp-config "$PROJECT_DIR/mcp-config.json" \
    -p "User's current location: $CURRENT_CITY (timezone: ${LOCATION_TZ:-Europe/Moscow}).
Today is $TODAY ($WEEKDAY). Generate morning briefing according to morning-briefer skill.

=== CONTEXT FOR TODAY ===
$CONTEXT

=== INSTRUCTIONS ===
1. Read MEMORY.md, goals/3-weekly.md, goals/2-monthly.md
2. Read daily logs for last 2 days
3. Call mcp__todoist__find-tasks-by-date for today
4. Call mcp__todoist__find-tasks to get overdue tasks
5. Generate HTML briefing using morning-briefer skill template

CRITICAL: Return RAW HTML only. No markdown. No explanations." \
    2>&1) || true
cd "$PROJECT_DIR"

echo "=== Claude output ==="
echo "$REPORT"

wait $NEWS_PID 2>/dev/null || true  # ensure news fetch is done before git commit
REPORT_CLEAN=$(clean_claude_output "$REPORT")
send_telegram "$REPORT_CLEAN"

echo "=== Morning briefing done ==="
