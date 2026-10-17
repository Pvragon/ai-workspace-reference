"""Synthesize a single cross-video "briefing" from a poll's chosen transcripts.

The per-video ``deepen()`` learnings answer "what's in THIS video." The brief
answers "what do I need to know THIS WEEK" — one theme-organized article woven
from every chosen transcript, so the reader learns the material without watching
anything. One style: ``dense`` — maximum learning-per-word, theme-grouped,
minimal prose, every concrete specific preserved, plus a cross-cutting-patterns
pass. (The ``verbose`` prose style was retired 2026-07-29.)

SUPERSEDED BY ``primer.py`` for the "what do I need to know" job: the primer works
at the IDEA level across videos, enforces a hard word cap in code, and cannot hit
the prompt-size failure this module did. This path remains because `poll` emails
it; it is now hardened against that failure and reports errors instead of
returning "" in silence.

Returns Markdown. Fails soft to "" on LLM error (caller just omits the brief).
"""
from __future__ import annotations

from .record import Item
from .gemini import generate_json, GeminiError


_COMMON = """\
You are writing a briefing for a working AI engineer (the operator) so he can learn
everything worthwhile from this week's videos WITHOUT watching them. You are given
the full transcripts of the chosen videos. Synthesize ACROSS them — organize by
THEME, not by video. Deduplicate points that recur; when several videos hit the
same idea, say so once and note it's a recurring signal. Teach the actual
substance: name the tools, techniques, numbers, APIs, and steps. No hype, no
filler, no "in this video." Ground claims in what the transcripts actually say.

SOURCE LINKS (required): each video's exact url is given below. Immediately UNDER
every section heading — before that section's content — put a line linking the
source video(s) that section draws from, as Markdown links:
  Source: [<exact video title>](<exact url>)
and when a section synthesizes several videos, list each:
  Sources: [Title A](urlA) · [Title B](urlB)
Use the exact url provided for each video. Put the relevant link(s) under EACH
heading (not only in a list at the end) so every section is grounded in its source
and one click away.
"""

# 2026-07-29: the "verbose" prose style was retired — dense (maximum
# learning-per-word) is the only style. Any stale config still asking for
# "verbose" resolves to dense rather than erroring.

_DENSE = """\
STYLE: maximum learning-per-word. Theme sections (H2). Under each, tight bullets
packed with concrete specifics (tool names, numbers, APIs, exact techniques) —
minimal connective prose. Preserve EVERY concrete, learnable detail; do not smooth
them away. Add a final "Cross-cutting patterns" section naming the ideas that
recurred across multiple videos. Target 1000-1600 words, denser than prose.
"""

_SCHEMA = {
    "type": "object",
    "properties": {"markdown": {"type": "string"}},
    "required": ["markdown"],
}


def _sources_block(items: list[Item], deep: dict) -> str:
    out = []
    for it in items:
        d = (deep or {}).get(it.uid) or {}
        learn = "; ".join(d.get("learnings", [])[:8])
        text = (it.text or "")[:16000]
        out.append(
            f"### {it.producer}: {it.title}\nurl: {it.url}\n"
            f"key learnings (pre-extracted): {learn}\n"
            f"transcript:\n{text}\n"
        )
    return "\n".join(out)


def synthesize(items: list[Item], *, style: str, model: str, api_key: str,
               date_label: str, deep: dict | None = None, log=None,
               max_items: int = 8) -> str:
    """Return a Markdown briefing for the chosen ``items``. Fails soft to ''.

    NOTE: ``digest primer`` supersedes this — it works at the IDEA level, holds a
    hard word cap, and cannot hit the failure below. This path is kept because
    `poll` still emails it, and is now hardened the same way:

      * thinking_budget=0 + an explicit output cap. 2.5-flash thinking draws down
        the OUTPUT budget, so an uncapped long generation returned truncated text
        -> JSONDecodeError. That is what killed this function silently for three
        consecutive polls.
      * transcript payload bounded by ``max_items``. Failures here tracked item
        count exactly: 8 chosen items succeeded, 10-12 failed, because the prompt
        grew to ~41k tokens against a 90s read timeout.
      * the error REASON is reported via ``log`` instead of vanishing.
    """
    items = [it for it in items if it is not None and (it.text or "")]
    if not items:
        return ""
    if len(items) > max_items:
        if log:
            log(f"  brief: {len(items)} items over the {max_items} cap — "
                f"synthesizing the top {max_items} (prompt-size guard)")
        items = items[:max_items]
    style_block = _DENSE          # dense is the only supported style
    prompt = (
        _COMMON + "\n" + style_block +
        f"\nWrite the briefing for: {date_label}. Start with a single H1 title. "
        f"Return STRICT JSON: {{\"markdown\": \"<the full briefing in markdown>\"}}.\n\n"
        f"=== CHOSEN VIDEOS (full transcripts) ===\n" + _sources_block(items, deep or {})
    )
    try:
        obj = generate_json(prompt, model=model, api_key=api_key,
                            max_output_tokens=16384, thinking_budget=0,
                            timeout=180)
    except GeminiError as e:
        if log:
            log(f"  brief: synthesis FAILED — {e}")
        return ""
    md = obj.get("markdown", "")
    return md if isinstance(md, str) else ""
