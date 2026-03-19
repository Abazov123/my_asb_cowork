#!/bin/bash
# night_implement.sh — autonomous nightly improvement implementation
# Triggered at 23:30 by d-brain-night.timer
# Flow: wait for process.sh → plan [→] items → announce → implement one by one

# NOTE: do NOT use set -e globally — individual commands handle their own errors
source "$(dirname "$0")/common.sh"
init

LOG_FILE="$PROJECT_DIR/logs/night_implement.log"
NOTES_FILE="$VAULT_DIR/agent/agent_notes.md"
PLAN_FILE="$VAULT_DIR/agent/impl-plan-$TODAY.json"
CONCEPTS_DIR="$VAULT_DIR/agent/concepts"
mkdir -p "$CONCEPTS_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"; }

log "=== Night implement started ==="

# ── 0. Toggle check ──────────────────────────────────────────────────────────
if [ "${NIGHT_IMPLEMENT_ENABLED:-true}" != "true" ]; then
    log "Disabled via NIGHT_IMPLEMENT_ENABLED=false — exiting"
    exit 0
fi

# ── 1. Wait for process.sh to finish (up to 30 min) ──────────────────────────
MAX_WAIT=30
for i in $(seq 1 $MAX_WAIT); do
    if ! systemctl is-active d-brain-process.service --quiet 2>/dev/null; then
        break
    fi
    log "Waiting for d-brain-process.service... ($i/$MAX_WAIT min)"
    sleep 60
done

# ── 2. Check for [→] items ───────────────────────────────────────────────────
if [ ! -f "$NOTES_FILE" ]; then
    log "agent_notes.md not found — exiting"
    exit 0
fi

ITEMS=$(grep -c '`\[→\]`' "$NOTES_FILE" 2>/dev/null || echo 0)
log "Found $ITEMS [→] items"

# Check for critical errors in bot logs (alert even with 0 [→] items)
CRIT_ERRORS=$(journalctl -u d-brain-bot --since "24 hours ago" \
    --priority crit --no-pager -q 2>/dev/null | wc -l) || CRIT_ERRORS=0
if [ "$CRIT_ERRORS" -gt 0 ]; then
    CRIT_MSG=$(journalctl -u d-brain-bot --since "24 hours ago" \
        --priority crit --no-pager -q 2>/dev/null | tail -3)
    send_telegram "🔴 <b>Критическая ошибка в боте!</b>

$CRIT_MSG

Требуется проверка."
fi

if [ "$ITEMS" -eq 0 ]; then
    log "No [→] items to implement — exiting silently"
    exit 0
fi

# ── 3. PLAN phase — context-first with grouping ──────────────────────────────
log "Starting PLAN phase..."
cd "$VAULT_DIR"

claude --print --dangerously-skip-permissions \
    --model claude-sonnet-4-6 \
    -p "Today is $TODAY. You are the night automation agent for d-brain Telegram bot.

