#!/usr/bin/env python3
"""Fetch weather (open-meteo) and AI news from multiple sources for morning briefing."""
import json, os, sys, urllib.request, urllib.error, xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from pathlib import Path

# Paths for deduplication and headlines cache
_VAULT = Path(os.environ.get("VAULT_DIR", Path(__file__).parent.parent / "vault"))
_SESSION = _VAULT / ".session"
SEEN_PATH = _SESSION / "news-seen.json"
HEADLINES_PATH = _SESSION / "morning-headlines.json"
DEDUP_DAYS = 14

WMO = {
    0:"ясно", 1:"преимущественно ясно", 2:"переменная облачность", 3:"пасмурно",
    45:"туман", 48:"туман с инеем",
    51:"лёгкая морось", 53:"морось", 55:"сильная морось",
    61:"небольшой дождь", 63:"дождь", 65:"сильный дождь",
    71:"небольшой снег", 73:"снег", 75:"сильный снег", 77:"снежные зёрна",
    80:"ливень", 81:"ливни", 82:"сильный ливень",
    85:"снегопад", 86:"сильный снегопад",
    95:"гроза", 96:"гроза с градом", 99:"сильная гроза с градом",
}

AI_SOURCES = [
    ("HuggingFace",  "https://huggingface.co/blog/feed.xml"),
    ("VentureBeat",  "https://venturebeat.com/category/ai/feed/"),
    ("OpenAI",       "https://openai.com/blog/rss.xml"),
    ("TechCrunch",   "https://techcrunch.com/category/artificial-intelligence/feed/"),
]

SKIP_KEYWORDS = [
    "war", "ukraine", "russia", "military", "soldier",
    "missile", "nato", "trump", "congress", "senate", "election", "politics",
    "prison", "arrest", "murder", "shooting", "crypto", "bitcoin", "nft",
    "lawsuit", "court", "stock", "ipo", "acquisition",
]


# ── Deduplication helpers ──────────────────────────────────────────────────

def load_seen() -> set:
    """Load set of seen URL/title keys from last DEDUP_DAYS days."""
    try:
        if SEEN_PATH.exists():
            data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
            cutoff = datetime.now() - timedelta(days=DEDUP_DAYS)
            return {e["key"] for e in data.get("seen", [])
                    if datetime.fromisoformat(e["date"]) > cutoff}
    except Exception:
        pass
    return set()


