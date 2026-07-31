"""Digest composer — renders passes + auditable reject list, grouped by source.

Output is Markdown-ish plain text (gws gmail sends it as the body). The reject
list with one-line reasons is the trust-building feature: the filter is visible,
not a black box.
"""
from __future__ import annotations

import html as _html
from collections import defaultdict

from .record import Item, Verdict

_SOURCE_LABEL = {"youtube": "YouTube", "blog": "Blogs", "medium": "Medium", "x": "X / Twitter"}


def _group(scored: list[tuple[Item, Verdict]]):
    by_src = defaultdict(list)
    for item, v in scored:
        by_src[item.source].append((item, v))
    return by_src


def _split_interest(scored, interest_map):
    """(for_you, non_interest_scored). ``for_you`` items are pulled out entirely so
    they surface ONLY in their own section (never double-listed under passes/rejects)."""
    interest_map = interest_map or {}
    for_you = [(i, v) for i, v in scored if i.uid in interest_map]
    rest = [(i, v) for i, v in scored if i.uid not in interest_map]
    return for_you, rest


def compose(scored: list[tuple[Item, Verdict]], date_label: str,
            skipped: list[dict] | None = None,
            interest_map: dict[str, str] | None = None,
            deep: dict[str, dict] | None = None) -> tuple[str, str]:
    """Return (subject, body). ``skipped`` = title-only downselect drops (audit).
    ``interest_map`` = {uid: matched_topic} for personal-interest ★ For you items.
    ``deep`` = {uid: {learnings, why_novel}} deep-dive briefings for chosen items."""
    skipped = skipped or []
    interest_map = interest_map or {}
    deep = deep or {}
    for_you, rest = _split_interest(scored, interest_map)
    passes = [(i, v) for i, v in rest if v.passed]
    rejects = [(i, v) for i, v in rest if not v.passed]
    subject = f"AI Digest — {date_label} — {len(passes)} pass / {len(scored)} evaluated"
    if for_you:
        subject += f" · ★{len(for_you)} for you"

    lines = [f"# AI Content Digest — {date_label}", ""]
    lines.append(f"Evaluated **{len(scored)}** items · **{len(passes)}** passed · "
                 f"**{len(for_you)}** for you · **{len(rejects)}** rejected · "
                 f"**{len(skipped)}** skipped on title.")
    lines.append("")

    def _bullets(entries, summary_of):
        out = []
        for item, v in sorted(entries, key=lambda iv: -iv[1].score):
            summ = _clip_words(summary_of(v), 65)
            out.append(f"- **[{item.title}]({item.url})** · {item.producer} · "
                       f"{v.score}/10 — {summ}")
        return out

    # ★ For you — personal-interest matches, surfaced regardless of novelty score.
    if for_you:
        lines.append("## ★ For you (matches your interests)")
        lines += _bullets(for_you, lambda v: v.summary or v.reason)
        lines.append("")

    lines.append("## ✅ Worth your time")
    if passes:
        lines += _bullets(passes, lambda v: v.summary or v.reason)
    else:
        lines.append("_No items cleared the novelty threshold this poll._")

    lines.append("\n## 🗂️ Rejected (transcript-scored, below bar)")
    if rejects:
        lines += _bullets(rejects, lambda v: v.reason or v.summary)
    else:
        lines.append("_Nothing rejected._")

    if skipped:
        lines.append("\n## ⏭️ Skipped on title (not fetched)")
        for c in skipped[:30]:
            lines.append(f"- [{c.get('title','')}]({c.get('url','')}) · {c.get('producer','')}")
        if len(skipped) > 30:
            lines.append(f"- …and {len(skipped) - 30} more")

    # 📖 Deep dive — the learnings, so the chosen ones don't need watching.
    chosen = sorted(for_you + passes, key=lambda iv: -iv[1].score)
    chosen = [(i, v) for i, v in chosen if deep.get(i.uid)]
    if chosen:
        lines.append("\n---\n\n## 📖 The learnings (skip the video)")
        for item, v in chosen:
            d = deep[item.uid]
            star = "★ " if item.uid in interest_map else ""
            lines.append(f"\n### {star}[{item.title}]({item.url}) · {item.producer} · {v.score}/10")
            if d.get("learnings"):
                lines.append("\n**What you'll learn**")
                lines += [f"- {b}" for b in d["learnings"]]
            if d.get("why_novel"):
                lines.append("\n**Why it's novel**")
                lines += [f"- {b}" for b in d["why_novel"]]

    return subject, "\n".join(lines)


