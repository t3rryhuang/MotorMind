"""
YouTube helpers: video id parsing, oEmbed metadata, caption transcripts.

No YouTube Data API key required for oEmbed or captions (youtube-transcript-api).
"""

from __future__ import annotations

import logging
from typing import Any
import requests

from courses.utils import extract_youtube_video_id as _extract_from_utils

logger = logging.getLogger(__name__)

OEMBED_URL = "https://www.youtube.com/oembed"


def extract_youtube_video_id(url: str) -> str:
    """Delegate to shared parser (youtu.be, watch, embed, shorts, etc.)."""
    return _extract_from_utils(url)


def get_youtube_oembed_metadata(video_url: str) -> dict[str, Any]:
    """
    Fetch title, channel (author_name), and thumbnail from YouTube oEmbed.

    Returns keys: title, author_name, thumbnail_url (may be empty strings on failure).
    """
    out: dict[str, Any] = {
        "title": "",
        "author_name": "",
        "thumbnail_url": "",
        "raw_error": "",
    }
    url = (video_url or "").strip()
    if not url:
        out["raw_error"] = "Empty URL."
        return out
    try:
        resp = requests.get(
            OEMBED_URL,
            params={"url": url, "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.info("oEmbed request failed: %s", exc)
        out["raw_error"] = str(exc)
        return out
    except ValueError:
        out["raw_error"] = "Invalid JSON from oEmbed."
        return out

    out["title"] = (data.get("title") or "").strip()
    out["author_name"] = (data.get("author_name") or "").strip()
    out["thumbnail_url"] = (data.get("thumbnail_url") or "").strip()
    return out


def get_youtube_description_ytdlp(video_url: str) -> str:
    """
    Best-effort full video description via yt-dlp (no API key).

    Returns empty string if yt-dlp is unavailable or extraction fails.
    """
    url = (video_url or "").strip()
    if not url:
        return ""
    try:
        import yt_dlp
    except ImportError:
        return ""
    try:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 15,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return (info.get("description") or "").strip()
    except Exception as exc:
        logger.info("yt-dlp description fetch failed: %s", exc)
        return ""


def get_youtube_transcript(video_url: str) -> dict[str, Any]:
    """
    Pull captions via youtube-transcript-api.

    Prefers manually created English, then generated English.

    Returns:
        transcript: plain text
        segments: list of {start, duration, text}
        source: machine code (youtube_captions_manual_en / youtube_captions_generated_en)
        transcript_source_label: human-readable source label
        error: empty on success, or user-facing message
    """
    result: dict[str, Any] = {
        "transcript": "",
        "segments": [],
        "source": "",
        "transcript_source_label": "",
        "error": "",
    }
    vid = extract_youtube_video_id(video_url or "")
    if not vid:
        result["error"] = "Not a recognized YouTube URL."
        return result

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            NoTranscriptFound,
            TranscriptsDisabled,
            VideoUnavailable,
            YouTubeRequestFailed,
        )
    except ImportError:
        result["error"] = "youtube-transcript-api is not installed."
        return result

    api = YouTubeTranscriptApi()
    try:
        tlist = api.list(vid)
    except (VideoUnavailable, YouTubeRequestFailed, Exception) as exc:
        logger.info("Could not list transcripts for %s: %s", vid, exc)
        result["error"] = "No YouTube captions available for this video."
        return result

    transcript_obj = None
    source_code = ""
    label = ""
    try:
        transcript_obj = tlist.find_manually_created_transcript(["en"])
        source_code = "youtube_captions_manual_en"
        label = "YouTube captions"
    except NoTranscriptFound:
        try:
            transcript_obj = tlist.find_generated_transcript(["en"])
            source_code = "youtube_captions_generated_en"
            label = "Auto-generated YouTube captions"
        except NoTranscriptFound:
            try:
                transcript_obj = tlist.find_transcript(["en"])
                if getattr(transcript_obj, "is_generated", False):
                    source_code = "youtube_captions_generated_en"
                    label = "Auto-generated YouTube captions"
                else:
                    source_code = "youtube_captions_manual_en"
                    label = "YouTube captions"
            except NoTranscriptFound:
                pass
    except TranscriptsDisabled:
        result["error"] = "No YouTube captions available for this video."
        return result

    if transcript_obj is None:
        result["error"] = "No YouTube captions available for this video."
        return result

    try:
        raw = transcript_obj.fetch()
    except Exception as exc:
        logger.info("Transcript fetch failed for %s: %s", vid, exc)
        result["error"] = "No YouTube captions available for this video."
        return result

    # Newer youtube-transcript-api returns FetchedTranscript with .to_raw_data() (list of dicts).
    if hasattr(raw, "to_raw_data"):
        segment_rows: list[dict[str, Any]] = raw.to_raw_data()
    else:
        segment_rows = []
        for seg in raw:
            if isinstance(seg, dict):
                segment_rows.append(seg)
            else:
                segment_rows.append(
                    {
                        "text": getattr(seg, "text", "") or "",
                        "start": float(getattr(seg, "start", 0.0)),
                        "duration": float(getattr(seg, "duration", 0.0)),
                    }
                )

    segments_out: list[dict[str, Any]] = []
    lines: list[str] = []
    for seg in segment_rows:
        text = (seg.get("text") or "").replace("\n", " ").strip()
        start = float(seg.get("start", 0.0))
        dur = float(seg.get("duration", 0.0))
        segments_out.append({"start": start, "duration": dur, "text": text})
        if text:
            lines.append(text)

    result["transcript"] = "\n".join(lines)
    result["segments"] = segments_out
    result["source"] = source_code
    result["transcript_source_label"] = label
    return result


def build_youtube_autofill_response(video_url: str) -> dict[str, Any]:
    """Combined payload for the teacher autofill API."""
    warnings: list[str] = []
    url = (video_url or "").strip()

    oembed = get_youtube_oembed_metadata(url)
    title = oembed.get("title") or ""
    thumb = oembed.get("thumbnail_url") or ""
    youtube_description = get_youtube_description_ytdlp(url)

    tr = get_youtube_transcript(url)
    transcript = tr.get("transcript") or ""
    transcript_source_code = tr.get("source") or ""
    transcript_label = tr.get("transcript_source_label") or ""

    if not transcript.strip():
        warnings.append(
            "No captions found. Add transcript manually or configure an audio transcription service later."
        )

    # TODO: if captions unavailable, optionally use yt-dlp for metadata-only / future Whisper transcription.

    return {
        "success": True,
        "title": title,
        "youtube_description": youtube_description,
        "thumbnail_url": thumb,
        "transcript": transcript,
        "transcript_source": transcript_label,
        "transcript_source_code": transcript_source_code,
        "warnings": warnings,
    }
