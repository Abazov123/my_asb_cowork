"""Web page scraping: article text + optional top comments."""

import asyncio
import logging
import re
import subprocess

import httpx

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")
_HABR_RE = re.compile(r"habr\.com/(?:\w{2}/)?(?:articles|post)/(\d+)")
_OSNOVA_RE = re.compile(r"(dtf\.ru|vc\.ru|tjournal\.ru)/(?:[^/]+/)?(\d+)-")
_PIKABU_RE = re.compile(r"pikabu\.ru/story/")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.9",
}

_SUMMARIZE_PROMPT = (
    "Прочитай статью и комментарии к ней. Выдели самую суть: ценные идеи, выводы, инсайты. "
    "Если ключевое «золото» — в комментариях, включи его. "
    "Пиши кратко (3–7 пунктов), без воды. Формат: маркированный список на русском языке."
)


def extract_urls(text: str) -> list[str]:
    """Extract all http(s) URLs from text."""
    return _URL_RE.findall(text)


def has_urls(text: str) -> bool:
    return bool(_URL_RE.search(text))


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_HEADERS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _extract_text(html: str, url: str) -> tuple[str, str]:
    """Return (title, body_text) via trafilatura."""
    import trafilatura

    meta = trafilatura.extract_metadata(html, default_url=url)
    title = (meta.title or "") if meta else ""
    text = (
        trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        or ""
    )
    return title.strip(), text.strip()


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean)
    for ent, ch in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")):
        clean = clean.replace(ent, ch)
    return clean.strip()


