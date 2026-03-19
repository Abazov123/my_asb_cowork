"""YouTube video processing: subtitles/transcription + top comments."""

import logging
import re
import tempfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_DENO_PATH = Path.home() / ".deno/bin/deno"

_YT_PATTERNS = [
    r"(?:https?://)?(?:www\.|m\.)?youtube\.com/watch\?(?:[^&\s]*&)*v=([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})",
    r"(?:https?://)?(?:www\.|m\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
]


def extract_video_id(text: str) -> str | None:
    """Return YouTube video ID found anywhere in text, or None."""
    for pattern in _YT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def _clean_vtt(vtt: str) -> str:
    """Strip VTT markup and deduplicate overlapping caption lines."""
    seen: set[str] = set()
    result: list[str] = []
    for line in vtt.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("WEBVTT") or s.startswith("NOTE") or s.startswith("STYLE"):
            continue
        if re.match(r"^\d{2}:\d{2}", s) or re.match(r"^\d+$", s):
            continue
        clean = re.sub(r"<[^>]+>", "", s)
        for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                              ("&quot;", '"'), ("&#39;", "'")):
            clean = clean.replace(entity, char)
        clean = clean.strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return " ".join(result)


def _ydl_base_opts() -> dict:
    opts: dict = {"quiet": True, "no_warnings": True}
    if _DENO_PATH.exists():
        opts["js_runtimes"] = {"deno": {}}  # yt-dlp ≥2026 expects dict, not list
    return opts


async def get_video_info(video_id: str, api_key: str) -> dict:
    """Return title, channel, duration_str via YouTube Data API."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"id": video_id, "part": "snippet,contentDetails", "key": api_key},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    if not items:
        return {}
    snippet = items[0].get("snippet", {})
    raw_dur = items[0].get("contentDetails", {}).get("duration", "")
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", raw_dur)
    if m:
        h, mn, s = (int(x or 0) for x in m.groups())
        dur = f"{h}:{mn:02d}:{s:02d}" if h else f"{mn}:{s:02d}"
    else:
        dur = ""
    return {
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "duration": dur,
    }


async def get_top_comments(video_id: str, api_key: str, max_results: int = 20) -> list[str]:
    """Return top comments by relevance (empty list if comments disabled)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/commentThreads",
                params={
                    "videoId": video_id,
                    "part": "snippet",
                    "order": "relevance",
                    "maxResults": max_results,
                    "key": api_key,
                },
            )
            if resp.status_code == 403:
                logger.info("Comments disabled for video %s", video_id)
                return []
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Could not fetch comments: %s", exc)
        return []

    comments: list[str] = []
    for item in data.get("items", []):
        raw = item["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "")
        clean = re.sub(r"<[^>]+>", "", raw)
        for ent, ch in (("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")):
            clean = clean.replace(ent, ch)
        clean = clean.strip()
        # Skip very short or emoji-only comments
        if len(clean) >= 30:
            comments.append(clean)
    return comments


async def get_subtitles(video_id: str) -> tuple[str, str] | None:
    """Try to get subtitles via yt-dlp.

    Returns (clean_text, language) or None if unavailable.
    Priority: manual ru > manual en > auto ru > auto en.
    """
    import yt_dlp  # type: ignore

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        **_ydl_base_opts(),
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["ru", "en"],
        "subtitlesformat": "vtt",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            opts["outtmpl"] = str(Path(tmp) / "%(id)s")
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                # Check what's actually available before downloading
                manual = info.get("subtitles", {})
                auto = info.get("automatic_captions", {})
                priority = [
                    ("ru", manual), ("en", manual),
                    ("ru", auto),   ("en", auto),
                ]
                chosen_lang = None
                for lang, source in priority:
                    if lang in source:
                        chosen_lang = lang
                        break
                if not chosen_lang:
                    logger.info("No subtitles available for %s", video_id)
                    return None
                ydl.download([url])

            for pattern in [f"*.{chosen_lang}.vtt", f"*.{chosen_lang}-*.vtt"]:
                files = list(Path(tmp).glob(pattern))
                if files:
                    raw = files[0].read_text(encoding="utf-8", errors="ignore")
                    clean = _clean_vtt(raw)
                    if len(clean) > 100:
                        logger.info("Subtitles OK: lang=%s %d chars", chosen_lang, len(clean))
                        return clean, chosen_lang
    except Exception as exc:
        logger.warning("Subtitle extraction error: %s", exc)
    return None


async def download_and_transcribe(video_id: str, transcriber) -> str:  # type: ignore[type-arg]
    """Download audio (mp3 64k) and transcribe via Deepgram."""
    import yt_dlp  # type: ignore

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        **_ydl_base_opts(),
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "64"}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        opts["outtmpl"] = str(Path(tmp) / "audio")
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = list(Path(tmp).glob("audio.*"))
        if not files:
            raise RuntimeError("Audio download failed")
        audio_bytes = files[0].read_bytes()
        logger.info("Downloaded audio: %.1f MB", len(audio_bytes) / 1024 / 1024)
        return await transcriber.transcribe(audio_bytes)


async def process_youtube(video_id: str, api_key: str, transcriber) -> dict:  # type: ignore[type-arg]
    """Orchestrate: info + subtitles/transcription + comments.

    Returns dict with keys: title, channel, duration, transcript,
    transcript_source ('subtitles_ru', 'subtitles_en', 'deepgram'),
    comments (list[str]).
    """
    import asyncio

    # Run info + comments in parallel; subtitles sequentially after
    info_task = asyncio.create_task(get_video_info(video_id, api_key))
    comments_task = asyncio.create_task(get_top_comments(video_id, api_key))

    sub_result = await get_subtitles(video_id)

    if sub_result:
        transcript, lang = sub_result
        source = f"subtitles_{lang}"
    else:
        logger.info("No subtitles — falling back to Deepgram for %s", video_id)
        transcript = await download_and_transcribe(video_id, transcriber)
        source = "deepgram"

    info = await info_task
    comments = await comments_task

    return {
        "title": info.get("title", ""),
        "channel": info.get("channel", ""),
        "duration": info.get("duration", ""),
        "transcript": transcript,
        "transcript_source": source,
        "comments": comments,
    }
