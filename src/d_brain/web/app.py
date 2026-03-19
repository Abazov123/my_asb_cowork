"""Web upload portal for large audio files (meeting recordings)."""

import logging
from datetime import datetime

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from d_brain.config import get_settings
from d_brain.services.corrections import CorrectionsService
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage
from d_brain.services.transcription import (
    DeepgramTranscriber,
    build_confidence_note,
    format_diarized,
    identify_user_speaker,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="d-brain", docs_url=None, redoc_url=None)

_UPLOAD_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>d-brain</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:#0f0f0f;color:#e0e0e0;min-height:100vh;
         display:flex;align-items:center;justify-content:center;padding:20px}
    .card{background:#1a1a1a;border-radius:16px;padding:32px;
          max-width:420px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,.4)}
    h1{font-size:20px;font-weight:600;margin-bottom:6px}
    .sub{font-size:13px;color:#888;margin-bottom:28px}
    .field{margin-bottom:18px}
    label.lbl{display:block;font-size:12px;color:#aaa;margin-bottom:7px}
    .fa{display:block;width:100%;padding:14px;background:#222;
        border:2px dashed #444;border-radius:10px;color:#ccc;
        font-size:14px;text-align:center;cursor:pointer;transition:border-color .2s}
    .fa:hover{border-color:#6366f1}
    input[type=file]{display:none}
    .fn{font-size:12px;color:#6366f1;margin-top:7px;min-height:16px}
    .tog{display:flex;align-items:flex-start;gap:12px;padding:14px;
         background:#222;border-radius:10px;cursor:pointer}
    .tog input{width:18px;height:18px;accent-color:#6366f1;cursor:pointer;
               margin-top:2px;flex-shrink:0}
    .tl{font-size:14px}.td{font-size:12px;color:#666;margin-top:3px}
    button[type=submit]{width:100%;padding:16px;background:#6366f1;border:none;
                        border-radius:10px;color:#fff;font-size:16px;font-weight:600;
                        cursor:pointer;margin-top:10px;transition:background .2s}
    button:hover{background:#4f52d6}
    button:disabled{background:#333;cursor:not-allowed}
    .fmt{font-size:11px;color:#555;text-align:center;margin-top:14px}
  </style>
</head>
<body>
<div class="card">
  <h1>&#127911; d-brain</h1>
  <p class="sub">Загрузи запись встречи — транскрипция придёт в Telegram</p>
  <form method="post" enctype="multipart/form-data" id="frm">
    <div class="field">
      <label class="lbl">Файл записи</label>
      <label class="fa" for="f">Выбрать файл</label>
      <input type="file" id="f" name="file" accept="audio/*,video/mp4"
             onchange="document.getElementById('fn').textContent=this.files[0]?.name||''">
      <div class="fn" id="fn"></div>
    </div>
    <div class="field">
      <label class="tog">
        <input type="checkbox" name="diarize" value="1" checked>
        <div>
          <div class="tl">Разделить по голосам</div>
          <div class="td">Для встреч с несколькими участниками</div>
        </div>
      </label>
    </div>
    <button type="submit" id="btn">Отправить</button>
    <p class="fmt">m4a &middot; mp3 &middot; ogg &middot; wav &middot; opus &middot; flac &middot; mp4</p>
  </form>
  <script>
    document.getElementById('frm').onsubmit = function() {
      if (!document.getElementById('f').files[0]) {
        alert('Выбери файл'); return false;
      }
      document.getElementById('btn').disabled = true;
      document.getElementById('btn').textContent = 'Обрабатывается\u2026';
    };
  </script>
</div>
</body></html>"""

_RESULT_TMPL = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>d-brain &middot; {title}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:#0f0f0f;color:#e0e0e0;min-height:100vh;
         display:flex;align-items:center;justify-content:center;padding:20px}}
    .card{{background:#1a1a1a;border-radius:16px;padding:32px;
           max-width:420px;width:100%;text-align:center}}
    .icon{{font-size:52px;margin-bottom:16px}}
    h2{{font-size:20px;margin-bottom:10px}}
    p{{color:#888;font-size:14px;margin-bottom:24px}}
    a{{display:block;padding:14px;background:#222;border-radius:10px;
       color:#6366f1;text-decoration:none;font-size:14px}}
  </style>
</head>
<body>
<div class="card">
  <div class="icon">{icon}</div>
  <h2>{title}</h2>
  <p>{message}</p>
  <a href="/">&#8592; Загрузить ещё</a>
</div>
</body></html>"""


def _result(icon: str, title: str, message: str) -> HTMLResponse:
    return HTMLResponse(_RESULT_TMPL.format(icon=icon, title=title, message=message))


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return _UPLOAD_HTML


@app.post("/", response_class=HTMLResponse)
async def upload(
    file: UploadFile = File(...),
    diarize: str = Form(default=""),
) -> HTMLResponse:
    settings = get_settings()
    use_diarize = diarize == "1"

    # File size limit: 100MB
    MAX_SIZE = 100 * 1024 * 1024
    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        return HTMLResponse("<h2>Файл слишком большой (макс. 100 MB)</h2>", status_code=413)
    try:
        audio_bytes = content
        filename = file.filename or "audio"
        size_mb = len(audio_bytes) / 1024 / 1024
        logger.info("Web upload: %s %.1f MB diarize=%s", filename, size_mb, use_diarize)

        transcriber = DeepgramTranscriber(settings.deepgram_api_key)

        if use_diarize:
            utterances = await transcriber.transcribe_diarized(audio_bytes)
            if not utterances:
                return _result("❌", "Ошибка", "Не удалось распознать речь в файле.")

            user_speaker, is_confident = identify_user_speaker(utterances)
            num_speakers = len({u.speaker for u in utterances})
            transcript = format_diarized(utterances, user_speaker)
            source_tag = f"[web-meeting · {num_speakers} speakers]"
            confidence_note = (
                ""
                if is_confident or num_speakers == 1
                else build_confidence_note(utterances, user_speaker)
            )
        else:
            transcript = await transcriber.transcribe(audio_bytes)
            if not transcript:
                return _result("❌", "Ошибка", "Не удалось распознать речь в файле.")
            source_tag = "[web-voice]"
            confidence_note = ""
            num_speakers = 1

        corrections = CorrectionsService(settings.vault_path)
        corrected, applied = corrections.apply(transcript)

        storage = VaultStorage(settings.vault_path)
        storage.append_to_daily(corrected, datetime.now(), source_tag)

        user_id = settings.allowed_user_ids[0] if settings.allowed_user_ids else 0
        session = SessionStore(settings.vault_path)
        session.append(user_id, "web-voice", text=corrected)

        tg_text = (
            f"🌐 {filename} ({size_mb:.1f} MB)\n\n"
            + corrected
            + confidence_note
            + "\n\n✓ Сохранено"
        )
        if applied:
            tg_text += f" · Исправлено: {', '.join(applied)}"

        await _send_telegram(settings.telegram_bot_token, user_id, tg_text)

        return _result(
            "✅",
            "Готово",
            f"Транскрипция отправлена в Telegram · {len(corrected)} символов",
        )

    except Exception as e:
        logger.exception("Web upload error")
        return _result("❌", "Ошибка", str(e))


async def _send_telegram(token: str, user_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(text), 4000):
            await client.post(url, json={"chat_id": user_id, "text": text[i : i + 4000]})
