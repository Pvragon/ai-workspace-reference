"""Compose the rapid primer — a hard-capped, scannable brief over ranked concepts.

DESIGN NOTES (why this is not ``brief.py``)
------------------------------------------
``brief.synthesize`` asked the LLM for the ENTIRE briefing inside a single JSON
string field, built from ~41k tokens of raw transcripts, with no output-token
limit and a 90s timeout. It failed silently for three consecutive polls. Two
lessons are baked in here:

  1. **The model returns STRUCTURE, not a document.** Headlines and dives come
     back as fields we render ourselves. So the word cap is enforced in CODE
     (``_enforce_budget``) instead of merely requested in the prompt — a prompt
     asking for "under 1000 words" is a wish, not a limit.
  2. **The prompt is small.** It sees pre-extracted concept statements, never
     raw transcripts, so the input is a few thousand tokens regardless of how
     many videos were polled.

Lanes are rendered separately and labelled, because "12 creators agree" and "one
sharp creator said it first" are different claims about the world and collapsing
them into one ranked list destroys the distinction.
"""
from __future__ import annotations

from typing import Optional

from .concepts import LANE_CONVERGING, LANE_EARLY
from .gemini import generate_json, GeminiError

class PrimerError(RuntimeError):
    """Primer synthesis failed. Deliberately fatal to the primer step: the
    primer IS the deliverable, so it must never fail quietly the way
    brief.synthesize did."""


_SCHEMA = {
    "type": "object",
    "properties": {
        "headlines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["key", "text"],
            },
        },
        "dives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "what": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["key", "title", "what", "why"],
            },
        },
    },
    "required": ["headlines", "dives"],
}

_PROMPT = """\
You are writing a rapid primer for ONE busy practitioner who will not watch any
of these videos. Total reading time must be under five minutes, so every word
competes for space.

You get pre-extracted, pre-ranked CONCEPTS with trend metadata. Do not summarize
videos. Write about IDEAS.

Produce two things:

1. `headlines` — one line per concept, for the concepts marked HEADLINE. Each is
   a single declarative sentence, max 18 words, stating WHAT IS NOW TRUE. Lead
   with the substance, not the framing. Include the concrete specifics (tool,
   model id, number) when one exists. No "creators are discussing", no
   "this week saw". Give the `key` you were given, verbatim.

2. `dives` — for the concepts marked DIVE only. Each has:
   - `title`: 3-8 words naming the idea
   - `what`: 2-3 sentences, max 55 words. The mechanism, concretely. What it IS
     and how it works. Specifics over adjectives.
   - `why`: 1-2 sentences, max 35 words, on why it changes what this person
     should DO. If it does not change anything, say so plainly rather than
     inventing significance.

Hard rules:
- Never inflate. If a concept is thin, its line should read as thin.
- Do not editorialize about consensus. The metadata already reports how many
  sources carried each idea; do not restate counts in your prose.
- Preserve concrete details (names, numbers, model ids) over smooth phrasing.
- Use the `key` values exactly as given so the output can be matched back.
"""


def _fmt_cluster(cl: dict, role: str) -> str:
    stmts = []
    for m in cl.get("concepts", [])[:4]:
        s = (m.get("statement") or "").strip()
        if s:
            stmts.append(f"    - ({m.get('producer','?')}) {s}")
    spec = sorted({s for m in cl.get("concepts", [])
                   for s in (m.get("specifics") or [])})[:8]
    bits = [
        f"[{role}] key={cl['key']} | lane={cl.get('lane')} | "
        f"sources={cl.get('n_sources')} | new={cl.get('is_new')} | "
        f"impact={cl.get('impact')}",
        f"    label: {cl.get('label')}",
    ]
    if spec:
        bits.append(f"    specifics: {', '.join(spec)}")
    bits.extend(stmts)
    return "\n".join(bits)


def _word_count(*parts: str) -> int:
    return sum(len((p or "").split()) for p in parts)


def _enforce_budget(headlines: list[dict], dives: list[dict],
                    max_words: int) -> tuple[list[dict], list[dict], bool]:
    """Trim to the word budget, dropping the LOWEST-ranked dives first.

    Called after generation because the model cannot be trusted to hold a word
    limit. Headlines are preserved as long as possible — the 30-second scan is
    the part that must survive; the dives are the expendable tail.
    """
    trimmed = False
    hl_words = sum(_word_count(h.get("text", "")) for h in headlines)
    while dives:
        total = hl_words + sum(
            _word_count(d.get("title", ""), d.get("what", ""), d.get("why", ""))
            for d in dives)
        if total <= max_words:
            break
        dives = dives[:-1]
        trimmed = True
    # Still over budget on headlines alone -> drop the tail of the scan list.
    while headlines and (sum(_word_count(h.get("text", "")) for h in headlines)
                         + sum(_word_count(d.get("title", ""), d.get("what", ""),
                                           d.get("why", "")) for d in dives)
                         ) > max_words:
        headlines = headlines[:-1]
        trimmed = True
    return headlines, dives, trimmed