async def _habr_comments(article_id: str, max_count: int = 15) -> list[str]:
    """Top comments from Habr API sorted by score."""
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            resp = await client.get(
                f"https://habr.com/kek/v2/articles/{article_id}/comments"
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception as exc:
        logger.warning("Habr comments error: %s", exc)
        return []

    items: list[tuple[int, str]] = []
    for c in data.get("comments", {}).values():
        score = c.get("score", 0)
        raw = c.get("message", "")
        if isinstance(raw, dict):
            # legacy format: message was an object with text/score fields
            score = raw.get("score", score)
            raw = raw.get("text", "")
        clean = _strip_html(raw)
        if len(clean) >= 30:
            items.append((score, clean))

    items.sort(key=lambda x: -x[0])
    return [t for _, t in items[:max_count]]


async def _osnova_comments(host: str, article_id: str, max_count: int = 15) -> list[str]:
    """Top comments from DTF/VC.ru/TJ (Osnova CMS) API."""
    api_host = f"https://api.{host}"
    try:
        async with httpx.AsyncClient(timeout=10, headers=_HEADERS) as client:
            resp = await client.get(f"{api_host}/v1.8/content/{article_id}/comments")
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception as exc:
        logger.warning("Osnova comments error (%s): %s", host, exc)
        return []

    items: list[tuple[int, str]] = []
    for c in data.get("result", {}).get("items", []):
        text = _strip_html(c.get("text", ""))
        likes = c.get("likes", {}).get("count", 0)
        if len(text) >= 30:
            items.append((likes, text))

    items.sort(key=lambda x: -x[0])
    return [t for _, t in items[:max_count]]


def _pikabu_comments(html_text: str, limit: int = 12) -> list[str]:
    """Extract top comments from Pikabu post HTML via lxml XPath."""
    try:
        from lxml import html as lhtml

        tree = lhtml.fromstring(html_text)
        results: list[tuple[int, str]] = []

        for el in tree.xpath('//div[contains(@class,"comment")]'):
            # Skip deleted/hidden comments
            if el.xpath('.//*[contains(@class,"comment_deleted")]'):
                continue
            # Rating via data-rating attribute
            rating_attr = el.get("data-rating", "0")
            try:
                rating = int(rating_attr)
            except (ValueError, TypeError):
                rating = 0
            if rating < 0:
                continue
            # Comment body text
            texts = el.xpath('.//*[contains(@class,"comment__body")]//text()')
            body = " ".join(t.strip() for t in texts if t.strip())
            if len(body) >= 30:
                results.append((rating, body))

        results.sort(key=lambda x: x[0], reverse=True)
        return [body for _, body in results[:limit]]
    except Exception as exc:
        logger.warning("Pikabu comments parse error: %s", exc)
        return []


def _run_claude_cli(prompt: str, timeout: int = 60) -> str:
    """Run claude CLI with haiku model synchronously. Returns output or empty string."""
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "claude-haiku-4-5-20251001", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        logger.warning("claude CLI returned code %d: %s", result.returncode, result.stderr[:200])
    except subprocess.TimeoutExpired:
        logger.warning("claude CLI timed out after %ds", timeout)
    except FileNotFoundError:
        logger.warning("claude CLI not found in PATH")
    except Exception as exc:
        logger.warning("claude CLI error: %s", exc)
    return ""


async def summarize_content(
    title: str, text: str, comments: list[str], api_key: str = ""
) -> str:
    """Summarize article text and top comments via claude CLI (haiku).

    api_key is ignored — uses claude subscription via CLI.
    """
    if not text:
        return ""

    parts = [f"# {title}" if title else "", text[:30_000]]
    if comments:
        parts.append("\n## Топ комментарии:\n" + "\n".join(f"- {c}" for c in comments[:8]))
    content = "\n\n".join(p for p in parts if p)

    prompt = f"{_SUMMARIZE_PROMPT}\n\n{content}"
    return await asyncio.to_thread(_run_claude_cli, prompt, 60)


async def synthesize_articles(articles: list[dict], api_key: str = "") -> str:
    """Unified synthesis of multiple articles via claude CLI (haiku).

    api_key is ignored — uses claude subscription via CLI.
    """
    parts = []
    for i, a in enumerate(articles, 1):
        title = a.get("title") or "Без заголовка"
        text = (a.get("text") or "")[:8_000]
        coms = "\n".join(f"• {c}" for c in (a.get("comments") or [])[:5])
        part = f"=== Публикация {i}: {title} ===\n{text}"
        if coms:
            part += f"\n\nКомментарии:\n{coms}"
        parts.append(part)

    combined = "\n\n".join(parts)[:55_000]
    prompt = (
        f"Прочитай {len(articles)} публикации и напиши общий синтез.\n\n"
        f"{combined}\n\n"
        "Что объединяет эти материалы? Ключевые идеи и инсайты — "
        "что ценного для размышлений или решений? "
        "Формат: 3–6 коротких буллетов на русском, без вводных фраз."
    )
    return await asyncio.to_thread(_run_claude_cli, prompt, 90)


async def _firecrawl_scrape(url: str, api_key: str) -> tuple[str, str] | None:
    """Try to scrape URL via Firecrawl API. Returns (title, text) or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            )
            if resp.status_code != 200:
                logger.warning("Firecrawl returned %d for %s", resp.status_code, url)
                return None
            data = resp.json()
            content = data.get("data", {})
            title = (content.get("metadata", {}) or {}).get("title", "") or ""
            text = content.get("markdown", "") or ""
            if text:
                return title.strip(), text.strip()
            return None
    except Exception as exc:
        logger.warning("Firecrawl error for %s: %s", url, exc)
        return None


async def scrape_webpage(url: str) -> dict:
    """Fetch URL, extract article text and top comments.

    Returns dict with keys: title, text, comments (list[str]).
    Uses Firecrawl as primary method when FIRECRAWL_API_KEY is set, falls back to trafilatura.
    """
    from d_brain.config import get_settings

    url = url.strip()
    comments: list[str] = []
    html: str | None = None

    firecrawl_key = get_settings().firecrawl_api_key
    if firecrawl_key:
        result = await _firecrawl_scrape(url, firecrawl_key)
        if result:
            title, text = result
            # Still fetch comments from platform APIs
            habr_m = _HABR_RE.search(url)
            if habr_m:
                comments = await _habr_comments(habr_m.group(1))
            else:
                osnova_m = _OSNOVA_RE.search(url)
                if osnova_m:
                    host, article_id = osnova_m.group(1), osnova_m.group(2)
                    comments = await _osnova_comments(host, article_id)
            return {"title": title, "text": text, "comments": comments}
        logger.info("Firecrawl failed for %s, falling back to trafilatura", url)

    html = await _fetch_html(url)
    title, text = _extract_text(html, url)

    habr_m = _HABR_RE.search(url)
    if habr_m:
        comments = await _habr_comments(habr_m.group(1))
    else:
        osnova_m = _OSNOVA_RE.search(url)
        if osnova_m:
            host, article_id = osnova_m.group(1), osnova_m.group(2)
            comments = await _osnova_comments(host, article_id)
        elif _PIKABU_RE.search(url):
            comments = _pikabu_comments(html)

    return {"title": title, "text": text, "comments": comments}
