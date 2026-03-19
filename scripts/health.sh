#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"
init
init_mcp

WEEKDAY=$(LC_TIME=ru_RU.UTF-8 date +%A 2>/dev/null || date +%A)

echo "=== Health check for $TODAY ==="

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

cd "$VAULT_DIR"
REPORT=$(claude --print --dangerously-skip-permissions --model claude-sonnet-4-6 \
    --mcp-config "$PROJECT_DIR/mcp-config.json" \
    -p "Today is $TODAY ($WEEKDAY), time: 12:00 midday. Generate a HEALTH CHECK message.

=== INSTRUCTIONS ===
1. Call Oura MCP tools to get TODAY's data:
   - get_daily_sleep (last night's sleep score, duration, efficiency)
   - get_readiness (recovery score)
   - get_stress (current stress level)
   - get_heart_rate (resting HR, current trends)
   - analyze_hrv_trend (HRV context)
2. Read today's daily log from vault (if exists) and yesterday's daily log
3. Read goals/3-weekly.md for current priorities

=== OUTPUT FORMAT ===
Generate a SHORT Telegram message in HTML. NOT a data dump — an insightful check-in:

<b>🫀 Здоровье — полдень</b>

<b>Ночь:</b> One sentence verdict — good/bad sleep, recovered or not. Only mention numbers if something is unusual.

<b>Сейчас:</b> Stress/HRV assessment. If stress is elevated or HRV is low — ask WHY, reference what's in today's calendar or recent notes.

<b>Рекомендация:</b> One actionable suggestion for the rest of the day, based on current state + today's planned tasks.

If stress is high, end with a question prompting reflection: 'Что сейчас давит? Расскажи.'

RULES:
- Max 10 lines total
- Russian language
- HTML formatting only (no markdown)
- Don't just list numbers from Oura — the user already sees those in the app
- Focus on CORRELATIONS and INSIGHTS: connect health data with life context from vault
- If Oura data is unavailable, say so briefly and skip" \
    2>&1) || true
cd "$PROJECT_DIR"

echo "=== Claude output ==="
echo "$REPORT"

REPORT_CLEAN=$(clean_claude_output "$REPORT")
send_telegram "$REPORT_CLEAN"

echo "=== Health check done ==="
