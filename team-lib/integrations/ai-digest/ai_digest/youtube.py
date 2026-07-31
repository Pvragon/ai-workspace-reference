"""YouTube ingest adapter (Phase 1).

New-item detection uses yt-dlp's flat playlist extraction on a channel's
``/videos`` tab (free, no API key, no per-video network). Transcripts come from
youtube-transcript-api (free auto-captions). yt-dlp remains the documented
fallback for transcripts but is not needed for the common path.

The RSS feed path (feeds/videos.xml) was evaluated and rejected: YouTube's edge
returns 404 for that endpoint from server hosts. yt-dlp flat extraction is the
robust substitute and doubles as the transcript fallback.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .record import Item

SOURCE = "youtube"


def list_recent(handle: str, limit: int) -> list[dict]:
    """Return up to ``limit`` most-recent uploads for a channel handle.

    Each dict: {id, title, url}. Raises on hard failures (caller catches per
    channel so one dead handle never aborts the whole poll).
    """
    import yt_dlp  # lazy: keeps import cost out of non-poll commands

    url = f"https://www.youtube.com/{handle}/videos"
    opts = {
        "extract_flat": True,
        "playlist_items": f"1:{max(1, limit)}",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False)
    out = []
    for e in (info or {}).get("entries", []) or []:
        vid = e.get("id")
        if not vid:
            continue
        out.append({
            "id": vid,
            "title": e.get("title") or "(untitled)",
            "url": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
        })
    return out


def list_playlist(url: str, limit: int = 50) -> list[dict]:
    """List videos in a playlist (flat; no per-video network). Each dict:
    {id, title, url, producer}. Used by `digest learn` — a user-curated playlist,
    so no filtering; every new item gets summarized."""
    import yt_dlp

    opts = {
        "extract_flat": True,
        "playlist_items": f"1:{max(1, limit)}",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False)
    out = []
    for e in (info or {}).get("entries", []) or []:
        vid = e.get("id")
        if not vid:
            continue
        out.append({
            "id": vid,
            "title": e.get("title") or "(untitled)",
            "url": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
            "producer": e.get("uploader") or e.get("channel") or "",
            "duration": e.get("duration"),
        })
    return out


class TranscriptBlocked(Exception):
    """YouTube blocked the transcript request (IP ban / PO-token / rate limit).

    Distinct from 'no captions': a block means STOP the whole poll (retrying just
    deepens the ban); no-captions means skip this one video and continue.
    """


# transcript-api exception class names that mean "blocked", not "no captions"
_BLOCK_NAMES = {"IpBlocked", "RequestBlocked", "PoTokenRequired", "YouTubeRequestFailed"}


def build_session(cookies_file: Optional[str]):
    """A requests.Session preloaded with a Netscape cookies.txt, or None.

    Authenticated (logged-in) transcript requests are treated far more leniently
    by YouTube and are the reliable fix for persistent IP/PO-token blocks.
    """
    if not cookies_file:
        return None
    import http.cookiejar
    from pathlib import Path
    import requests

    p = Path(cookies_file).expanduser()
    if not p.exists():
        return None
    jar = http.cookiejar.MozillaCookieJar(str(p))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception:
        return None
    s = requests.Session()
    s.cookies = jar  # type: ignore[assignment]
    return s


def _transcript_api(video_id: str, session=None) -> Optional[str]:
    from youtube_transcript_api import YouTubeTranscriptApi as Y
    langs = ["en", "en-US", "en-GB"]
    try:
        api = Y(http_client=session) if session is not None else Y()
        try:
            fetched = api.fetch(video_id, languages=langs)
        except TypeError:
            fetched = api.fetch(video_id)
        chunks = fetched.to_raw_data()
    except AttributeError:                     # legacy classmethod API
        chunks = Y.get_transcript(video_id, languages=langs)
    except Exception as e:                     # noqa: BLE001
        name = type(e).__name__
        if name in _BLOCK_NAMES or "block" in str(e).lower() or "too many requests" in str(e).lower():
            raise TranscriptBlocked(f"{name}: {str(e)[:120]}") from e
        return None                            # genuinely no captions / disabled
    return " ".join(c.get("text", "") for c in chunks).strip() or None


def _transcript_ytdlp(video_id: str, cookies_file: Optional[str] = None,
                      cookies_from_browser: Optional[str] = None,
                      js_runtime: Optional[str] = None) -> Optional[str]:
    """Fallback: pull auto-captions via yt-dlp. With cookies + a JS runtime this
    can generate PO tokens and dodge blocks the plain API can't."""
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as td:
        out = str(Path(td) / "%(id)s")
        cmd = ["yt-dlp", "--skip-download", "--write-auto-subs",
               "--sub-langs", "en.*", "--sub-format", "json3/vtt", "-o", out]
        if cookies_file:
            cmd += ["--cookies", str(Path(cookies_file).expanduser())]
        elif cookies_from_browser:
            cmd += ["--cookies-from-browser", cookies_from_browser]
        if js_runtime:
            cmd += ["--js-runtimes", js_runtime]
            # Current yt-dlp moved YouTube's JS "n-challenge" solver to an opt-in
            # remote component (EJS); without it, subtitle/format extraction fails
            # even with a valid JS runtime. Fetches a small solver from GitHub once,
            # then cached. Required as of yt-dlp 2025.x for authenticated sub pulls.
            cmd += ["--remote-components", "ejs:github"]
        cmd.append(url)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        err = (r.stderr or "").lower()
        if "429" in err or "too many requests" in err or "sign in to confirm" in err or "blocked" in err:
            raise TranscriptBlocked(f"yt-dlp: {(r.stderr or '')[:120]}")
        files = list(Path(td).glob("*.json3")) + list(Path(td).glob("*.en*.vtt")) + list(Path(td).glob("*.vtt"))
        if not files:
            return None
        f = files[0]
        raw = f.read_text(errors="ignore")
        if f.suffix == ".json3":
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return None
            parts = []
            for ev in data.get("events", []):
                for seg in ev.get("segs", []) or []:
                    parts.append(seg.get("utf8", ""))
            return " ".join(parts).replace("\n", " ").strip() or None
        # crude VTT strip: drop timestamps/cue headers
        import re
        lines = []
        for ln in raw.splitlines():
            if not ln.strip() or "-->" in ln or ln.strip().isdigit() or ln.startswith("WEBVTT"):
                continue
            lines.append(re.sub(r"<[^>]+>", "", ln))
        return " ".join(lines).strip() or None