def compose(ranked: list[dict], *, model: str, api_key: str, date_label: str,
            n_headlines: int = 8, n_dives: int = 4,
            max_words: int = 1000, max_rest: int = 12) -> Optional[dict]:
    """Return {"headlines","dives","rest","trimmed","words"} or None on failure.

    ``rest`` is everything past the headline cut — rendered as bare links, which
    is how the primer stays short without silently discarding coverage.
    """
    if not ranked:
        return None
    head = ranked[:n_headlines]
    dive_keys = {c["key"] for c in ranked[:n_dives]}
    rest = ranked[n_headlines:n_headlines + max_rest]

    blocks = [_fmt_cluster(c, "DIVE" if c["key"] in dive_keys else "HEADLINE")
              for c in head]
    prompt = (f"{_PROMPT}\nPrimer date: {date_label}.\n"
              f"Return STRICT JSON: {{\"headlines\":[{{\"key\",\"text\"}}],"
              f"\"dives\":[{{\"key\",\"title\",\"what\",\"why\"}}]}}\n\n"
              f"=== CONCEPTS ===\n" + "\n\n".join(blocks) + "\n")
    try:
        obj = generate_json(prompt, model=model, api_key=api_key,
                            max_output_tokens=8192, thinking_budget=0)
    except GeminiError as e:
        # Surfaced, not swallowed: the primer IS the deliverable, so a failure
        # here must be loud. brief.py's silent `return ""` hid three dead polls.
        raise PrimerError(str(e)) from e

    by_key = {c["key"]: c for c in ranked}
    headlines = [h for h in (obj.get("headlines") or [])
                 if h.get("key") in by_key and (h.get("text") or "").strip()]
    dives = [d for d in (obj.get("dives") or [])
             if d.get("key") in by_key and (d.get("what") or "").strip()]
    # Keep the model's output in OUR ranked order, not whatever order it emitted.
    order = {c["key"]: i for i, c in enumerate(ranked)}
    headlines.sort(key=lambda h: order.get(h["key"], 999))
    dives.sort(key=lambda d: order.get(d["key"], 999))
    if not headlines and not dives:
        raise PrimerError("model returned no usable headlines or dives")

    headlines, dives, trimmed = _enforce_budget(headlines, dives, max_words)
    words = (sum(_word_count(h.get("text", "")) for h in headlines)
             + sum(_word_count(d.get("title", ""), d.get("what", ""),
                               d.get("why", "")) for d in dives))
    return {"headlines": headlines, "dives": dives, "rest": rest,
            "trimmed": trimmed, "words": words, "by_key": by_key,
            "n_dropped": max(0, len(ranked) - n_headlines - len(rest))}


# --- rendering --------------------------------------------------------------

def _sources(cl: dict, limit: int = 4) -> list[dict]:
    """One entry per distinct video, in order — the raw member list repeats the
    same video once per concept it contributed."""
    seen, out = set(), []
    for m in cl.get("concepts", []):
        k = m.get("uid") or m.get("url")
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
        if len(out) >= limit:
            break
    return out


def _tag(cl: dict) -> str:
    """Short provenance tag. States HOW we know, so a lone-source call is never
    mistaken for a confirmed trend."""
    def _who():
        # the producer the lane is actually based on, not the alphabetical first
        return (cl.get("top_producer")
                or (cl["producers"][0] if cl.get("producers") else "?"))
    n = cl.get("n_sources", 1)
    if cl.get("lane") == LANE_CONVERGING:
        t = f"{n} sources"
    elif cl.get("lane") == LANE_EARLY:
        t = f"EARLY · {_who()}"
        if n > 1:                       # never hide a corroborating source
            t += f" +{n - 1}"
    else:
        t = _who()
        if n > 1:
            t += f" +{n - 1}"
    if cl.get("is_new"):
        t += " · NEW"
    elif cl.get("velocity", 0) >= 2:
        t += f" · ▲{cl['velocity']:g}x"
    return t