def save_seen(new_keys: list) -> None:
    """Append new keys to seen cache, pruning entries older than DEDUP_DAYS."""
    try:
        existing = []
        if SEEN_PATH.exists():
            existing = json.loads(SEEN_PATH.read_text(encoding="utf-8")).get("seen", [])
        cutoff = datetime.now() - timedelta(days=DEDUP_DAYS)
        pruned = [e for e in existing
                  if datetime.fromisoformat(e["date"]) > cutoff]
        today = date.today().isoformat()
        for k in new_keys:
            pruned.append({"key": k, "date": today})
        _SESSION.mkdir(parents=True, exist_ok=True)
        SEEN_PATH.write_text(
            json.dumps({"seen": pruned}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        print(f"[fetch_context] save_seen error: {e}", file=sys.stderr)


# ── Precipitation helpers ──────────────────────────────────────────────────

def _precip_ranges(precip_arr: list, threshold: int = 40) -> list:
    ranges = []
    in_range = False
    start_h = 0
    for h, prob in enumerate(precip_arr[:24]):
        if prob >= threshold and not in_range:
            in_range = True
            start_h = h
        elif prob < threshold and in_range:
            in_range = False
            ranges.append((start_h, h - 1))
    if in_range:
        ranges.append((start_h, len(precip_arr) - 1))
    return ranges


def _precip_type(wcode: int) -> str:
    if wcode in (71, 73, 75, 77, 85, 86):
        return "снег"
    if wcode in (95, 96, 99):
        return "гроза"
    return "дождь"


# ── Weather ────────────────────────────────────────────────────────────────

def get_weather():
    try:
        lat = os.environ.get("LOCATION_LAT", "55.75")
        lon = os.environ.get("LOCATION_LON", "37.62")
        tz = os.environ.get("LOCATION_TZ", "Europe/Moscow")
        city = os.environ.get("LOCATION_CITY", "Москва")
        url = ("https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}"
               "&current_weather=true"
               "&hourly=precipitation_probability,apparent_temperature,weathercode"
               f"&timezone={tz}&forecast_days=1")
        with urllib.request.urlopen(url, timeout=15) as r:
            d = json.load(r)
        cw = d["current_weather"]
        desc = WMO.get(cw["weathercode"], f"код {cw['weathercode']}")
        temp = cw["temperature"]
        wind = cw["windspeed"]
        hour = datetime.now().hour

        feels_arr = d["hourly"].get("apparent_temperature", [])
        precip_arr = d["hourly"].get("precipitation_probability", [])
        hourly_wcodes = d["hourly"].get("weathercode", [])

        feels = feels_arr[min(hour, len(feels_arr) - 1)] if feels_arr else None
        feels_str = f"{feels:+.0f}°C" if isinstance(feels, (int, float)) else "?"

        ranges = _precip_ranges(precip_arr, threshold=40)
        if ranges:
            rs, re = ranges[0]
            range_codes = hourly_wcodes[rs: re + 1] if hourly_wcodes else []
            dominant = max(range_codes, default=cw["weathercode"])
            ptype = _precip_type(dominant)
            parts = []
            for sh, eh in ranges:
                if eh >= 23:
                    parts.append(f"с {sh:02d}:00 и дольше суток")
                else:
                    parts.append(f"с {sh:02d}:00 до {eh + 1:02d}:00")
            precip_info = f", {ptype} ожидается {', '.join(parts)}"
        else:
            precip_info = ""

        return (f"{city}: {desc}, {temp:+.0f}°C (ощущается {feels_str}), "
                f"ветер {wind:.0f} км/ч{precip_info}")
    except Exception as e:
        print(f"[fetch_context] weather error: {e}", file=sys.stderr)
        return f"погода недоступна ({e})"


# ── RSS ────────────────────────────────────────────────────────────────────

def fetch_rss(rss_url: str, count: int = 6) -> list:
    """Return list of {title, url} dicts from RSS feed."""
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            tree = ET.parse(r)
        items = []
        for item in tree.findall(".//item")[:count]:
            t = item.find("title")
            if t is not None and t.text:
                title = t.text.strip()
                if any(kw in title.lower() for kw in SKIP_KEYWORDS):
                    continue
                # Extract article URL from <link> or <guid>
                art_url = ""
                link_el = item.find("link")
                guid_el = item.find("guid")
                if link_el is not None and link_el.text and link_el.text.startswith("http"):
                    art_url = link_el.text.strip()
                elif guid_el is not None and guid_el.text and guid_el.text.startswith("http"):
                    art_url = guid_el.text.strip()
                items.append({"title": title, "url": art_url})
        return items
    except Exception:
        return []


def get_ai_news() -> list:
    """Return formatted headline strings for Claude context (deduped, max 20)."""
    seen = load_seen()
    all_articles = []
    for source_name, rss_url in AI_SOURCES:
        for art in fetch_rss(rss_url, count=5):
            all_articles.append({**art, "source": source_name})

    # Filter out seen entries (by URL, fall back to title)
    new_articles = []
    for a in all_articles:
        key = a["url"] or a["title"]
        if key not in seen:
            new_articles.append(a)

    top = new_articles[:20]

    # Persist seen keys
    new_keys = [a["url"] or a["title"] for a in top]
    if new_keys:
        save_seen(new_keys)

    # Save raw headlines for fetch_news_full.py
    try:
        _SESSION.mkdir(parents=True, exist_ok=True)
        HEADLINES_PATH.write_text(json.dumps({
            "date": date.today().isoformat(),
            "articles": top[:8],  # top 8 for full fetch
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[fetch_context] save headlines error: {e}", file=sys.stderr)

    # Return formatted strings for Claude (same format as before)
    return [f"[{a['source']}] {a['title']}" for a in top]


# ── Main ───────────────────────────────────────────────────────────────────

weather = get_weather()
news = get_ai_news()

print("=WEATHER=")
print(weather)
print("=AI_NEWS=")
for h in news:
    print(h)