def fetch_metadata(video_id: str) -> tuple:
    """(publish_datetime_or_None, description_str) from the watch page in ONE GET.

    Cheap page-path request (NOT the transcript endpoint that triggers IP bans —
    it survived our block). Gives date + description for the pre-transcript gate.
    """
    import json
    import re
    import urllib.request
    from datetime import datetime

    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception:
        return None, ""

    ts = None
    m = (re.search(r'"uploadDate":"([^"]+)"', html)
         or re.search(r'itemprop="datePublished"\s+content="([^"]+)"', html))
    if m:
        try:
            ts = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        except ValueError:
            ts = None

    desc = ""
    d = re.search(r'"shortDescription":"((?:[^"\\]|\\.)*)"', html)
    if d:
        try:
            desc = json.loads('"' + d.group(1) + '"')
        except json.JSONDecodeError:
            desc = d.group(1)
    if not desc:
        og = re.search(r'<meta name="description" content="([^"]*)"', html)
        if og:
            desc = og.group(1)
    return ts, (desc or "")[:600]


def upload_ts(video_id: str):
    """Back-compat thin wrapper — publish datetime only."""
    return fetch_metadata(video_id)[0]


def fetch_transcript(video_id: str, session=None, cookies_file: Optional[str] = None,
                     cookies_from_browser: Optional[str] = None,
                     js_runtime: Optional[str] = None) -> Optional[str]:
    """Best-effort English transcript. Fast API first, yt-dlp fallback.

    Returns None only if the video genuinely has no captions. Raises
    TranscriptBlocked if YouTube blocked us on BOTH paths — the caller must then
    abort the poll and enter cooldown rather than keep hammering.
    """
    api_blocked = False
    try:
        text = _transcript_api(video_id, session=session)
        if text:
            return text
    except TranscriptBlocked:
        api_blocked = True                     # try yt-dlp (cookies may rescue it)

    try:
        text = _transcript_ytdlp(video_id, cookies_file, cookies_from_browser, js_runtime)
        if text:
            return text
    except TranscriptBlocked:
        raise                                  # both paths blocked -> propagate
    # yt-dlp returned no captions. If the API had been blocked, we can't be sure
    # captions truly don't exist -> treat as blocked so the poll backs off safely.
    if api_blocked:
        raise TranscriptBlocked("both transcript paths blocked")
    return None


def _nap(base: float):
    import random
    import time
    if base > 0:
        time.sleep(base + random.uniform(0, base * 0.5))   # jitter avoids a fixed pattern


