"""
ElevenLabs text-to-speech (MP3 bytes only — no reasoning).
"""

from __future__ import annotations

import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_SPEECH_CHARS = 1500


def synthesize_speech(text: str) -> tuple[bytes | None, str]:
    """
    Return (mp3_bytes_or_none, error_message).
    Empty error_message means success.
    """
    key = (getattr(settings, "ELEVENLABS_API_KEY", None) or "").strip()
    if not key:
        return None, "ElevenLabs API key is not configured."

    voice_id = (getattr(settings, "ELEVENLABS_VOICE_ID", None) or "").strip()
    if not voice_id:
        return None, "ELEVENLABS_VOICE_ID is not configured."

    model_id = (getattr(settings, "ELEVENLABS_MODEL", None) or "").strip() or "eleven_multilingual_v2"
    body_text = (text or "").strip()
    if not body_text:
        return None, "No text to synthesize."
    if len(body_text) > MAX_SPEECH_CHARS:
        body_text = body_text[:MAX_SPEECH_CHARS]

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key,
    }
    payload = {
        "text": body_text,
        "model_id": model_id,
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=120)
        ct = (r.headers.get("Content-Type") or "").split(";")[0].strip()
        body_len = len(r.content) if r.content else 0
        logger.info(
            "ElevenLabs TTS response status=%s content_length=%s bytes=%s mime=%s text_chars=%s",
            r.status_code,
            r.headers.get("Content-Length"),
            body_len,
            ct,
            len(body_text),
        )
        if r.status_code >= 400:
            return None, f"ElevenLabs error {r.status_code}: {r.text[:500]}"
        if body_len < 100:
            logger.warning("ElevenLabs TTS: unusually small MP3 (%s bytes)", body_len)
        return r.content, ""
    except requests.RequestException as exc:
        logger.warning("ElevenLabs request failed: %s", exc)
        return None, f"ElevenLabs request failed: {exc}"
