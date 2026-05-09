import re
from urllib.parse import parse_qs, urlparse, unquote

_YT_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _valid_youtube_video_id(candidate: str) -> bool:
    return bool(candidate and _YT_VIDEO_ID_RE.fullmatch(candidate))


def extract_youtube_video_id(url: str) -> str:
    """
    Return the 11-character YouTube video id from a URL, or "" if not found/invalid.

    Supports youtu.be, youtube.com/watch, /embed/, /shorts/, /v/, and youtube-nocookie.com.
    """
    if not url or not isinstance(url, str):
        return ""
    raw = url.strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    if not parsed.netloc and raw.startswith("//"):
        parsed = urlparse("https:" + raw)

    netloc = (parsed.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path or ""
    parts = [unquote(p) for p in path.strip("/").split("/") if p]

    if netloc == "youtu.be":
        if parts:
            c = parts[0].split("?")[0].split("&")[0]
            if _valid_youtube_video_id(c):
                return c
        return ""

    if not (
        netloc == "youtube.com"
        or netloc.endswith(".youtube.com")
        or netloc == "youtube-nocookie.com"
        or netloc.endswith(".youtube-nocookie.com")
    ):
        return ""

    q = parse_qs(parsed.query)
    if "v" in q and q["v"]:
        c = (q["v"][0] or "").strip()
        if _valid_youtube_video_id(c):
            return c

    lowered = [p.lower() for p in parts]
    for key in ("embed", "shorts", "v", "live"):
        if key in lowered:
            i = lowered.index(key)
            if i + 1 < len(parts):
                c = parts[i + 1]
                if _valid_youtube_video_id(c):
                    return c

    return ""


def get_youtube_thumbnail_url(url: str) -> str:
    """Static hqdefault thumbnail URL, or "" if the URL is not a recognized YouTube link."""
    vid = extract_youtube_video_id(url)
    if not vid:
        return ""
    return f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