def render_markdown(p: dict, *, date_label: str) -> str:
    by_key = p["by_key"]
    L = [f"# AI Primer — {date_label}", ""]
    read_min = max(1, round(p["words"] / 220))
    L.append(f"*{p['words']} words · ~{read_min} min*")
    L.append("")
    L.append("## What changed")
    L.append("")
    for h in p["headlines"]:
        cl = by_key[h["key"]]
        L.append(f"- {h['text'].strip()}  `{_tag(cl)}`")
    L.append("")
    if p["dives"]:
        L.append("## The ones that matter")
        L.append("")
        for d in p["dives"]:
            cl = by_key[d["key"]]
            L.append(f"### {d['title'].strip()}  `{_tag(cl)}`")
            L.append("")
            L.append(d["what"].strip())
            L.append("")
            L.append(f"**Why it matters:** {d['why'].strip()}")
            L.append("")
            src = " · ".join(
                f"[{m['producer']}]({m['url']})" for m in _sources(cl))
            if src:
                L.append(f"▸ {src}")
                L.append("")
    if p["rest"]:
        L.append("## Everything else")
        L.append("")
        for cl in p["rest"]:
            links = " · ".join(
                f"[{m['producer']}]({m['url']})" for m in _sources(cl, 3))
            L.append(f"- {cl['label']} — {links}")
        L.append("")
    # Never truncate silently: a capped list that does not say it was capped
    # reads as "this was everything".
    if p.get("n_dropped"):
        L.append(f"*+{p['n_dropped']} lower-ranked ideas not shown "
                 f"(raise `n_headlines`/`max_rest` in [primer] to see them).*")
        L.append("")
    return "\n".join(L)


def render_html(p: dict, *, date_label: str) -> str:
    by_key = p["by_key"]
    read_min = max(1, round(p["words"] / 220))
    F = ("-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,"
         "sans-serif")
    o = [f'<div style="max-width:660px;margin:0 auto;padding:8px 4px;'
         f'font-family:{F};color:#1a1a1a;line-height:1.5;">',
         f'<div style="font-size:12px;color:#70757a;text-transform:uppercase;'
         f'letter-spacing:.05em;">⚡ AI Primer · {date_label}</div>',
         f'<div style="font-size:12px;color:#70757a;margin-bottom:14px;">'
         f'{p["words"]} words · ~{read_min} min read</div>',
         '<h2 style="font-size:15px;margin:18px 0 8px;">What changed</h2>',
         '<ul style="font-size:14px;padding-left:18px;margin:0;">']
    for h in p["headlines"]:
        cl = by_key[h["key"]]
        o.append(f'<li style="margin-bottom:7px;">{_esc(h["text"].strip())} '
                 f'<span style="color:#70757a;font-size:11px;white-space:nowrap;">'
                 f'{_esc(_tag(cl))}</span></li>')
    o.append("</ul>")
    if p["dives"]:
        o.append('<h2 style="font-size:15px;margin:22px 0 8px;">'
                 'The ones that matter</h2>')
        for d in p["dives"]:
            cl = by_key[d["key"]]
            o.append(f'<div style="margin-bottom:16px;">'
                     f'<div style="font-size:14px;font-weight:600;">'
                     f'{_esc(d["title"].strip())} '
                     f'<span style="color:#70757a;font-size:11px;font-weight:400;">'
                     f'{_esc(_tag(cl))}</span></div>'
                     f'<div style="font-size:14px;margin:3px 0;">'
                     f'{_esc(d["what"].strip())}</div>'
                     f'<div style="font-size:13px;color:#3c4043;">'
                     f'<b>Why it matters:</b> {_esc(d["why"].strip())}</div>')
            src = " · ".join(
                f'<a href="{_esc(m["url"])}" style="color:#70757a;">'
                f'{_esc(m["producer"])}</a>' for m in _sources(cl))
            if src:
                o.append(f'<div style="font-size:11px;color:#70757a;'
                         f'margin-top:3px;">▸ {src}</div>')
            o.append("</div>")
    if p["rest"]:
        o.append('<h2 style="font-size:15px;margin:22px 0 8px;">Everything else'
                 '</h2><ul style="font-size:13px;padding-left:18px;margin:0;'
                 'color:#3c4043;">')
        for cl in p["rest"]:
            links = " · ".join(
                f'<a href="{_esc(m["url"])}" style="color:#70757a;">'
                f'{_esc(m["producer"])}</a>' for m in _sources(cl, 3))
            o.append(f'<li style="margin-bottom:4px;">{_esc(cl["label"])} — '
                     f'{links}</li>')
        o.append("</ul>")
    if p.get("n_dropped"):
        o.append(f'<div style="font-size:11px;color:#70757a;margin-top:10px;">'
                 f'+{p["n_dropped"]} lower-ranked ideas not shown</div>')
    o.append("</div>")
    return "\n".join(o)


def _esc(s) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))
