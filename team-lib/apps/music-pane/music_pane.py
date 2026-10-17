#!/usr/bin/env python3
# ---
# template: app
# version: 2.5.3
# summary: Audio-only terminal music pane for a tiling desktop. Followed YouTube channels or a search feed an mpv playlist with no video (~0.7% of a core vs ~17% for a YouTube tab). Play/pause, volume, seek, next/prev, shuffle per channel or across all, favorites, and audio-reactive waves. Follows the Omarchy theme live.
# created: 2026-10-15
# last_updated: 2026-10-15
# maintainer: pvragon
# ---
"""Music pane: channel picker + audio-only playlist playback.

Channels live in ~/.config/music-pane/channels.txt, one YouTube channel link
per line ("#" comments allowed).

Picker (fzf): Enter opens or plays, Esc goes back. Top rows: search YouTube,
and shuffle every followed channel. Inside a channel, the first row shuffles
that channel. In search results, Ctrl+A follows the result's channel.

Player: mpv runs headless (--no-terminal) and the pane draws itself, talking
to mpv over its JSON IPC socket. Keys:
  space play/pause   up/down volume   left/right seek 10 s   [ ] seek 1 min
  n / p  next / previous   m mute   f follow this track's channel
  s save the track to favorites ("★ favorites" in the picker)   q back
While playing, translucent teal wave lines breathe in the free space under
the status line; they vanish when paused or loading.
Rows in the lists start with the publish date (YYMMDD, estimated by yt-dlp
from YouTube's "3 days ago" labels, so exact for recent uploads only).

Look: colors come from the current Omarchy theme and follow theme changes live
(neutral defaults elsewhere). The accent carries structure; orange is only a thin
mark for "active" (the pointer and the playing glyph), text stays neutral.

History: v1.0 matched fzf picks by text and crashed on trimmed padding. v1.1
asked to follow before anything played and used too much color. Some tracks
fail with the default stream ("EDL: Could not open source file"); asking for
m4a audio fixed every one tested (2026-10-15).

Usage: music_pane.py            run the pane
       music_pane.py --follow URL   follow the channel of a video (used by `f`)
"""
import json
import random
import re
import subprocess
import sys
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve()
CONF_DIR = Path.home() / ".config" / "music-pane"
CHANNELS = CONF_DIR / "channels.txt"
FAVORITES = CONF_DIR / "favorites.txt"      # date<TAB>title<TAB>link<TAB>channel
RETRY_LUA = CONF_DIR / "pane.lua"
THEME = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
LATEST = 15          # uploads listed per channel
SHUFFLE_DEPTH = 30   # uploads per channel pulled into a shuffle
SEARCH_HITS = 20     # results for a search
AUDIO = "bestaudio[ext=m4a]/bestaudio"

# Neutral fallback colors for terminals without an Omarchy theme. With Omarchy,
# every color comes from the current theme's colors.toml instead.
DEFAULTS = {"background": "#16181d", "foreground": "#c8ccd4", "light_foreground": "#e6e9ef",
            "accent": "#5fa8d3", "selection": "#2c3e50", "muted": "#6b7280", "orange": "#f08a4b",
            "lighter_background": "#1f232b"}
_theme_mtime = None


def palette():
    c = dict(DEFAULTS)
    try:
        # Themes can come from third-party repos: take only well-formed #rrggbb values.
        c.update({k: v for k, v in tomllib.loads(THEME.read_text()).items()
                  if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)})
    except (OSError, ValueError):
        pass
    return c


C = palette()


def refresh_palette():
    """Re-read the theme if it changed (Omarchy rewrites colors.toml on a theme switch)."""
    global _theme_mtime
    try:
        mtime = THEME.stat().st_mtime
    except OSError:
        mtime = None
    if mtime != _theme_mtime:
        _theme_mtime = mtime
        C.clear()
        C.update(palette())


refresh_palette()


# ── Untrusted input ─────────────────────────────────────────────────────────
# Titles, channel names and links come from YouTube. Two hardening rules
# (security pass 2026-10-15, before sharing with the team):
#  * text is stripped of control characters before it reaches the terminal or
#    fzf, so a crafted title cannot inject escape sequences;
#  * a link is used only if it matches a YouTube shape, and every external
#    command gets "--" before its links, so nothing can pass as an option
#    (yt-dlp --exec would run commands).
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
CHANNEL_URL = re.compile(r"https://(www\.|m\.)?youtube\.com/(@[\w.\-]+|channel/UC[\w-]{20,24}|c/[\w.\-]+|user/[\w.\-]+)/?", re.ASCII)
VIDEO_URL = re.compile(r"https://(www\.)?youtube\.com/(watch\?v=[\w-]{11}|shorts/[\w-]{11})", re.ASCII)