# ── Stage 1: cheap scan ─────────────────────────────────────────────────────
def list_candidates(
    channels: Iterable[dict],
    is_seen,                       # callable(uid)->bool
    scan_per_channel: int,
    channel_delay_sec: float = 3.0,
    log=lambda *a: None,
) -> tuple[list[dict], list[str]]:
    """Scan every channel for NEW (unseen) uploads — TITLES ONLY, no transcripts.

    Uses yt-dlp flat listing (1 request/channel; NOT the transcript endpoint that
    triggers IP blocks). Returns candidate dicts {uid,id,title,producer,url} for
    the downselect stage. This is the "get high-level details first" pass — safe
    to run across all channels.
    """
    cands: list[dict] = []
    warnings: list[str] = []
    for ci, ch in enumerate(channels):
        name = ch.get("name") or ch.get("handle") or "?"
        handle = ch.get("handle")
        if not handle:
            warnings.append(f"{name}: no handle in config; skipped")
            continue
        if ci > 0:
            _nap(channel_delay_sec)
        try:
            recent = list_recent(handle, max(scan_per_channel * 2, scan_per_channel))
        except Exception as e:
            warnings.append(f"{name} ({handle}): list failed — {type(e).__name__}; skipped")
            continue
        added = 0
        for v in recent:
            if added >= scan_per_channel:
                break
            uid = f"{SOURCE}:{v['id']}"
            if is_seen(uid):
                continue
            cands.append({"uid": uid, "id": v["id"], "title": v["title"],
                          "producer": name, "url": v["url"]})
            added += 1
    log(f"  scanned {len(list(channels)) if hasattr(channels, '__len__') else '?'} channels "
        f"→ {len(cands)} new candidate titles")
    return cands, warnings


# ── Stage 3: transcript fetch for the vetted shortlist only ─────────────────
# ── Stage 2.5: metadata enrichment (page GETs; NOT the transcript endpoint) ──
def collect_metadata(
    cands: list[dict],
    cutoff_ts,                     # tz-aware datetime or None
    request_delay_sec: float = 4.0,
    log=lambda *a: None,
) -> tuple[list[dict], list[str]]:
    """For each candidate, ONE watch-page GET → date + description (no transcript).
    Applies recency here. Returns (results, warnings): result = {cand, status, published,
    description}; status in {ok, old}. Page GETs ride the lenient (non-transcript)
    budget, so this is safe to run on more candidates than we will transcript.
    """
    results: list[dict] = []
    warnings: list[str] = []
    for i, c in enumerate(cands):
        if i > 0:
            _nap(request_delay_sec)
        ts, desc = fetch_metadata(c["id"])
        if cutoff_ts is not None and ts is not None and ts < cutoff_ts:
            results.append({"cand": c, "status": "old", "published": "", "description": desc})
            continue
        results.append({"cand": c, "status": "ok",
                        "published": ts.isoformat() if ts else "", "description": desc})
    return results, warnings


# ── Stage 3: transcript fetch (rate-paced; the guard-sensitive endpoint) ─────
def fetch_transcripts(
    kept: list[dict],              # [{cand, published, description}]
    transcript_max_chars: int,
    min_interval_sec: float = 20.0,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
    js_runtime: Optional[str] = None,
    log=lambda *a: None,
) -> tuple[list[dict], list[str], bool]:
    """Fetch transcripts for the vetted+budgeted shortlist, STEADILY PACED at
    ~min_interval_sec apart (+jitter) so we never burst the transcript endpoint.
    Returns (results, warnings, blocked); result = {cand, status, item}; status in
    {ok, nocaps}. The first TranscriptBlocked aborts (leaves the rest unseen)."""
    session = build_session(cookies_file)
    results: list[dict] = []
    warnings: list[str] = []
    blocked = False
    for i, s in enumerate(kept):
        c = s["cand"]
        if i > 0:
            _nap(min_interval_sec)                   # steady spacing between transcript hits
        try:
            text = fetch_transcript(
                c["id"], session=session, cookies_file=cookies_file,
                cookies_from_browser=cookies_from_browser, js_runtime=js_runtime)
        except TranscriptBlocked as e:
            warnings.append(f"ABORTED — YouTube blocked transcripts ({e}). "
                            f"Stopping to avoid deepening the ban; entering cooldown.")
            blocked = True
            break
        if not text:
            results.append({"cand": c, "status": "nocaps", "item": None})
            continue
        if len(text) > transcript_max_chars:
            text = text[:transcript_max_chars]
        item = Item(uid=c["uid"], source=SOURCE, producer=c["producer"],
                    title=c["title"], url=c["url"], text=text,
                    description=s.get("description", ""), published=s.get("published", ""))
        results.append({"cand": c, "status": "ok", "item": item})
        log(f"  + {c['producer']}: {c['title'][:70]}")
    return results, warnings, blocked
