#!/bin/bash
set -e

source "$(dirname "$0")/common.sh"
init
init_mcp

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== d-brain processing for $TODAY ==="

# ── FREE RAM: stop bot during heavy processing ──
BOT_WAS_RUNNING=false
if systemctl is-active --quiet d-brain-bot; then
    BOT_WAS_RUNNING=true
    echo "=== Pausing bot to free RAM ==="
    sudo systemctl stop d-brain-bot || true
fi
# Ensure bot restarts even on failure
trap '
    if [ "$BOT_WAS_RUNNING" = true ]; then
        echo "=== Restarting bot ==="
        sudo systemctl start d-brain-bot || true
    fi
' EXIT

# Pull latest vault changes
echo "=== Pulling latest vault changes ==="
cd "$PROJECT_DIR"
git pull --rebase --autostash || echo "Git pull failed (non-critical)"

# ── ORIENT PHASE: pre-flight checks ──
DAILY_FILE="$VAULT_DIR/daily/$TODAY.md"
HANDOFF_FILE="$VAULT_DIR/.session/handoff.md"
GRAPH_FILE="$VAULT_DIR/.graph/vault-graph.json"
SESSION_DIR="$VAULT_DIR/.session"
mkdir -p "$SESSION_DIR"

# Check daily file exists and has content
if [ ! -f "$DAILY_FILE" ]; then
    echo "ORIENT: daily/$TODAY.md not found — creating empty file"
    echo "# $TODAY" > "$DAILY_FILE"
fi

DAILY_SIZE=$(wc -c < "$DAILY_FILE" 2>/dev/null || echo "0")
if [ "$DAILY_SIZE" -lt 50 ]; then
    echo "ORIENT: daily/$TODAY.md is empty ($DAILY_SIZE bytes) — skipping Claude processing"
    echo "ORIENT: Running graph rebuild only"

    # Still rebuild graph and commit
    cd "$VAULT_DIR"
    uv run .claude/skills/graph-builder/scripts/analyze.py || echo "Graph rebuild failed (non-critical)"
    uv run .claude/skills/agent-memory/scripts/memory-engine.py decay . || echo "Memory decay failed (non-critical)"
    cd "$PROJECT_DIR"

    git add vault/
    git commit -m "chore: process daily $TODAY" || true
    git push || true
    echo "=== Done (empty daily, graph-only) ==="
    exit 0
fi

# Check handoff exists
if [ ! -f "$HANDOFF_FILE" ]; then
    echo "ORIENT: handoff.md not found — creating stub"
    echo -e "---\nupdated: $(date -Iseconds)\n---\n\n## Last Session\n(none)\n\n## Observations" > "$HANDOFF_FILE"
fi

# Check graph freshness (warn if >7 days old)
if [ -f "$GRAPH_FILE" ]; then
    GRAPH_AGE=$(( ($(date +%s) - $(stat -c %Y "$GRAPH_FILE" 2>/dev/null || echo 0)) / 86400 ))
    if [ "$GRAPH_AGE" -gt 7 ]; then
        echo "ORIENT: vault-graph.json is $GRAPH_AGE days old (>7)"
    fi
fi

echo "ORIENT: daily=$DAILY_SIZE bytes, handoff=OK"
# ── END ORIENT PHASE ──

# Find yearly goals file (auto-detect year)
YEARLY_GOALS=$(ls "$VAULT_DIR/goals/1-yearly-"*.md 2>/dev/null | tail -1)
YEARLY_GOALS_NAME=$(basename "$YEARLY_GOALS" 2>/dev/null || echo "1-yearly.md")

# MCP prompt (needed for Phase 2)
MCP_PROMPT="CRITICAL: MCP loads in 10-30 seconds. You are NOT in subprocess — MCP IS running, just initializing.
Algorithm: 1) Call tool. 2) Error? Wait 10 sec. 3) Call again. 4) Wait 20 sec. 5) Call — GUARANTEED to work.
DO NOT say MCP unavailable. It is available. Just wait and call."

CAPTURE_FILE="$SESSION_DIR/capture.json"
EXECUTE_FILE="$SESSION_DIR/execute.json"

cd "$VAULT_DIR"

# ── ORIENT: Log Check ──
LOG_ERRORS=$(journalctl -u d-brain-bot -u d-brain-process -u d-brain-morning \
    --since "24 hours ago" --priority err --no-pager -q 2>/dev/null | tail -20) || LOG_ERRORS=""

# ── 3-PHASE PIPELINE ──
# Phase 1: CAPTURE (classify entries → JSON) — no MCP needed
# Phase 2: EXECUTE (create tasks, save thoughts → JSON) — with MCP/Todoist
# Phase 3: REFLECT (generate HTML report, update MEMORY → HTML) — no MCP needed
# Each phase = fresh Claude context for better quality.

