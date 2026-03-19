"""Handler for /location command — change current city/timezone."""

import asyncio
import json
import logging
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from d_brain.config import get_settings

router = Router(name="location")
logger = logging.getLogger(__name__)

# ── WMO weather codes (Open-Meteo) ────────────────────────────────────────────
_WMO: dict[int, str] = {
    0: "ясно ☀️", 1: "преим. ясно 🌤", 2: "переменная облачность ⛅️", 3: "пасмурно ☁️",
    45: "туман 🌫", 48: "туман с инеем 🌫",
    51: "лёгкая морось 🌦", 53: "морось 🌦", 55: "сильная морось 🌧",
    61: "небольшой дождь 🌧", 63: "дождь 🌧", 65: "сильный дождь 🌧",
    71: "небольшой снег 🌨", 73: "снег 🌨", 75: "сильный снег ❄️",
    80: "ливень 🌩", 81: "ливни 🌩", 82: "сильный ливень ⛈",
    95: "гроза ⛈", 96: "гроза с градом ⛈", 99: "сильная гроза ⛈",
}

# ── Known cities fast lookup ───────────────────────────────────────────────────
KNOWN_CITIES: dict[str, tuple[float, float, str, str]] = {
    "москва": (55.75, 37.62, "Europe/Moscow", "Москва"),
    "moscow": (55.75, 37.62, "Europe/Moscow", "Москва"),
    "санкт-петербург": (59.93, 30.32, "Europe/Moscow", "Санкт-Петербург"),
    "tokyo": (35.68, 139.69, "Asia/Tokyo", "Токио"),
    "токио": (35.68, 139.69, "Asia/Tokyo", "Токио"),
    "osaka": (34.69, 135.50, "Asia/Tokyo", "Осака"),
    "kyoto": (35.01, 135.77, "Asia/Tokyo", "Киото"),
    "yokohama": (35.44, 139.64, "Asia/Tokyo", "Йокогама"),
    "berlin": (52.52, 13.41, "Europe/Berlin", "Берлин"),
    "paris": (48.86, 2.35, "Europe/Paris", "Париж"),
    "london": (51.51, -0.13, "Europe/London", "Лондон"),
    "new york": (40.71, -74.01, "America/New_York", "Нью-Йорк"),
    "dubai": (25.28, 55.30, "Asia/Dubai", "Дубай"),
    "istanbul": (41.01, 28.98, "Europe/Istanbul", "Стамбул"),
    "bali": (-8.41, 115.19, "Asia/Makassar", "Бали"),
    "bangkok": (13.76, 100.50, "Asia/Bangkok", "Бангкок"),
    "singapore": (1.35, 103.82, "Asia/Singapore", "Сингапур"),
    "beijing": (39.90, 116.40, "Asia/Shanghai", "Пекин"),
    "seoul": (37.57, 126.98, "Asia/Seoul", "Сеул"),
}

# ── Callback data for inline buttons ──────────────────────────────────────────
class _LocSuggestCB(CallbackData, prefix="loc_sug"):
    action: str   # "yes" | "no" | "manual"
    city: str     # "yes"→suggested area, "no"→base city, "manual"→""


# ── Weather ───────────────────────────────────────────────────────────────────

def _fetch_weather(lat: float, lon: float, tz: str) -> str:
    """Fetch current weather from Open-Meteo. Returns formatted string."""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current_weather=true"
            "&hourly=precipitation_probability,apparent_temperature"
            f"&timezone={urllib.parse.quote(tz)}&forecast_days=1"
        )
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        cw = d["current_weather"]
        desc = _WMO.get(int(cw["weathercode"]), f"код {cw['weathercode']}")
        temp = cw["temperature"]
        wind = cw["windspeed"]
        hour = datetime.now().hour
        feels_arr = d["hourly"].get("apparent_temperature", [])
        precip_arr = d["hourly"].get("precipitation_probability", [])
        feels = feels_arr[min(hour, len(feels_arr) - 1)] if feels_arr else None
        precip = precip_arr[min(hour, len(precip_arr) - 1)] if precip_arr else None
        feels_str = f"{feels:+.0f}°" if isinstance(feels, (int, float)) else "?"
        precip_str = f"{precip}%" if isinstance(precip, (int, float)) else "?"
        return f"{desc}, {temp:+.0f}°C (ощущается {feels_str}), ветер {wind:.0f} км/ч, осадки {precip_str}"
    except Exception as e:
        logger.warning("Weather fetch failed: %s", e)
        return "погода недоступна"


