#!/bin/bash
# common.sh — shared functions for d-brain scripts
# Source this file: source "$(dirname "$0")/common.sh"

export HOME="/home/niks"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

PROJECT_DIR="/home/niks/my_asb"
VAULT_DIR="$PROJECT_DIR/vault"
ENV_FILE="$PROJECT_DIR/.env"

# Load .env safely
load_env() {
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
}

# Require TELEGRAM_BOT_TOKEN, set CHAT_ID and TODAY
init() {
    load_env

    if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
        echo "ERROR: TELEGRAM_BOT_TOKEN not set"
        exit 1
    fi

    TODAY=${TODAY:-$(date +%Y-%m-%d)}
    CHAT_ID="${ALLOWED_USER_IDS//[\[\]]/}"
}

# Set MCP env vars (for scripts that call Claude with MCP)
init_mcp() {
    export MCP_TIMEOUT=30000
    export MAX_MCP_OUTPUT_TOKENS=50000
}

# Clean Claude output: remove HTML comments, --- wrappers, preamble phrases
clean_claude_output() {
    local raw="$1"

    # Remove HTML comments
    local cleaned
    cleaned=$(echo "$raw" | sed '/<!--/,/-->/d')

    # Remove --- wrappers and preamble via Python
    echo "$cleaned" | python3 -c '
import sys, re

text = sys.stdin.read().strip()

# Strip --- separator wrapper
if "\n---\n" in text or text.startswith("---\n"):
    lines = text.split("\n")
    seps = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
    if len(seps) >= 2:
        text = "\n".join(lines[seps[0]+1:seps[-1]]).strip()
    elif len(seps) == 1:
        before = "\n".join(lines[:seps[0]]).strip()
        after = "\n".join(lines[seps[0]+1:]).strip()
        before_nonempty = [l for l in before.split("\n") if l.strip()]
        # Only strip if before is a short preamble (<=5 lines) not starting with report markers
        if len(before_nonempty) <= 5 and not re.match(r"^[📅📊✅❌<]", before):
            text = after

# Strip known preamble phrases
for pattern in [
    r"^All data collected[.!\s]*(?:Generating[^:\n]*:)?\s*",
    r"^Теперь генерирую финальный HTML[ -]отчёт[.:\s]*",
    r"^Теперь генерирую финальный HTML[ -]отчет[.:\s]*",
    r"^Теперь генерируя финальный HTML[ -]отчёт[.:\s]*",
    r"^Теперь генерируя финальный HTML[ -]отчет[.:\s]*",
    r"^HTML для Telegram[:\s]*",
    r"^Вот HTML для Telegram[:\s]*",
    r"^Вот готовый HTML[:\s]*",
    r"^Готовые HTML для вставки в Телеграм[:\s]*",
]:
    text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

print(text)
'
}

# Send message to Telegram with HTML fallback
# Usage: send_telegram "message text"
send_telegram() {
    local text="$1"

    if [ -z "$text" ] || [ -z "$CHAT_ID" ]; then
        echo "WARNING: empty text or CHAT_ID, skipping Telegram send"
        return 1
    fi

    # Always try HTML first (markdown patterns can appear inside valid HTML content)
    local result
    result=$(curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
        -d "chat_id=$CHAT_ID" \
        --data-urlencode "text=$text" \
        -d "parse_mode=HTML")

    # Fallback: strip HTML tags, then send as plain text
    if echo "$result" | grep -q '"ok":false'; then
        echo "HTML parse failed, retrying as plain text"
        local plain
        plain=$(echo "$text" | sed 's/<[^>]*>//g' | sed 's/&lt;/</g; s/&gt;/>/g; s/&amp;/\&/g')
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d "chat_id=$CHAT_ID" \
            --data-urlencode "text=$plain" > /dev/null
    fi
}

# Usage: send_telegram_silent "message text"
# Like send_telegram but with disable_notification=true (no phone vibration/sound)
send_telegram_silent() {
    local text="$1"
    if [ -z "$text" ] || [ -z "$CHAT_ID" ]; then return 1; fi
    # Try HTML first, fallback to plain text
    local result
    result=$(curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
        -d "chat_id=$CHAT_ID" \
        --data-urlencode "text=$text" \
        -d "parse_mode=HTML" \
        -d "disable_notification=true")
    if echo "$result" | grep -q '"ok":false'; then
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d "chat_id=$CHAT_ID" \
            --data-urlencode "text=$text" \
            -d "disable_notification=true" > /dev/null
    fi
}