# --- HTML rendering (email body) -------------------------------------------
# Inline styles only — email clients strip <head><style>. Keep it simple/robust.
def _esc(s) -> str:
    return _html.escape(str(s or ""))


def _badge(score: int) -> str:
    # green when it passed the bar, muted grey when it didn't
    bg, fg = ("#e6f4ea", "#137333") if score >= 8 else ("#eef0f2", "#5f6368")
    return (f'<span style="background:{bg};color:{fg};border-radius:10px;'
            f'padding:1px 7px;font-size:12px;font-weight:600;white-space:nowrap;">{score}/10</span>')


def _short_url(url: str) -> str:
    """Compact, human-readable form of a URL. youtu.be/<id> for YouTube watch links."""
    import re
    import urllib.parse as up
    m = re.search(r"[?&]v=([\w-]{6,})", url or "")
    if m:
        return f"youtu.be/{m.group(1)}"
    try:
        p = up.urlparse(url)
        s = (p.netloc + p.path).lstrip("/").rstrip("/")
        s = re.sub(r"^www\.", "", s)
        return s[:40] + ("…" if len(s) > 40 else "")
    except Exception:
        return url or ""


def _clip_words(text: str, n: int = 50) -> str:
    words = str(text or "").split()
    return " ".join(words) if len(words) <= n else " ".join(words[:n]).rstrip(".,;") + "…"


# shared table column styling (inline; table-layout:fixed => predictable wrap)
_TH = ('style="text-align:left;padding:6px 8px;border-bottom:2px solid #d9dce0;'
       'font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:#70757a;font-weight:700;"')
_TD = 'style="padding:8px;vertical-align:top;border-bottom:1px solid #eef0f2;word-break:break-word;"'


def _rows(entries, summary_of) -> str:
    out = []
    for item, v in sorted(entries, key=lambda iv: -iv[1].score):
        out.append("<tr>")
        out.append(f'<td {_TD}><a href="{_esc(item.url)}" style="color:#1a56db;text-decoration:none;'
                   f'font-weight:600;">{_esc(item.title)}</a></td>')
        out.append(f'<td {_TD}style="padding:8px;vertical-align:top;border-bottom:1px solid #eef0f2;'
                   f'color:#3c4043;">{_esc(item.producer)}</td>')
        out.append(f'<td style="padding:8px;vertical-align:top;border-bottom:1px solid #eef0f2;'
                   f'text-align:center;">{_badge(v.score)}</td>')
        out.append(f'<td {_TD}style="padding:8px;vertical-align:top;border-bottom:1px solid #eef0f2;'
                   f'color:#3c4043;">{_esc(_clip_words(summary_of(v), 65))}</td>')
        out.append("</tr>")
    return "\n".join(out)


def _table(entries, summary_of) -> str:
    head = (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px;margin:0 0 8px;">'
        '<colgroup>'
        '<col style="width:32%"><col style="width:13%"><col style="width:7%"><col style="width:48%">'
        '</colgroup>'
        f'<thead><tr><th {_TH}>Title</th><th {_TH}>Source</th>'
        f'<th {_TH}style="text-align:center;padding:6px 8px;border-bottom:2px solid #d9dce0;'
        f'font-size:11px;text-transform:uppercase;color:#70757a;font-weight:700;">Score</th>'
        f'<th {_TH}>Summary</th></tr></thead><tbody>'
    )
    return head + _rows(entries, summary_of) + "</tbody></table>"