# ── Location hint via vault + Claude CLI ─────────────────────────────────────

def _find_location_hint(vault_path: Path, base_city: str) -> str | None:
    """Read last 3 daily notes and use Claude CLI (haiku) to find specific area.

    Returns "Area, BaseCity" string (max 50 chars) or None if nothing found.
    """
    daily_dir = vault_path / "daily"
    if not daily_dir.exists():
        return None

    files = sorted(daily_dir.glob("*.md"), reverse=True)[:3]
    if not files:
        return None

    content = ""
    for f in files:
        try:
            content += f"\n\n=== {f.stem} ===\n" + f.read_text(encoding="utf-8")[:3000]
        except Exception:
            pass

    if not content.strip():
        return None

    prompt = (
        f"Пользователь сейчас в {base_city}. "
        "Найди в дневниковых записях ниже точное упоминание конкретного места: "
        "район, улица, отель, станция метро, достопримечательность.\n\n"
        f"{content}\n\n"
        "Верни ТОЛЬКО одну строку JSON без markdown:\n"
        '{"area": "название места или null"}\n'
        'Примеры: {"area": "Namba"} или {"area": null}'
    )

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "claude-haiku-4-5-20251001", "-p", prompt],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            return None
        output = result.stdout.strip()
        # Strip markdown code fence if present
        if "```" in output:
            output = output.split("```")[1].lstrip("json").strip()
        data = json.loads(output)
        area = data.get("area")
        if area and str(area).lower() not in ("null", "none", ""):
            full = f"{area}, {base_city}"
            return full[:50]
        return None
    except Exception as e:
        logger.warning("Location hint failed: %s", e)
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_city(name: str) -> tuple[float, float, str, str] | None:
    """Resolve city name to (lat, lon, timezone, display_name)."""
    key = name.lower().strip()
    if key in KNOWN_CITIES:
        return KNOWN_CITIES[key]

    try:
        encoded = urllib.parse.quote(name)
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1&language=ru"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
        results = data.get("results")
        if not results:
            return None
        r = results[0]
        return (r["latitude"], r["longitude"], r["timezone"], r["name"])
    except Exception as e:
        logger.warning("Geocoding API failed for %s: %s", name, e)
        return None


def update_env_file(lat: float, lon: float, tz: str, city: str) -> None:
    """Update LOCATION_* variables in .env file."""
    env_path = get_settings().vault_path.parent / ".env"
    lines = env_path.read_text().splitlines()
    filtered = [
        ln for ln in lines
        if not ln.startswith(("LOCATION_CITY=", "LOCATION_LAT=", "LOCATION_LON=", "LOCATION_TZ="))
    ]
    filtered.extend([
        f"LOCATION_CITY={city}",
        f"LOCATION_LAT={lat}",
        f"LOCATION_LON={lon}",
        f"LOCATION_TZ={tz}",
    ])
    env_path.write_text("\n".join(filtered) + "\n")