# ── Phase 1: CAPTURE ──
echo "=== Phase 1: CAPTURE ==="
CAPTURE=$(claude --print --dangerously-skip-permissions --model claude-sonnet-4-6 \
    -p "Today is $TODAY. Read .claude/skills/dbrain-processor/phases/capture.md and execute Phase 1.
Read daily/$TODAY.md, goals/3-weekly.md, goals/2-monthly.md, goals/$YEARLY_GOALS_NAME.
Classify each entry. Return ONLY JSON." \
    2>&1) || true

# Save raw output for debugging
echo "$CAPTURE" > "$SESSION_DIR/capture.raw.log"

# Extract JSON using robust parser
echo "$CAPTURE" | python3 "$SCRIPTS_DIR/extract_json.py" > "$CAPTURE_FILE" 2>/dev/null \
    || echo '{"error": "capture failed"}' > "$CAPTURE_FILE"

echo "Capture saved: $(wc -c < "$CAPTURE_FILE") bytes"

# Check if capture produced valid entries
if grep -q '"error"' "$CAPTURE_FILE"; then
    echo "WARN: Capture phase had issues, falling back to monolith mode"
    # Fallback to monolith processing (same as old process.sh)
    REPORT=$(claude --print --dangerously-skip-permissions --model claude-sonnet-4-6 \
        --mcp-config "$PROJECT_DIR/mcp-config.json" \
        -p "Today is $TODAY. TIME: 23:00. EVENING DAILY PROCESSING.

USE ONLY: dbrain-processor skill. Output template: Обработка за {DATE}
DO NOT use morning-briefer skill. DO NOT generate morning briefing.

TASK: Process todays voice/text entries. Also call Oura MCP (get_stress, get_daily_sleep, get_readiness) to include health context in the report — correlate stress peaks with events from daily notes -> classify -> create Todoist tasks -> save thoughts -> generate evening HTML report.

$MCP_PROMPT" \
        2>&1) || true
else
    # ── Phase 2: EXECUTE ──
    # Uses mcp-cli (Bash) for Todoist — no --mcp-config needed
    echo "=== Phase 2: EXECUTE ==="
    EXECUTE=$(claude --print --dangerously-skip-permissions --model claude-sonnet-4-6 \
        -p "Today is $TODAY. Read .claude/skills/dbrain-processor/phases/execute.md and execute Phase 2.
Read .session/capture.json for input data.
Create tasks in Todoist via mcp-cli (Bash tool), save thoughts, build links. Return ONLY JSON.

CRITICAL: Use Bash tool to call mcp-cli for Todoist operations.
Example: mcp-cli call todoist find-tasks-by-date '{\"startDate\": \"today\"}'
mcp-cli may take 10-30 sec on first call (server startup). Retry 3x on error." \
        2>&1) || true

    # Save raw output for debugging
    echo "$EXECUTE" > "$SESSION_DIR/execute.raw.log"

    echo "$EXECUTE" | python3 "$SCRIPTS_DIR/extract_json.py" > "$EXECUTE_FILE" 2>/dev/null \
        || echo '{"error": "execute failed"}' > "$EXECUTE_FILE"

    echo "Execute saved: $(wc -c < "$EXECUTE_FILE") bytes"

    # ── Phase 3: REFLECT ──
    echo "=== Phase 3: REFLECT ==="
    REPORT=$(claude --print --dangerously-skip-permissions --model claude-sonnet-4-6 \
        -p "Today is $TODAY. Read .claude/skills/dbrain-processor/phases/reflect.md and execute Phase 3.
Read .session/capture.json and .session/execute.json for input data.
Read MEMORY.md, .session/handoff.md.
Generate HTML report, update MEMORY, record observations.

SYSTEM LOGS (last 24h, may be empty):
${LOG_ERRORS}

AGENT NOTES TASK: Scan the input text for:
1. User complaints about the bot (not found, failed, broken, did not save) - add to vault/agent/agent_notes.md section "Проблемы из рефлексии" with id: r-{DATE}-NNN
2. Ideas for new automations (would be convenient, want a command, should automate) - add to "Идеи агента" with id: a-{DATE}-NNN
3. If LOG_ERRORS is not empty - add brief error summary to "Системные ошибки" with id: e-{DATE}-NNN (skip if already logged today)
4. If you notice friction patterns or repetitive actions - add 1-2 ideas to "Идеи агента"

Format for each agent_notes.md entry:
- \`[ ]\` **[source]** description <!-- id: X-YYYYMMDD-NNN -->

Return ONLY RAW HTML (for Telegram)." \
        2>&1) || true
fi

cd "$PROJECT_DIR"

echo "=== Claude output ==="
echo "$REPORT"
echo "===================="

REPORT_CLEAN=$(clean_claude_output "$REPORT")

# Rebuild vault graph
echo "=== Rebuilding vault graph ==="
cd "$VAULT_DIR"
uv run .claude/skills/graph-builder/scripts/analyze.py || echo "Graph rebuild failed (non-critical)"

# Memory decay (update relevance scores and tiers)
echo "=== Memory decay ==="
uv run .claude/skills/agent-memory/scripts/memory-engine.py decay . || echo "Memory decay failed (non-critical)"
cd "$PROJECT_DIR"

# Git commit (only vault/)
git add vault/
git commit -m "chore: process daily $TODAY" || true
git push || true

# Send to Telegram
send_telegram "$REPORT_CLEAN"

echo "=== Done ==="