def _deep_dive_html(chosen, interest_map, deep) -> str:
    """Bulleted 'skip the video' learnings for each chosen item — the bottom section."""
    out = ['<h2 style="font-size:14px;text-transform:uppercase;letter-spacing:.04em;'
           'color:#1a1a1a;margin:30px 0 4px;border-top:2px solid #d9dce0;padding-top:20px;">'
           '📖 The learnings · skip the video</h2>']
    for item, v in chosen:
        d = deep.get(item.uid) or {}
        if not d:
            continue
        star = ("<span style=\"color:#8a5a00;\">★ </span>" if item.uid in interest_map else "")
        out.append('<div style="margin:16px 0 4px;">')
        out.append(f'{star}<a href="{_esc(item.url)}" style="color:#1a56db;text-decoration:none;'
                   f'font-weight:700;font-size:14px;">{_esc(item.title)}</a>'
                   f'<span style="color:#70757a;font-size:12px;"> · {_esc(item.producer)} · {v.score}/10</span>')
        if d.get("learnings"):
            out.append('<div style="font-size:12px;font-weight:700;color:#137333;margin:8px 0 2px;">'
                       'WHAT YOU\'LL LEARN</div>')
            out.append('<ul style="margin:0 0 6px;padding-left:18px;font-size:13px;color:#1a1a1a;line-height:1.5;">')
            out += [f'<li style="margin:3px 0;">{_esc(b)}</li>' for b in d["learnings"]]
            out.append('</ul>')
        if d.get("why_novel"):
            out.append('<div style="font-size:12px;font-weight:700;color:#8a5a00;margin:6px 0 2px;">'
                       'WHY IT\'S NOVEL</div>')
            out.append('<ul style="margin:0 0 6px;padding-left:18px;font-size:13px;color:#3c4043;line-height:1.5;">')
            out += [f'<li style="margin:3px 0;">{_esc(b)}</li>' for b in d["why_novel"]]
            out.append('</ul>')
        out.append('</div>')
    return "\n".join(out)


def _brief_hero_html(brief_links: dict) -> str:
    """The hero at the top of the email: 'read this and you're caught up' links to
    the synthesized briefing Docs (one per style). Empty string if no links."""
    if not brief_links:
        return ""
    label = {"verbose": "Full briefing", "dense": "Dense briefing"}
    order = [s for s in ("dense", "verbose") if s in brief_links] + \
            [s for s in brief_links if s not in ("dense", "verbose")]
    btns = []
    for s in order:
        btns.append(
            f'<a href="{_esc(brief_links[s])}" style="display:inline-block;margin:0 8px 6px 0;'
            f'padding:9px 16px;background:#1a56db;color:#fff;text-decoration:none;border-radius:8px;'
            f'font-size:14px;font-weight:600;">📄 {_esc(label.get(s, s.title()))}</a>')
    return (
        '<div style="border:1px solid #d9dce0;border-radius:10px;padding:14px 16px;margin:0 0 20px;'
        'background:#f7f9fc;">'
        '<div style="font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:3px;">'
        '📚 This week\'s briefing — read this, skip the videos</div>'
        '<div style="font-size:12.5px;color:#5f6368;margin-bottom:10px;">'
        'One synthesized article of everything worth knowing from the picks below.</div>'
        + "".join(btns) + '</div>')


def compose_html(scored: list[tuple[Item, Verdict]], date_label: str,
                 skipped: list[dict] | None = None,
                 interest_map: dict[str, str] | None = None,
                 deep: dict[str, dict] | None = None,
                 brief_links: dict[str, str] | None = None) -> str:
    skipped = skipped or []
    interest_map = interest_map or {}
    deep = deep or {}
    brief_links = brief_links or {}
    for_you, rest = _split_interest(scored, interest_map)
    passes = [(i, v) for i, v in rest if v.passed]
    rejects = [(i, v) for i, v in rest if not v.passed]
    P = []
    P.append('<div style="max-width:920px;margin:0 auto;padding:8px 4px;'
             'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
             'color:#1a1a1a;line-height:1.45;">')
    P.append('<h1 style="font-size:20px;margin:0 0 2px;">AI Content Digest</h1>')
    P.append(f'<div style="color:#70757a;font-size:13px;margin-bottom:18px;">{_esc(date_label)} '
             f'&nbsp;·&nbsp; <b>{len(passes)}</b> passed / {len(scored)} evaluated'
             f'{f" · ★{len(for_you)} for you" if for_you else ""}'
             f'{f" · {len(skipped)} skipped on title" if skipped else ""}</div>')

    # 📚 Hero — the synthesized briefing links, above everything else.
    P.append(_brief_hero_html(brief_links))

    # ★ For you — personal-interest matches, surfaced regardless of novelty score.
    if for_you:
        P.append('<h2 style="font-size:14px;text-transform:uppercase;letter-spacing:.04em;'
                 'color:#8a5a00;margin:0 0 8px;">★ For you · matches your interests</h2>')
        P.append(_table(for_you, lambda v: v.summary or v.reason))

    # Worth your time — summary = content summary (fallback to reason for old data)
    P.append('<h2 style="font-size:14px;text-transform:uppercase;letter-spacing:.04em;'
             'color:#137333;margin:0 0 8px;">Worth your time</h2>')
    if passes:
        P.append(_table(passes, lambda v: v.summary or v.reason))
    else:
        P.append('<p style="color:#70757a;font-style:italic;font-size:13px;">'
                 'No items cleared the novelty threshold this poll.</p>')

    # Rejected — transcript-scored but below the bar; summary = why cut
    P.append('<h2 style="font-size:14px;text-transform:uppercase;letter-spacing:.04em;'
             'color:#70757a;margin:26px 0 8px;">Rejected · transcript-scored, below bar</h2>')
    if rejects:
        P.append(_table(rejects, lambda v: v.reason or v.summary))
    else:
        P.append('<p style="color:#70757a;font-style:italic;font-size:13px;">Nothing rejected.</p>')

    # Skipped on title — downselected before any transcript fetch (audit trail)
    if skipped:
        P.append('<h2 style="font-size:14px;text-transform:uppercase;letter-spacing:.04em;'
                 'color:#9aa0a6;margin:26px 0 8px;">Skipped on title · not fetched</h2>')
        P.append('<ul style="margin:0;padding-left:18px;font-size:12.5px;color:#5f6368;">')
        for c in skipped[:30]:
            P.append(f'<li style="margin:2px 0;"><a href="{_esc(c.get("url",""))}" '
                     f'style="color:#5f6368;">{_esc(c.get("title",""))}</a> '
                     f'— {_esc(c.get("producer",""))}</li>')
        P.append('</ul>')
        if len(skipped) > 30:
            P.append(f'<div style="font-size:12px;color:#9aa0a6;margin-top:4px;">'
                     f'…and {len(skipped) - 30} more</div>')

    # 📖 Deep dive — the learnings, so the chosen ones don't need watching.
    chosen = sorted(for_you + passes, key=lambda iv: -iv[1].score)
    if any(deep.get(i.uid) for i, _ in chosen):
        P.append(_deep_dive_html(chosen, interest_map, deep))

    P.append('</div>')
    return "\n".join(P)


