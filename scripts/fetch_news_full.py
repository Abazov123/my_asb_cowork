#!/usr/bin/env python3
"""Fetch full article texts, generate summaries and agent notes for morning news.

Reads vault/.session/morning-headlines.json (written by fetch_context.py),
fetches full article content, generates summaries via claude haiku,
writes morning-news.json, vault/daily/YYYY-MM-DD.md, and vault/agent/agent_notes.md.
"""
import json, os, subprocess, sys
from datetime import date, datetime
from pathlib import Path

# Paths
_PROJECT = Path(os.environ.get("PROJECT_DIR", Path(__file__).parent.parent))
_VAULT   = Path(os.environ.get("VAULT_DIR",   _PROJECT / "vault"))
_SESSION = _VAULT / ".session"
_AGENT   = _VAULT / "agent"
_DAILY   = _VAULT / "daily"

HEADLINES_PATH  = _SESSION / "morning-headlines.json"
MORNING_NEWS    = _SESSION / "morning-news.json"
AGENT_NOTES     = _AGENT   / "agent_notes.md"

TODAY        = date.today().isoformat()
MAX_ARTICLES = 5   # max articles to fully fetch


# ── Claude haiku subprocess ────────────────────────────────────────────────

def run_haiku(prompt: str, timeout: int = 60) -> str:
    try:
        r = subprocess.run(
            ["claude", "--print", "--model", "claude-haiku-4-5-20251001", "-p", prompt],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


# ── Article fetching ───────────────────────────────────────────────────────

def fetch_article(url: str) -> str:
    """Fetch and extract article text via trafilatura."""
    if not url:
        return ""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return (text or "").strip()
    except Exception as e:
        print(f"[fetch_news] fetch error {url[:60]}: {e}", file=sys.stderr)
        return ""


def generate_summary(title: str, text: str) -> str:
    """3-5 bullet points summary via haiku."""
    if not text:
        return ""
    prompt = (
        "Выдели 3-5 ключевых мыслей из этой статьи. "
        "Формат: буллеты на русском, без вводных фраз:\n\n"
        f"Заголовок: {title}\n\n{text[:15000]}"
    )
    return run_haiku(prompt, timeout=60)


def generate_agent_note(title: str, text: str, source: str) -> str | None:
    """Double-evaluation: return actionable bot improvement or None.
    Strict filtering — only specific, implementable improvements for THIS bot."""
    if not text:
        return None
    prompt = (
        "Ты — строгий технический рецензент для небольшого личного Telegram-бота.\n"
        "Бот: aiogram 3, Python 3.12, 1 пользователь, функции: дневник/заметки/напоминания/новости/рефлексия.\n\n"
        f"Статья: {title} | Источник: {source}\n"
        f"Текст (1200 символов): {text[:1200]}\n\n"
        "ЭТАП 1 — ФИЛЬТР (жёсткий):\n"
        "Автоматически верни SKIP если статья про:\n"
        "→ ML-обучение, нейросетевые архитектуры, корпоративные AI-системы\n"
        "→ Политику, бизнес, финансы, события в мире\n"
        '→ Общие рассуждения о "будущем AI" без конкретного кода\n'
        "→ Инструменты, требующие собственных GPU или >$50/мес инфраструктуры\n"
        "→ Академические исследования без практической реализации\n\n"
        "ЭТАП 2 — КОНКРЕТНОСТЬ (только если прошло фильтр):\n"
        "Опиши конкретное изменение: Изменить/Добавить/Исправить [компонент] — [что именно]\n"
        "Требования: начинается с глагола, один компонент, реализуемо за <2 часа.\n\n"
        "Верни ОДНУ строку (≤120 символов) или SKIP. Без объяснений."
    )
    result = run_haiku(prompt, timeout=30)
    if not result:
        return None
    line = result.strip().splitlines()[0].strip()
    if not line or line.upper() == "SKIP":
        return None
    # Validate: must start with recognized action verb
    action_verbs = ("добав", "измен", "оптим", "исправ", "улучш", "реализ", "внедр", "переработ")
    if not any(line.lower().startswith(v) for v in action_verbs):
        return None
    return line[:120]


# ── Vault writers ──────────────────────────────────────────────────────────

def save_to_vault_daily(articles: list) -> None:
    """Append article cards to today's daily note."""
    _DAILY.mkdir(parents=True, exist_ok=True)
    daily_file = _DAILY / f"{TODAY}.md"
    now_str = datetime.now().strftime("%H:%M")
    lines = []
    for art in articles:
        if not art.get("text"):
            continue
        title   = art["title"]
        url     = art["url"]
        source  = art["source"]
        summary = art.get("summary", "")
        entry   = f"\n## {now_str} [url]\n📰 [{source}] {title}\n{url}\n"
        if summary:
            entry += f"\nКлючевые мысли:\n{summary}\n"
        lines.append(entry)
    if lines:
        with open(daily_file, "a", encoding="utf-8") as f:
            f.write("".join(lines))
        print(f"[fetch_news] Saved {len(lines)} articles to {daily_file.name}", file=sys.stderr)


def append_agent_notes(articles: list) -> None:
    """Write improvement idea entries to vault/agent/agent_notes.md."""
    relevant = [(i, a) for i, a in enumerate(articles) if a.get("agent_note")]
    if not relevant:
        return

    _AGENT.mkdir(parents=True, exist_ok=True)
    if not AGENT_NOTES.exists():
        AGENT_NOTES.write_text(
            "# Agent Notes — идеи и проблемы для улучшения\n", encoding="utf-8"
        )

    content = AGENT_NOTES.read_text(encoding="utf-8")
    section_header = f"\n## {TODAY}"
    news_sub = "\n### 💡 Идеи от новостей\n"

    new_lines = []
    for i, art in relevant:
        note_id = f"n-{TODAY.replace('-', '')}-{i+1:03d}"
        new_lines.append(
            f"- `[ ]` **[{art['source']}]** {art['agent_note']} "
            f"([{art['title'][:60]}]({art['url']}))   <!-- id: {note_id} -->"
        )

    addition = "\n".join(new_lines) + "\n"

    if section_header in content:
        if news_sub.strip() in content:
            # Append after existing news subsection header
            idx = content.find(news_sub)
            insert = idx + len(news_sub)
            content = content[:insert] + addition + content[insert:]
        else:
            # Insert news subsection at start of today's section
            idx = content.find(section_header) + len(section_header)
            content = content[:idx] + "\n" + news_sub + addition + content[idx:]
    else:
        # New day section at end
        content = content.rstrip() + section_header + "\n" + news_sub + addition

    AGENT_NOTES.write_text(content, encoding="utf-8")
    print(f"[fetch_news] Wrote {len(new_lines)} agent notes", file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    if not HEADLINES_PATH.exists():
        print("[fetch_news] morning-headlines.json not found, skipping.", file=sys.stderr)
        return

    try:
        data = json.loads(HEADLINES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[fetch_news] Error reading headlines: {e}", file=sys.stderr)
        return

    raw = data.get("articles", [])[:MAX_ARTICLES]
    if not raw:
        print("[fetch_news] No articles to process.", file=sys.stderr)
        return

    print(f"[fetch_news] Processing {len(raw)} articles...", file=sys.stderr)

    enriched = []
    for art in raw:
        title  = art.get("title", "")
        url    = art.get("url", "")
        source = art.get("source", "")
        print(f"[fetch_news] → {title[:70]}", file=sys.stderr)

        text        = fetch_article(url)
        summary     = generate_summary(title, text) if text else ""
        agent_note  = generate_agent_note(title, text, source) if text else None

        enriched.append({
            "source":     source,
            "title":      title,
            "url":        url,
            "text":       text[:50000] if text else "",
            "summary":    summary,
            "agent_note": agent_note,
        })

    # Write morning-news.json (without full text to keep it small)
    _SESSION.mkdir(parents=True, exist_ok=True)
    news_out = [{k: v for k, v in a.items() if k != "text"} for a in enriched]
    MORNING_NEWS.write_text(
        json.dumps({"date": TODAY, "articles": news_out}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[fetch_news] Saved morning-news.json ({len(news_out)} articles)", file=sys.stderr)

    # Write to vault
    save_to_vault_daily(enriched)
    append_agent_notes(enriched)


if __name__ == "__main__":
    main()