def clean(text):
    return CONTROL.sub("", str(text or ""))


def fg(hexcolor, text):
    r, g, b = (int(hexcolor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"


def header(line=""):
    """A quiet equalizer and a title: structure in the accent color, one orange mark."""
    eq = fg(C["selection"], "▁▂") + fg(C["accent"], "▃▅▆") + fg(C["selection"], "▄▂")
    print(f"\033[2J\033[H {eq} {fg(C['orange'], '♫')} {fg(C['light_foreground'], 'music')}"
          + (f"  {fg(C['muted'], line)}" if line else "") + "\n", flush=True)


def fzf(rows, prompt, header_text="", expect=""):
    """rows: [(key, display)]. Returns (pressed_key, key) or (None, None) if cancelled."""
    colors = (f"bg:{C['background']},fg:{C['foreground']},hl:{C['accent']},fg+:{C['light_foreground']},"
              f"bg+:{C['lighter_background']},hl+:{C['accent']},pointer:{C['orange']},prompt:{C['accent']},"
              f"info:{C['muted']},header:{C['muted']},border:{C['selection']},label:{C['accent']},"
              f"marker:{C['accent']},spinner:{C['accent']},gutter:{C['background']}")
    cmd = ["fzf", "--ansi", "--prompt", prompt, "--height", "100%", "--reverse", "--no-sort",
           "--delimiter", "\t", "--with-nth", "2..", "--color", colors, "--pointer", "▌",
           "--border", "rounded", "--border-label", " music ", "--info", "inline-right"]
    if header_text:
        cmd += ["--header", header_text]
    if expect:
        cmd += ["--expect", expect]
    out = subprocess.run(cmd, input="\n".join(f"{k}\t{d}" for k, d in rows),
                         stdout=subprocess.PIPE, text=True).stdout
    parts = out.rstrip("\n").split("\n")
    pressed, chosen = ((parts + ["", ""])[:2] if expect else ("", parts[0] if parts else ""))
    if not chosen:
        return None, None
    return pressed, chosen.split("\t", 1)[0]


def listing(url, limit=None):
    """[{title, duration, url, channel, channel_url}] from a channel or search URL."""
    # approximate_date: YouTube's "3 days ago" labels become a timestamp, so
    # rows can show a publish date without a slow full extraction per video.
    cmd = ["yt-dlp", "--flat-playlist", "--extractor-args", "youtubetab:approximate_date", "-J"]
    if limit:
        cmd += ["--playlist-end", str(limit)]
    cmd += ["--", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        return []
    if r.returncode != 0:
        return []
    out = []
    for e in json.loads(r.stdout).get("entries") or []:
        if e.get("url") and e.get("title") and VIDEO_URL.fullmatch(e["url"]):
            ts = e.get("timestamp") or e.get("release_timestamp")
            date = time.strftime("%y%m%d", time.gmtime(ts)) if ts else "      "
            out.append({"title": clean(e["title"]), "duration": e.get("duration") or 0, "url": e["url"], "date": date,
                        "channel": clean(e.get("channel") or e.get("uploader") or ""),
                        "channel_url": e.get("uploader_url") or e.get("channel_url") or "",
                        "channel_id_url": e.get("channel_url") or ""})
    return out


def fmt_len(seconds):
    seconds = int(seconds or 0)
    if seconds >= 3600:
        return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"
    return f"{seconds // 60}m" if seconds else "?"


def channels():
    if not CHANNELS.exists():
        return []
    lines = [line.strip() for line in CHANNELS.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    return [line for line in lines if CHANNEL_URL.fullmatch(line)]   # anything else is ignored


def follow_url(channel_url, name="", aliases=()):
    """Append a channel link; returns a one-line result. A channel has two link
    forms (@handle and channel/ID); any of them already listed counts as followed."""
    if not channel_url or not CHANNEL_URL.fullmatch(channel_url):
        return "No usable channel link found."
    name = clean(name)
    have = {c.rstrip("/").lower() for c in channels()}
    if any(u and u.rstrip("/").lower() in have for u in (channel_url, *aliases)):
        return f"Already following {name or channel_url}."
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    with CHANNELS.open("a") as f:
        f.write(channel_url.rstrip("/") + "\n")
    return f"Following {name or channel_url}"


def favorites():
    """[{date, title, url, channel}] from favorites.txt; malformed or non-YouTube lines are skipped."""
    out = []
    if FAVORITES.exists():
        for line in FAVORITES.read_text().splitlines():
            parts = line.split("\t")
            if line.startswith("#") or len(parts) < 3 or not VIDEO_URL.fullmatch(parts[2].strip()):
                continue
            out.append({"date": clean(parts[0])[:6], "title": clean(parts[1]), "url": parts[2].strip(),
                        "channel": clean(parts[3]) if len(parts) > 3 else "", "duration": 0})
    return out


def save_favorite(item):
    """Append a track to favorites.txt unless it is already there."""
    if not item or not VIDEO_URL.fullmatch(str(item.get("url", ""))):
        return "Nothing to save."
    if any(f["url"] == item["url"] for f in favorites()):
        return "Already a favorite."
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    new = not FAVORITES.exists()
    with FAVORITES.open("a") as f:
        if new:
            f.write("# Favorite tracks for the music pane: date<TAB>title<TAB>link<TAB>channel. Edit freely.\n")
        f.write("\t".join([clean(item.get("date", "")).strip(), clean(item.get("title", "")),
                           item["url"], clean(item.get("channel", ""))]) + "\n")
    return "★ saved to favorites"


def follow_video(video_url):
    """`f` in the player: look up the playing video's channel and follow it."""
    if not VIDEO_URL.fullmatch(str(video_url or "")):
        return "Not a YouTube video."
    r = subprocess.run(["yt-dlp", "--skip-download", "--print",
                        "%(uploader_url)s\t%(channel_url)s\t%(channel)s", "--", video_url],
                       capture_output=True, text=True, timeout=45)
    handle, chan_id, name = (r.stdout.strip().split("\t") + ["", "", ""])[:3]
    handle = "" if handle in ("NA", "None") else handle
    # Prefer the readable @handle form, but treat the ID form as the same channel.
    return follow_url(handle or chan_id, name, aliases=(chan_id,))


RETRY_SCRIPT = """-- Written by music_pane.py on every start; edit there.
-- YouTube refuses about 1 stream open in 4 at random, and a retry almost always
-- works (measured 2026-10-15). Retry a failed track up to 3 times, then let it
-- go. mpv runs with --idle=yes so a failure can't end the session before the
-- retry is queued; this script quits once the playlist is really finished.
-- The playlist loops (--loop-playlist=inf: after the last track, back to the
-- first), so a list where nothing will play could cycle forever; "failing"
-- counts errors since the last track that played, and stops that.
local tries, last_retry, failing = {}, -100, 0
mp.register_event("playback-restart", function() failing = 0 end)
-- On a failed load, jump back to the failed entry (it is still in the
-- playlist). Inserting a copy and removing the old one raced mpv's own advance
-- to the next track and removed the wrong entry (2026-10-15).
mp.register_event("end-file", function(ev)
  if ev.reason ~= "error" then return end
  local n = mp.get_property_number("playlist-count", 0)
  failing = failing + 1
  if failing > 4 * n + 2 then mp.command("quit") return end
  for i = 0, n - 1 do
    if mp.get_property_number("playlist/" .. i .. "/id") == ev.playlist_entry_id then
      local url = mp.get_property("playlist/" .. i .. "/filename")
      tries[url] = (tries[url] or 0) + 1
      if tries[url] <= 3 then
        -- Setting playlist-pos inside the event is ignored (mpv has already
        -- moved on); a short delay and an explicit play-index works.
        last_retry = mp.get_time()
        mp.add_timeout(0.3, function() mp.commandv("playlist-play-index", tostring(i)) end)
      end
      return
    end
  end
end)
-- Quit once the playlist is really over: idle, and no retry in the last 6 s.
-- Re-check every second while idle; a one-shot check could fire mid-retry and
-- then never run again (hung, 2026-10-15).
mp.add_periodic_timer(1, function()
  if mp.get_property_bool("idle-active") and mp.get_time() - last_retry > 6 then
    mp.command("quit")
  end
end)
"""


def pause_other_players():
    """Pause every MPRIS player (a YouTube tab, Spotify...) before mpv starts."""
    try:
        out = subprocess.run(["busctl", "--user", "--no-legend", "--timeout=2", "list"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):  # no systemd user bus (macOS, some distros): skip
        return
    for line in out.splitlines():
        name = line.split()[0] if line.split() else ""
        if name.startswith("org.mpris.MediaPlayer2.") and "mpv" not in name:
            try:
                subprocess.run(["busctl", "--user", "--timeout=2", "call", name, "/org/mpris/MediaPlayer2",
                                "org.mpris.MediaPlayer2.Player", "Pause"], capture_output=True, timeout=5)
            except subprocess.TimeoutExpired:
                pass   # a hung player shouldn't delay ours


WAVE_LAYERS = [  # (share of the teal, frequency, speed, amplitude): back to front
    (0.16, 1.1, 0.35, 0.80),
    (0.24, 1.7, -0.50, 0.62),
    (0.34, 2.3, 0.70, 0.46),
    (0.48, 3.1, -0.95, 0.30),
]
WAVE_SCALE = 2.2  # input gain into the tanh limiter; peaks ease to at most ~97.5% of the height (tuned 2026-10-15 at the 303px pane)
BRAILLE_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))  # [row][col]


def blend(hex_a, hex_b, t):
    """Mix two colors; t=0 gives a, t=1 gives b. Used to fake translucency on the background."""
    a = [int(hex_a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(hex_b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


class AudioBands:
    """Live band levels from mpv's own PipeWire stream, for the waves.

    Taps only mpv's stream (parec --monitor-stream on its sink-input), runs an
    FFT on ~93 ms windows about 20 times a second, and keeps four smoothed
    levels (bass, low-mid, high-mid, treble) plus overall loudness, each 0..1
    against a slowly decaying peak (auto-gain). Fast attack, slow release, so
    beats punch and quiet passages settle. If the tap fails, levels stay None
    and the waves fall back to plain breathing.
    """
    BANDS = ((30, 150), (150, 600), (600, 2500), (2500, 9000))
    RATE = 22050

    def __init__(self, stream_name):
        import threading
        self.stream_name = stream_name
        self.beat = 0.0      # 1.0 on a detected bass hit, decaying; drives the orange flashes
        self.levels = None
        self.loud = 0.0
        self.stop = False
        self.proc = None
        threading.Thread(target=self._run, daemon=True).start()

    def _sink_input(self):
        try:
            out = subprocess.run(["pactl", "-f", "json", "list", "sink-inputs"], capture_output=True, text=True,
                                 errors="replace").stdout
        except OSError:  # no PulseAudio/PipeWire tools: waves fall back to breathing
            self.stop = True
            return None
        try:
            for si in json.loads(out or "[]"):
                # mpv talks to PipeWire natively, so its stream has no process id;
                # it is started with a unique --audio-client-name instead.
                if si.get("properties", {}).get("application.name") == self.stream_name:
                    index = si.get("index")
                    return index if isinstance(index, int) else None
        except ValueError:
            pass
        return None

    def _run(self):
        import time as _t
        import numpy as np
        n = 2048
        window = np.hanning(n)
        freqs = np.fft.rfftfreq(n, 1 / self.RATE)
        masks = [(freqs >= lo) & (freqs < hi) for lo, hi in self.BANDS]
        peak = np.full(len(self.BANDS), 1e-6)
        loud_peak = 1e-6
        smooth = np.zeros(len(self.BANDS))
        buf = np.zeros(n)
        while not self.stop:
            idx = self._sink_input()
            if idx is None:
                _t.sleep(0.5)
                continue
            self.proc = subprocess.Popen(
                ["parec", f"--monitor-stream={idx}", "--format=s16le", f"--rate={self.RATE}",
                 "--channels=1", "--latency-msec=30", "--raw"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            hop = 1024
            while not self.stop:
                chunk = self.proc.stdout.read(hop * 2)
                if not chunk or len(chunk) < hop * 2:
                    break  # stream gone (track change, quit): find it again
                buf = np.roll(buf, -hop)
                buf[-hop:] = np.frombuffer(chunk, dtype="<i2") / 32768.0
                mag = np.abs(np.fft.rfft(buf * window))
                bands = np.array([mag[m].mean() if m.any() else 0.0 for m in masks])
                # Level = energy against this band's own running average (~2 s), so the
                # waves move with the music instead of sitting near a peak.
                avg = getattr(self, "_avg", bands.copy())
                self._avg = avg * 0.97 + bands * 0.03
                level = np.clip((bands / np.maximum(self._avg, 1e-9) - 0.4) / 1.6, 0, 1)
                rise = level > smooth
                smooth = np.where(rise, smooth + (level - smooth) * 0.65, smooth + (level - smooth) * 0.15)
                rms = float(np.sqrt((buf[-hop:] ** 2).mean()))
                loud_peak = max(loud_peak * 0.997, rms)
                self.loud = self.loud + (min(1.0, rms / loud_peak) - self.loud) * (0.5 if rms / loud_peak > self.loud else 0.1)
                # Beat: raw bass energy well above its short average (~0.5 s), with a
                # cooldown, so kicks and drops flash and steady bass does not.
                fast = getattr(self, "_bass_fast", bands[0])
                self._bass_fast = fast * 0.9 + bands[0] * 0.1
                cooldown = getattr(self, "_cool", 0)
                if bands[0] > fast * 1.3 and bands[0] > self._avg[0] and cooldown <= 0:
                    self.beat, self._cool = 1.0, 10       # at most ~2 flashes a second
                else:
                    self.beat *= 0.82                      # ~0.3 s fade
                    self._cool = cooldown - 1
                self.levels = smooth.tolist()
            if self.proc.poll() is None:
                self.proc.terminate()
            self.levels = None

    def close(self):
        self.stop = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def waves(w, h, t, levels=None, loud=0.0, beat=0.0):
    """Breathing translucent wave lines as braille text rows.

    Each layer is a sine with a slow envelope; the whole field breathes on a
    6 s cycle. Line segments are joined vertically so the waves read as lines,
    not dots. Front layers are a little more opaque than back ones.
    """
    import math
    X, Y = w * 2, h * 4
    if X < 4 or Y < 8:
        return []
    cells = [[0] * w for _ in range(h)]
    layer_of = [[-1] * w for _ in range(h)]
    if levels:
        # Music-driven: each layer follows its band (bass at the back, treble in
        # front), and the whole field swells with overall loudness.
        breath = 0.45 + 0.65 * loud
        gains = [0.18 + 0.95 * lv for lv in levels]
    else:
        breath = 0.72 + 0.28 * math.sin(2 * math.pi * t / 6.0)
        gains = [1.0] * len(WAVE_LAYERS)
    mid = (Y - 1) / 2
    front = len(WAVE_LAYERS) - 1
    glint_x = (t * 9) % (X + 40) - 20          # breathing mode: one drifting glint
    orange = [[False] * w for _ in range(h)]
    for k, (_, freq, speed, amp) in enumerate(WAVE_LAYERS):
        amp = min(1.0, amp * gains[k])
        prev = None
        for x in range(X):
            env = 0.65 + 0.35 * math.sin(x / X * math.pi * 1.3 + t * 0.21 + k)
            # Soft limiter instead of clipping (the operator, 2026-10-15: "I'd prefer no clipping at
            # all"). tanh passes small and medium swings almost unchanged and eases big ones
            # toward the edge without ever reaching it, so peaks round off instead of flattening.
            # WAVE_SCALE sets how full the canvas gets before the easing takes over.
            swing = WAVE_SCALE * amp * breath * env * math.sin(x / X * 2 * math.pi * freq + t * speed + k * 1.7)
            y = mid + (mid - 0.5) * math.tanh(swing)
            yi = max(0, min(Y - 1, int(round(y))))   # safety only; tanh keeps |y - mid| < mid - 0.5
            span = range(min(prev, yi), max(prev, yi) + 1) if prev is not None else [yi]
            for yy in span:
                if 0 <= yy < Y:
                    r, c = yy // 4, x // 2
                    cells[r][c] |= BRAILLE_BITS[yy % 4][x % 2]
                    layer_of[r][c] = max(layer_of[r][c], k)
            # Orange stays a thin mark (brand rule): only crest cells of the
            # front-most two layers, on a beat (music mode) or under the glint.
            if k >= front - 1 and 0 <= yi < Y:
                crest = math.cos(x / X * 2 * math.pi * freq + t * speed + k * 1.7) ** 2 < 0.04
                if levels and beat > 0.25 and crest:
                    orange[yi // 4][x // 2] = True
                elif not levels and k == front and abs(x - glint_x) < 2:
                    orange[yi // 4][x // 2] = True
            prev = yi
    # A layer brightens a little with its band, never past half-opaque teal.
    colors = [ansi_fg(blend(C["background"], C["accent"],
                            min(0.6, share * (0.75 + 0.6 * (levels[k] if levels else 0.4)))))
              for k, (share, *_) in enumerate(WAVE_LAYERS)]
    hot = ansi_fg(blend(C["background"], C["orange"], 0.55 + 0.45 * (beat if levels else 0.6)))
    rows = []
    for r in range(h):
        line, cur = [], None
        for c in range(w):
            if cells[r][c]:
                col = hot if orange[r][c] else colors[layer_of[r][c]]
                if col != cur:
                    line.append(col)
                    cur = col
                line.append(chr(0x2800 + cells[r][c]))
            else:
                line.append(" ")
        rows.append("".join(line) + "\033[0m")
    return rows


def ansi_fg(hexcolor):
    r, g, b = (int(hexcolor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return f"\033[38;2;{r};{g};{b}m"


class Mpv:
    """Minimal JSON IPC client for one mpv instance."""

    def __init__(self, path):
        import socket
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(path))
        self.sock.settimeout(1.0)
        self.buf = b""
        self.next_id = 0

    def request(self, *cmds):
        """Send several commands at once; return their data in order (None on error)."""
        ids = []
        for cmd in cmds:
            self.next_id += 1
            ids.append(self.next_id)
            self.sock.sendall(json.dumps({"command": list(cmd), "request_id": self.next_id}).encode() + b"\n")
        got = {}
        while len(got) < len(ids):
            while b"\n" not in self.buf:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise ConnectionError("mpv closed")
                self.buf += chunk
            line, self.buf = self.buf.split(b"\n", 1)
            msg = json.loads(line or b"{}")
            if msg.get("request_id") in ids:
                got[msg["request_id"]] = msg.get("data") if msg.get("error") == "success" else None
        return [got[i] for i in ids]


def fmt_clock(seconds):
    if seconds is None:
        return "--:--"
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def wrap(text, width, lines):
    out, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + (1 if cur else 0) > width:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1][: max(0, width - 1)] + "…"
    return out


def play(items, start=0, label="", show_channel=True):
    """Run mpv headless and draw the whole pane ourselves: header, track, status, waves, keys.
    The header carries the track's channel (unless label already names it) and its date."""
    import os, select, shutil, termios, threading, time, tty
    CONF_DIR.mkdir(parents=True, exist_ok=True)   # first run on a fresh machine
    pause_other_players()
    RETRY_LUA.write_text(RETRY_SCRIPT)
    # mpv's IPC accepts a `run` command, so the socket must be private: the
    # per-user runtime dir (mode 0700), or a fresh private temp dir if unset.
    import tempfile
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    own_dir = not (runtime and Path(runtime).is_dir())
    sock_dir = Path(tempfile.mkdtemp(prefix="music-pane-")) if own_dir else Path(runtime)
    sock = sock_dir / f"music-pane-{os.getpid()}.sock"
    sock.unlink(missing_ok=True)
    # Retries: YouTube intermittently refuses a stream (3 in 12 in a burst; 0 in 10 spaced out).
    # Do not add --stream-lavf-o=reconnect...: it stalled playback entirely (2026-10-15).
    stream_name = f"music-pane-{os.getpid()}"
    proc = subprocess.Popen(["mpv", "--no-video", "--no-terminal", f"--ytdl-format={AUDIO}",
                             f"--audio-client-name={stream_name}",
                             "--ytdl-raw-options=retries=5", f"--input-ipc-server={sock}",
                             f"--script={RETRY_LUA}", "--idle=yes", "--loop-playlist=inf", f"--playlist-start={start}",
                             "--", *[it["url"] for it in items if VIDEO_URL.fullmatch(it["url"])]])
    for _ in range(100):
        if sock.exists():
            break
        time.sleep(0.05)
    try:
        mpv = Mpv(sock)
    except OSError:
        proc.terminate()
        return
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    note = {"text": "", "until": 0.0}
    keys = {" ": ("cycle", "pause"), "\x1b[A": ("add", "volume", "5"), "\x1b[B": ("add", "volume", "-5"),
            "\x1b[C": ("seek", "10"), "\x1b[D": ("seek", "-10"), "]": ("seek", "60"), "[": ("seek", "-60"),
            "n": ("playlist-next",), "p": ("playlist-prev",), ">": ("playlist-next",),
            "<": ("playlist-prev",), "m": ("cycle", "mute")}
    def handle_keys(pressed):
        """Apply key presses; returns True when the user asked to go back."""
        for key in pressed:
            if key in ("q", "Q", "\x1b"):
                mpv.request(("quit",))
                return True
            if key == "s":
                pos = mpv.request(("get_property", "playlist-pos"))[0]
                item = items[pos] if isinstance(pos, int) and 0 <= pos < len(items) else None
                note.update(text=save_favorite(item), until=time.time() + 3)
            elif key == "v":
                visual["mode"] = "breathe" if visual["mode"] == "music" else "music"
                note.update(text=f"visual: {visual['mode']}", until=time.time() + 2)
            elif key == "f":
                path = mpv.request(("get_property", "path"))[0]
                note.update(text="following…", until=time.time() + 30)

                def do_follow(p=path):
                    note.update(text=follow_video(p) if p else "nothing playing", until=time.time() + 4)
                threading.Thread(target=do_follow, daemon=True).start()
            elif key in keys:
                mpv.request(keys[key])
        return False

    t0 = time.time()
    try:
        audio = AudioBands(stream_name)
    except Exception:
        audio = None
    debug = os.environ.get("MUSIC_PANE_DEBUG")
    fav_cache = {}
    visual = {"mode": "music"}   # v toggles: "music" (follows the audio) / "breathe" (calm, no audio)
    sys.stdout.write("\033[?25l")
    try:
        while proc.poll() is None:
            ready, _, _ = select.select([fd], [], [], 1 / 15)
            pressed = []
            if ready:
                # One read can hold several keys (fast typing, held arrows): split into
                # escape sequences and single characters.
                raw = os.read(fd, 64).decode(errors="ignore")
                i = 0
                while i < len(raw):
                    if raw.startswith("\x1b[", i) and i + 2 < len(raw):
                        pressed.append(raw[i:i + 3])
                        i += 3
                    else:
                        pressed.append(raw[i])
                        i += 1
            quit_now = False
            try:
                quit_now = handle_keys(pressed)
            except (ConnectionError, OSError, ValueError):
                break   # mpv went away or stopped answering: back to the picker
            if quit_now:
                break
            try:
                title, paused, pos, dur, vol, mute, idx, count, idle = mpv.request(
                    ("get_property", "media-title"), ("get_property", "pause"), ("get_property", "time-pos"),
                    ("get_property", "duration"), ("get_property", "volume"), ("get_property", "mute"),
                    ("get_property", "playlist-pos-1"), ("get_property", "playlist-count"),
                    ("get_property", "idle-active"))
            except (ConnectionError, OSError, ValueError):
                break
            if int(time.time() - t0) % 2 == 0:
                refresh_palette()       # a theme switch recolors the pane within ~2 s
            cols, rows = shutil.get_terminal_size((64, 22))
            width = max(20, cols - 2)
            eq = fg(C["selection"], "▁▂") + fg(C["accent"], "▃▅▆") + fg(C["selection"], "▄▂")
            cur = items[idx - 1] if isinstance(idx, int) and 0 < idx <= len(items) else {}
            parts = [label] + ([cur.get("channel", "")] if show_channel else []) + [cur.get("date", "").strip()]
            where = " | ".join(p for p in parts if p)
            out = [f" {eq} {fg(C['orange'], '♫')} {fg(C['light_foreground'], 'music')}  {fg(C['muted'], where[:cols - 22])}", ""]
            title_lines = wrap(clean(title) or "loading…", width - 2, 2)
            out.append(f" {fg(C['orange'], '♫')} {fg(C['light_foreground'], title_lines[0])}")
            out += [f"   {fg(C['light_foreground'], t)}" for t in title_lines[1:]]
            playing = not paused and not idle and pos is not None
            state = "playing" if playing else ("loading" if pos is None and not paused else "paused")
            vol_txt = f"{int(vol or 0)}" + (" muted" if mute else "")
            fav_urls = fav_cache.get("urls", set())
            if time.time() - fav_cache.get("at", 0) > 2:
                fav_urls = {f["url"] for f in favorites()}
                fav_cache.update(urls=fav_urls, at=time.time())
            star = fg(C["orange"], " ★") if cur.get("url") in fav_urls else ""
            out.append(f" {fg(C['accent'], state)}  {fg(C['light_foreground'], fmt_clock(pos))}"
                       f"{fg(C['muted'], ' / ' + fmt_clock(dur))}  {fg(C['muted'], 'vol')} {fg(C['accent'], vol_txt)}"
                       f"  {fg(C['muted'], f'{idx or 0}/{count or 0}')}{star}")
            hints = "space ⏯  ↑↓ vol  ←→ seek  [ ] 1 min  n/p next/prev  m mute  v visual  s save  f follow  q back"
            if time.time() < note["until"]:
                footer = [clean(note["text"])]
            elif len(hints) <= cols - 2:
                footer = [hints]
            else:
                footer = ["space ⏯  ↑↓ vol  ←→ seek  [ ] 1 min  v visual", "n/p next/prev  m mute  s save  f follow  q back"]
            canvas_h = rows - len(out) - len(footer)      # waves get every free row
            levels = audio.levels if audio and visual["mode"] == "music" else None
            if debug and levels:
                with open(debug, "a") as dbg:
                    dbg.write(f"{time.time() - t0:.2f} {' '.join(f'{v:.2f}' for v in levels)} {audio.loud:.2f} beat={audio.beat:.2f}\n")
            canvas = (waves(width, canvas_h, time.time() - t0, levels, audio.loud if audio else 0.0,
                            audio.beat if audio else 0.0)
                      if playing and canvas_h >= 3 else [""] * max(canvas_h, 0))
            frame = out + [" " + line for line in canvas] + [" " + fg(C["muted"], f[:cols - 2]) for f in footer]
            sys.stdout.write("\033[H" + "".join(line + "\033[K\r\n" for line in frame[:-1]) + frame[-1] + "\033[K\033[J")
            sys.stdout.flush()
    finally:
        if audio:
            audio.close()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\033[?25h\033[0m")
        sys.stdout.flush()
        if proc.poll() is None:
            proc.terminate()
        sock.unlink(missing_ok=True)
        if own_dir:
            try:
                sock_dir.rmdir()
            except OSError:
                pass


def pull_channel(url, depth):
    return listing(f"{url.rstrip('/')}/videos", depth)


def pick_and_play():
    refresh_palette()
    header()
    names = {c.rstrip("/").rsplit("/", 1)[-1]: c for c in channels()}
    rows = [("search", fg(C["accent"], "⌕") + "  search YouTube"),
            ("shuffle-all", fg(C["accent"], "⤨") + "  shuffle all channels")]
    if favorites():
        rows.append(("favorites", fg(C["orange"], "★") + "  favorites"))
    rows += [(n, fg(C["selection"], "♪") + "  " + n) for n in names]
    hint = "enter open · esc quit" if names else "no channels yet: search, then ctrl-a (or f while playing) to follow one"
    _, choice = fzf(rows, "› ", header_text=hint)
    if choice is None:
        return False

    if choice == "shuffle-all":
        header("gathering…")
        with ThreadPoolExecutor(max_workers=6) as pool:
            items = [it for chunk in pool.map(lambda u: pull_channel(u, SHUFFLE_DEPTH), names.values())
                     for it in chunk]
        random.shuffle(items)
        if items:
            play(items, 0, "shuffle · all channels")
        return True

    if choice == "favorites":
        items = favorites()
        if not items:
            return True
        rows = [("shuffle", fg(C["accent"], "⤨") + "  shuffle favorites")]
        rows += [(str(i), f"{fg(C['muted'], it['date'])}  {it['title']}  {fg(C['muted'], it['channel'])}")
                 for i, it in enumerate(items)]
        _, key = fzf(rows, "› ", header_text="enter play · esc back")
        if key is None:
            return True
        if key == "shuffle":
            random.shuffle(items)
            play(items, 0, "shuffle · favorites")
        else:
            play(items, int(key), "favorites")
        return True

    is_search = choice == "search"
    if is_search:
        query = input(fg(C["accent"], " search › ")).strip()
        if not query:
            return True
        items = listing(f"ytsearch{SEARCH_HITS}:{query}")
        hint, label = "enter play · ctrl-a follow channel · esc back", f"search · {query}"
    else:
        items = pull_channel(names[choice], LATEST)
        hint, label = "enter play · esc back", choice
    if not items:
        print(fg(C["muted"], " Nothing found."))
        return True

    rows = [] if is_search else [("shuffle", fg(C["accent"], "⤨") + "  shuffle this channel")]
    for i, it in enumerate(items):
        chan = f"  {fg(C['muted'], it['channel'])}" if is_search and it["channel"] else ""
        rows.append((str(i), f"{fg(C['muted'], it.get('date', ''))}  {fg(C['muted'], f'{fmt_len(it['duration']):>6}')}  {it['title']}{chan}"))
    while True:
        pressed, key = fzf(rows, "› ", header_text=hint, expect="ctrl-a" if is_search else "")
        if key is None:
            return True
        if key == "shuffle":
            more = pull_channel(names[choice], SHUFFLE_DEPTH)
            random.shuffle(more)
            play(more, 0, f"shuffle · {choice}", show_channel=False)
            return True
        if pressed == "ctrl-a":
            it = items[int(key)]
            print(fg(C["accent"], " " + follow_url(it["channel_url"], it["channel"],
                                                   aliases=(it.get("channel_id_url"),))), flush=True)
            continue
        play(items, int(key), label, show_channel=is_search)
        return True


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--follow":
        print(follow_video(sys.argv[2]))
        return 0
    print("\033]2;music\007", end="", flush=True)  # window title, so a window manager can find the pane
    while pick_and_play():
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