# ── `digest learn` — per-video learnings email ──────────────────────────────
def _md_to_html(md: str) -> str:
    """Minimal, email-safe Markdown → HTML (bullets, bold, headings, paragraphs).
    Inline styles only — no <style> block (clients strip it)."""
    import re
    out, in_ul = [], False
    def _inline(s):
        s = _esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)
        return s
    for raw in (md or "").splitlines():
        ln = raw.rstrip()
        if re.match(r"^\s*[-*]\s+", ln):
            if not in_ul:
                out.append('<ul style="margin:6px 0;padding-left:20px;">'); in_ul = True
            body = _inline(re.sub(r"^\s*[-*]\s+", "", ln))
            out.append(f'<li style="margin:3px 0;">{body}</li>')
            continue
        if in_ul:
            out.append("</ul>"); in_ul = False
        m = re.match(r"^(#{1,4})\s+(.*)", ln)
        if m:
            out.append(f'<div style="font-weight:700;font-size:14px;margin:12px 0 4px;">{_inline(m.group(2))}</div>')
        elif ln.strip():
            out.append(f'<p style="margin:8px 0;">{_inline(ln)}</p>')
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


def _fmt_duration(seconds) -> str:
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return ""
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m}m" if h else f"{m}m"


def compose_learn_html(item, headline: str, summary_md: str,
                       duration=None, playlist: str = "") -> str:
    dur = _fmt_duration(duration)
    meta = " · ".join(x for x in [_esc(item.producer), dur, _esc(playlist)] if x)
    return "\n".join([
        '<div style="max-width:640px;margin:0 auto;padding:8px 4px;'
        'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'color:#1a1a1a;line-height:1.5;">',
        f'<div style="font-size:12px;color:#70757a;text-transform:uppercase;letter-spacing:.05em;">📝 Video learnings</div>',
        f'<h1 style="font-size:19px;margin:2px 0 2px;"><a href="{_esc(item.url)}" '
        f'style="color:#1a56db;text-decoration:none;">{_esc(item.title)}</a></h1>',
        f'<div style="color:#70757a;font-size:12px;margin-bottom:4px;">{meta}</div>' if meta else "",
        f'<div style="font-size:14px;font-style:italic;color:#3c4043;margin:6px 0 12px;">{_esc(headline)}</div>' if headline else "",
        f'<div style="font-size:14px;">{_md_to_html(summary_md)}</div>',
        f'<div style="margin-top:16px;font-size:12px;color:#70757a;">▶ <a href="{_esc(item.url)}" '
        f'style="color:#70757a;">Watch on YouTube</a></div>',
        '</div>',
    ])
