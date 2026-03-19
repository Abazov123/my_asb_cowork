#!/bin/bash
# night_implement_single.sh — on-demand implementation of a single concept
# Usage: bash scripts/night_implement_single.sh NOTE_ID CONCEPT_FILE
# Returns: "DONE: ..." or "FAILED: ..." to stdout

NOTE_ID="${1:-}"
CONCEPT_FILE="${2:-}"

source "$(dirname "$0")/common.sh"
init

if [ -z "$NOTE_ID" ] || [ -z "$CONCEPT_FILE" ]; then
    echo "FAILED: не указаны аргументы (note_id и concept_file)"
    exit 0
fi

FULL_CONCEPT_PATH="$PROJECT_DIR/$CONCEPT_FILE"

if [ ! -f "$FULL_CONCEPT_PATH" ]; then
    echo "FAILED: файл концепта не найден: $CONCEPT_FILE"
    exit 0
fi

# Extract title and implementation spec from concept doc
TITLE=$(head -5 "$FULL_CONCEPT_PATH" | grep '^#' | sed 's/^# //' | head -1)

SPEC=$(python3 -c "
import pathlib, re
doc = pathlib.Path('$FULL_CONCEPT_PATH').read_text(encoding='utf-8')
m = re.search(r'## Как реализовать\n(.*?)(?=\n##|\Z)', doc, re.DOTALL)
spec = m.group(1).strip() if m else doc[:600]
print(spec[:800])
" 2>/dev/null || echo "")

ITEM_FILE=$(python3 -c "
import pathlib, re
doc = pathlib.Path('$FULL_CONCEPT_PATH').read_text(encoding='utf-8')
m = re.search(r'src/d_brain/\S+\.py', doc)
print(m.group(0) if m else '')
" 2>/dev/null || echo "")

cd "$PROJECT_DIR"

RESULT=$(claude --print --dangerously-skip-permissions \
    --model claude-sonnet-4-6 \
    -p "Implement this improvement to the d-brain Telegram bot project.

Concept document: $FULL_CONCEPT_PATH

Title: $TITLE
Target file (if identified): $ITEM_FILE
Implementation steps: $SPEC

RULES:
- Read the full concept document first for complete context
- Read the target file before making changes
- Make ONLY the specific change described
- Verify Python syntax after editing
- If spec is too vague or change would break functionality → FAILED

Return EXACTLY ONE of:
DONE: одно предложение на русском, описывающее что изменено
FAILED: одно предложение на русском, объясняющее причину (конкретно)" \
    </dev/null 2>/dev/null) || RESULT="FAILED: ошибка выполнения claude"

RESULT_LINE=$(echo "$RESULT" | grep -E '^(DONE|FAILED):' | head -1)
if [ -z "$RESULT_LINE" ]; then
    RESULT_LINE="FAILED: нет результата от claude"
fi

# Output result to stdout for Python to read
echo "$RESULT_LINE"