def set_system_timezone(tz: str) -> bool:
    """Set system timezone via timedatectl."""
    try:
        subprocess.run(
            ["sudo", "timedatectl", "set-timezone", tz],
            check=True, capture_output=True, timeout=10,
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error("timedatectl failed: %s", e.stderr)
        return False


def _make_suggest_kb(hint: str, base_city: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Да",
            callback_data=_LocSuggestCB(action="yes", city=hint[:45]).pack(),
        ),
        InlineKeyboardButton(
            text="❌ Нет",
            callback_data=_LocSuggestCB(action="no", city=base_city[:45]).pack(),
        ),
        InlineKeyboardButton(
            text="✏️ Ввести",
            callback_data=_LocSuggestCB(action="manual", city="").pack(),
        ),
    ]])


# ── Handlers ──────────────────────────────────────────────────────────────────

@router.message(Command("location"))
async def cmd_location(message: Message, command: CommandObject) -> None:
    """Handle /location [city] command."""
    if not command.args:
        settings = get_settings()
        city = getattr(settings, "location_city", "Москва")
        tz = getattr(settings, "location_tz", "Europe/Moscow")
        lat = getattr(settings, "location_lat", 55.75)
        lon = getattr(settings, "location_lon", 37.62)
        weather = await asyncio.to_thread(_fetch_weather, lat, lon, tz)
        await message.answer(
            f"📍 <b>Текущая локация:</b> {city}\n"
            f"🕐 <b>Таймзона:</b> {tz}\n"
            f"🌤 {weather}\n\n"
            "Чтобы сменить: <code>/location Tokyo</code>"
        )
        return

    city_input = command.args.strip()
    result = resolve_city(city_input)

    if result is None:
        await message.answer(
            f"❌ Город <b>{city_input}</b> не найден.\n\n"
            "Попробуй на английском или проверь название."
        )
        return

    lat, lon, tz, display_name = result
    update_env_file(lat, lon, tz, display_name)
    tz_ok = set_system_timezone(tz)
    if hasattr(get_settings, "cache_clear"):
        get_settings.cache_clear()

    tz_note = "" if tz_ok else " ⚠️"

    # Fetch weather + look for vault location hint in parallel
    settings = get_settings()
    weather, hint = await asyncio.gather(
        asyncio.to_thread(_fetch_weather, lat, lon, tz),
        asyncio.to_thread(_find_location_hint, settings.vault_path, display_name),
    )

    base_text = (
        f"✅ <b>Локация обновлена!</b>\n\n"
        f"📍 {display_name}{tz_note}\n"
        f"🕐 {tz}\n"
        f"🌤 {weather}"
    )

    if hint:
        await message.answer(
            base_text + f"\n\n📌 Судя по записям, ты в <b>{hint}</b> — уточнить локацию?",
            reply_markup=_make_suggest_kb(hint, display_name),
        )
    else:
        await message.answer(base_text)


@router.callback_query(_LocSuggestCB.filter())
async def _on_loc_suggest(query: CallbackQuery, callback_data: _LocSuggestCB) -> None:
    """Handle location suggestion inline buttons (Да / Нет / Ввести вручную)."""
    action = callback_data.action

    if action == "yes":
        city = callback_data.city
        result = resolve_city(city)
        if result:
            lat, lon, tz, display_name = result
            update_env_file(lat, lon, tz, display_name)
            set_system_timezone(tz)
            if hasattr(get_settings, "cache_clear"):
                get_settings.cache_clear()
            weather = await asyncio.to_thread(_fetch_weather, lat, lon, tz)
            await query.message.edit_text(
                f"✅ Уточнено: <b>{display_name}</b>\n"
                f"🕐 {tz}\n"
                f"🌤 {weather}",
                reply_markup=None,
            )
        else:
            await query.message.edit_text(
                f"⚠️ Не удалось уточнить <b>{city}</b> — оставлено как есть.",
                reply_markup=None,
            )

    elif action == "no":
        city = callback_data.city
        await query.message.edit_text(
            f"📍 Оставлено: <b>{city}</b>",
            reply_markup=None,
        )

    elif action == "manual":
        await query.message.edit_text(
            "Введи: <code>/location &lt;название города&gt;</code>",
            reply_markup=None,
        )

    await query.answer()