Read in this order:
1. MEMORY.md — user preferences, accepted/rejected improvement patterns
2. goals/3-weekly.md — current week priorities (skip if missing)
3. vault/agent/agent_notes.md — find ALL lines containing \`[→]\` status

Analyze the [→] items and create an implementation plan:

GROUPING RULES:
a) If 2+ items touch the SAME file or module → ONE 'merged' item (implement together)
b) Small, clear, independent changes → 'simple'
c) Complex (>2h, ML/infra, architectural redesign) → 'concept'
   These are NOT skipped — write a concept doc for user to review later

PRIORITY: errors/bugs first → items aligned with weekly goals → small effort → ideas

Write the plan to vault/agent/impl-plan-$TODAY.json with EXACT JSON format:
{
  \"date\": \"$TODAY\",
  \"items\": [
    {
      \"ids\": [\"n-20260313-001\"],
      \"title\": \"Краткое название\",
      \"type\": \"simple\",
      \"file\": \"src/d_brain/bot/handlers/voice.py\",
      \"spec\": \"Конкретное изменение в 2-3 предложениях\",
      \"effort\": \"small\"
    },
    {
      \"ids\": [\"n-20260313-005\"],
      \"title\": \"Семантический поиск по заметкам\",
      \"type\": \"concept\",
      \"file\": null,
      \"spec\": \"Поиск по смыслу через векторные индексы\",
      \"effort\": \"large\",
      \"auto_implementable\": false,
      \"complexity_reason\": \"Нужна отдельная база данных для поиска по смыслу — это новый компонент, который займёт несколько часов настройки и затрагивает всю архитектуру бота.\"
    }
  ]
}

Valid types: simple | merged | concept
Valid effort: small (<30min) | medium (<2h) | large (>2h)
For concept type: file must be null. ALSO set:
- auto_implementable: true if implementable autonomously in <2h with 1-2 file edits only
- auto_implementable: false if requires: ML/embeddings/vector DB, multiple new files, new external services, >2h
- complexity_reason: plain Russian explanation WHY not auto-implementable (1-2 sentences, leave \"\" if auto_implementable=true)
  Good: \"Нужна отдельная база данных для поиска по смыслу — новый компонент, который займёт несколько часов настройки.\"
  Bad: \"Requires vector database integration\"

Return ONLY: PLAN_WRITTEN: N items (X merged, Y simple, Z concepts)" \
    </dev/null >> "$LOG_FILE" 2>&1 || log "WARN: plan phase had errors"

# Verify plan file was created
if [ ! -f "$PLAN_FILE" ]; then
    log "Plan file not created — exiting"
    send_telegram_silent "⚠️ Ночное внедрение: не удалось создать план. Проверь логи."
    exit 1
fi

ITEM_COUNT=$(python3 -c "
import json, sys
try:
    d = json.load(open('$PLAN_FILE'))
    print(len(d.get('items', [])))
except Exception as e:
    print(0)
" 2>/dev/null || echo 0)

log "Plan contains $ITEM_COUNT items"

if [ "$ITEM_COUNT" -eq 0 ]; then
    log "Empty plan — exiting"
    exit 0
fi

# ── 4. Send plan announcement (normal mode — audible) ────────────────────────
PLAN_MSG=$(python3 -c "
import json
d = json.load(open('$PLAN_FILE'))
items = d.get('items', [])
lines = ['🌙 <b>Ночной план</b> — ' + str(len(items)) + ' улучшений:']
lines.append('')
for i, it in enumerate(items, 1):
    t = it.get('type','simple')
    title = it['title']
    auto = it.get('auto_implementable', True)
    if t == 'merged':
        label = '⚡ <b>Объединённая правка:</b> ' + title
    elif t == 'simple':
        label = '⚡ <b>Небольшая правка:</b> ' + title
    else:
        if auto:
            label = '💡 <b>Сложная идея</b> (подготовлю документ, внедрить через /concepts): ' + title
        else:
            label = '💡 <b>Сложная идея</b> (только ты сможешь реализовать, объясню почему): ' + title
    lines.append(str(i) + '. ' + label)
lines.append('')
lines.append('Буду присылать тихие уведомления о каждом шаге, чтобы не мешать.')
print('\n'.join(lines))
" 2>/dev/null || echo "🌙 Начинаю ночное внедрение ($ITEM_COUNT улучшений)")
send_telegram "$PLAN_MSG"
log "Plan announcement sent"

# ── 5. IMPLEMENT loop (index-based — avoids pipe stdin consumption bug) ───────
cd "$PROJECT_DIR"
DONE=0
FAILED=0
CONCEPTS=0

for ((I=0; I<ITEM_COUNT; I++)); do
    # Read item from plan file by index — no pipe, no stdin conflict
    ITEM_JSON=$(python3 -c "
import json, sys
d = json.load(open('$PLAN_FILE'))
json.dump(d['items'][$I], sys.stdout)
" 2>/dev/null || echo '{}')

    ITEM_TYPE=$(echo "$ITEM_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('type','simple'))" 2>/dev/null || echo "simple")
    ITEM_TITLE=$(echo "$ITEM_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('title','?'))" 2>/dev/null || echo "?")
    ITEM_FILE=$(echo "$ITEM_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('file') or '')" 2>/dev/null || echo "")
    ITEM_SPEC=$(echo "$ITEM_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('spec',''))" 2>/dev/null || echo "")
    ITEM_IDS=$(echo "$ITEM_JSON" | python3 -c "import sys,json; ids=json.loads(sys.stdin.read()).get('ids',[]); print(' '.join(ids) if isinstance(ids,list) else str(ids))" 2>/dev/null || echo "")
    ITEM_AUTO=$(echo "$ITEM_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print('true' if d.get('auto_implementable', True) else 'false')" 2>/dev/null || echo "true")
    ITEM_REASON=$(echo "$ITEM_JSON" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('complexity_reason',''))" 2>/dev/null || echo "")

    IDX=$((I+1))
    log "[$IDX/$ITEM_COUNT] Processing: $ITEM_TITLE (type=$ITEM_TYPE auto=$ITEM_AUTO)"
    send_telegram_silent "🔨 <b>[$IDX/$ITEM_COUNT]</b> Начинаю: $ITEM_TITLE"

    if [ "$ITEM_TYPE" = "concept" ]; then
        # ── Concept: prepare document for user ────────────────────────────
        SLUG=$(echo "$ITEM_TITLE" | python3 -c "
import sys, re
t = sys.stdin.read().strip().lower()
t = re.sub(r'[^a-z0-9а-яёa-z ]', '', t)
t = re.sub(r'\s+', '-', t.strip())[:40]
print(t)
" 2>/dev/null || echo "concept")
        CONCEPT_FILE="vault/agent/concepts/${TODAY}-${SLUG}.md"
        AUTO_LABEL=$([ "$ITEM_AUTO" = "true" ] && echo "Да" || echo "Нет")

        CONCEPT_RESULT=$(claude --print --dangerously-skip-permissions \
            --model claude-sonnet-4-6 \
            -p "Подготовь документ концепта для сложной идеи улучшения d-brain бота.

Название: $ITEM_TITLE
Описание: $ITEM_SPEC

Напиши в файл $CONCEPT_FILE следующий Markdown:

# $ITEM_TITLE

## Что это
2-3 предложения: что за идея, как это изменит бота.

## Ценность для бота
Почему это улучшит опыт пользователя. 1-2 предложения.

## Как реализовать
3-5 пронумерованных шагов. Укажи конкретные файлы и библиотеки.

## Оценка времени
Реалистичная оценка — сколько часов займёт реализация и какой уровень знаний нужен.

## Что нужно подготовить
Что должно быть готово перед началом работы (зависимости, инфраструктура).

## Реализация

**Автоматически:** $AUTO_LABEL
**Если нет — почему:** $ITEM_REASON

Верни СТРОГО одну строку: CONCEPT_DOC: $CONCEPT_FILE" \
            </dev/null 2>>"$LOG_FILE") || CONCEPT_RESULT="FAILED: claude error"

        if echo "$CONCEPT_RESULT" | grep -q "^CONCEPT_DOC:"; then
            DOC_PATH=$(echo "$CONCEPT_RESULT" | grep "^CONCEPT_DOC:" | head -1 | sed 's/^CONCEPT_DOC: //')
            # Update status: [→] → [⏳] + append concept file path to the note line
            for ID in $ITEM_IDS; do
                python3 -c "
import re, pathlib
path = '$NOTES_FILE'
content = pathlib.Path(path).read_text(encoding='utf-8')
note_id = '$ID'
concept_path = '$DOC_PATH'
lines = content.splitlines()
for i, line in enumerate(lines):
    if f'<!-- id: {note_id} -->' in line:
        line = re.sub(r'\`\[→\]\`', '\`[⏳]\`', line)
        if concept_path not in line:
            line = line.rstrip() + f' | файл: {concept_path}'
        lines[i] = line
        break
pathlib.Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')
" 2>/dev/null || true
            done
            CONCEPTS=$((CONCEPTS+1))
            if [ "$ITEM_AUTO" = "true" ]; then
                send_telegram_silent "💡 <b>[$IDX/$ITEM_COUNT] Подготовил документ:</b>
<b>$ITEM_TITLE</b>
Файл: <code>$DOC_PATH</code>
Если хочешь внедрить — открой /concepts"
            else
                send_telegram_silent "💡 <b>[$IDX/$ITEM_COUNT] Идея для ручной реализации:</b>
<b>$ITEM_TITLE</b>

Почему не автоматически: $ITEM_REASON

Файл с описанием: <code>$DOC_PATH</code>
Как реализовать: открой в терминале →
<code>claude $DOC_PATH</code>"
            fi
            log "[$IDX] Concept doc: $DOC_PATH (auto=$ITEM_AUTO)"
        else
            FAILED=$((FAILED+1))
            WHY=$(echo "$CONCEPT_RESULT" | head -1 | sed 's/^FAILED: //')
            send_telegram_silent "⚠️ <b>[$IDX/$ITEM_COUNT]</b> Концепт не создан: $ITEM_TITLE
Причина: $WHY"
            log "[$IDX] Concept failed: $WHY"
        fi

    else
        # ── simple / merged: implement the change ─────────────────────────
        IMPL_RESULT=$(claude --print --dangerously-skip-permissions \
            --model claude-sonnet-4-6 \
            -p "Implement this improvement to the d-brain Telegram bot project.

Title: $ITEM_TITLE
Target file: $ITEM_FILE
Specification: $ITEM_SPEC
Related agent_notes IDs: $ITEM_IDS

RULES:
- Read the target file first to understand the full context
- Make ONLY the specific change described — no refactoring, no style changes
- After editing: verify Python syntax with: python3 -c 'import ast; ast.parse(open(\"$ITEM_FILE\").read())'
- If file not found, spec is too vague, or change would clearly break functionality → SKIP

Return EXACTLY ONE of:
DONE: одно предложение на русском, описывающее что изменено
SKIP: одно предложение на русском, объясняющее причину (конкретно)" \
            </dev/null 2>>"$LOG_FILE") || IMPL_RESULT="SKIP: claude execution error"

        RESULT_LINE=$(echo "$IMPL_RESULT" | grep -E '^(DONE|SKIP):' | head -1)
        if [ -z "$RESULT_LINE" ]; then
            RESULT_LINE="SKIP: no result line from claude"
        fi

        if echo "$RESULT_LINE" | grep -q "^DONE:"; then
            WHAT=$(echo "$RESULT_LINE" | sed 's/^DONE: //')
            # Update [→] → [✅]
            for ID in $ITEM_IDS; do
                python3 -c "
import re, pathlib
path = '$NOTES_FILE'
content = pathlib.Path(path).read_text(encoding='utf-8')
note_id = '$ID'
content = re.sub(r'\`\[→\]\`(.*?<!-- id: ' + re.escape(note_id) + r' -->)', r'\`[✅]\`\1', content)
pathlib.Path(path).write_text(content, encoding='utf-8')
" 2>/dev/null || true
            done
            DONE=$((DONE+1))
            send_telegram_silent "✅ <b>[$IDX/$ITEM_COUNT] Готово:</b> $ITEM_TITLE
$WHAT"
            log "[$IDX] Done: $WHAT"
        else
            # Leave [→] as-is — will retry next night
            FAILED=$((FAILED+1))
            WHY=$(echo "$RESULT_LINE" | sed 's/^SKIP: //')
            send_telegram_silent "⏭ <b>[$IDX/$ITEM_COUNT] Пропущено:</b> $ITEM_TITLE
Причина: $WHY
Попробую снова следующей ночью."
            log "[$IDX] Skipped: $WHY"
        fi
    fi
done

# ── 6. Git commit ────────────────────────────────────────────────────────────
cd "$PROJECT_DIR"
git add vault/ src/ scripts/ 2>/dev/null || true
if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "feat: auto-implemented improvements $TODAY" 2>/dev/null || true
    log "Git committed"
else
    log "No changes to commit"
fi

# ── 7. Final summary ─────────────────────────────────────────────────────────
log "=== Night implement finished: done=$DONE concepts=$CONCEPTS failed=$FAILED ==="

SUMMARY="🌙 <b>Ночь завершена!</b>
✅ Внедрено: $DONE"

if [ "$FAILED" -gt 0 ]; then
    SUMMARY="${SUMMARY} · ⚠️ Ошибок: ${FAILED} (повторю завтра)"
fi

if [ "$CONCEPTS" -gt 0 ]; then
    SUMMARY="${SUMMARY} · 💡 На рассмотрении: ${CONCEPTS}"
fi

SUMMARY="${SUMMARY}

<b>Что делать дальше:</b>
• /improve — новые идеи из новостей и анализа
• /concepts — идеи, которые требуют твоего решения
• /news — последние технические новости"

if [ "$CONCEPTS" -gt 0 ]; then
    SUMMARY="${SUMMARY}

💡 Есть ${CONCEPTS} идей для рассмотрения → /concepts"
fi

send_telegram_silent "$SUMMARY"
