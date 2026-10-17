---
template: app-readme
version: 2.5.1
summary: "Audio-only terminal music player for a tiling desktop: plays followed YouTube channels or a search through mpv with no video, with shuffle, favorites, audio-reactive waves and live Omarchy theme colors. README covers install per distro, keys and platform support."
created: 2026-10-15
last_updated: 2026-10-16
maintainer: pvragon
---

# music pane

A small terminal music player built for a corner of a tiling desktop. You pick a YouTube channel you
follow, or search, and it plays the audio only. Under the track it draws slow, translucent wave lines
that move with the music.

It plays audio with no video, so it stays light: about 1% of a CPU core for the pane and 1% for
playback. A YouTube tab playing the same mix uses around 17% of a core and a gigabyte of memory.

## What you get

- Keep a short list of YouTube channels. Each one shows its latest uploads with
  their publish dates.
- Search YouTube from the pane. Press Ctrl+A on a result, or `f` while it plays, to add
  its channel to your list.
- Shuffle one channel, or everything you follow.
- Four layers of wave lines track the bass, mids and highs, and
  the whole field swells with the volume. Strong bass hits flash the front crests orange. Press `v`
  for a calmer breathing mode that ignores the audio.
- On Omarchy the pane uses the current theme and recolors itself within a
  couple of seconds when you switch themes. Elsewhere it uses neutral colors.

## Install

You need Python 3.11 or newer, plus `mpv`, `yt-dlp`, `fzf` and `numpy`.

| Distro | Command |
|---|---|
| Arch, Omarchy | `sudo pacman -S mpv yt-dlp fzf python-numpy` |
| Debian, Ubuntu | `sudo apt install mpv fzf python3-numpy pipx && pipx install yt-dlp` |
| Fedora | enable RPM Fusion, then `sudo dnf install mpv yt-dlp fzf python3-numpy` |
| macOS | `brew install mpv yt-dlp fzf && pip3 install numpy` |

Debian and Ubuntu ship an old `yt-dlp`, and YouTube breaks old versions often, so install it with
`pipx`. Fedora probably needs RPM Fusion for `mpv` and for the audio codecs YouTube uses; that has not
been checked. Only the Arch
command has been tested so far.

Then run it:

```
python3 ~/ai-workspace/team-lib/apps/music-pane/music_pane.py
```

On a tiling window manager, give it its own small terminal window. It looks best around 60 by 20
characters or larger.

## Keys

| Key | In the player |
|---|---|
| space | play or pause |
| ↑ ↓ | volume |
| ← → | seek 10 seconds |
| [ ] | seek 1 minute |
| n p | next or previous track |
| m | mute |
| v | switch visuals: music or breathing |
| f | follow the playing track's channel |
| s | save the track to favorites |
| q | back to the picker |

In the picker, type to filter, use the arrow keys to move, Enter to choose and Esc to go back. In
search results, Ctrl+A follows the result's channel.

Your channel list is a plain text file at `~/.config/music-pane/channels.txt`, one channel link per
line. You can edit it by hand. To start one, copy `channels.example.txt` from this folder there.
Saved tracks go to `~/.config/music-pane/favorites.txt` and show up as "★ favorites" in the picker.

## Platform support

| Platform | Status |
|---|---|
| Omarchy | Everything, including live theme colors. |
| Other Linux with PipeWire or PulseAudio | Everything, with neutral colors. |
| Linux without PipeWire or PulseAudio | Plays fine. The waves breathe instead of following the music. |
| macOS | Should work, untested. The waves breathe instead of following the music. |
| Windows | Not supported. |

## How it works

`mpv` plays the audio in the background with video turned off, and `yt-dlp` fetches listings and
streams. The pane controls `mpv` over a private local socket and draws the whole screen itself about
15 times a second. The waves are braille characters, so each terminal cell holds a 2 by 4 grid of
dots.

To follow the music, the pane listens to its own audio stream only, never other apps. It splits the
sound into four frequency bands about 20 times a second, and each band drives one wave layer.

YouTube refuses about one stream request in four at random, and asking again almost always works. So
the pane retries a refused track up to three times before skipping it.

## Security

Video titles, channel names and links come from YouTube, so the pane treats them as untrusted. It
strips control characters from text before showing it. It only accepts links that look like real
YouTube channel or video links, and it passes them to other programs in a way that can't be read as
a command option. The control socket lives in a private directory that only you can open.

## A note on YouTube

This streams YouTube through `yt-dlp`, as tools like `ytfzf` do. It works, but YouTube's terms of
service don't permit it.

## License

MIT. See [LICENSE](LICENSE).
