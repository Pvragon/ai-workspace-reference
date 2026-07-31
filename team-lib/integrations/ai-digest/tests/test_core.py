"""Offline unit tests — no network. Mocks the Gemini and adapter boundaries."""
import os
from pathlib import Path

import pytest

from ai_digest.record import Item, Verdict
from ai_digest.corpus import Corpus
from ai_digest import digest as digestmod
from ai_digest import score as scoremod


# --- config / init ----------------------------------------------------------
def test_init_seeds_channels(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path / "cfg"))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    p = cfg.init()
    assert p.exists()
    conf = cfg.load()
    chans = conf["youtube"]["channels"]
    assert len(chans) == len(cfg.SEED_CHANNELS)
    assert any(c["name"] == "OpenAI" for c in chans)
    assert conf["scoring"]["threshold"] == 8
    assert conf["digest"]["recipient"] == "you@example.com"


# --- corpus -----------------------------------------------------------------
def _item(uid, title="t", producer="P"):
    return Item(uid=uid, source="youtube", producer=producer, title=title,
                url=f"https://y/{uid}", text="body")


def test_corpus_dedupe_and_context(tmp_path):
    c = Corpus(tmp_path / "corpus.db")
    a, b = _item("youtube:a"), _item("youtube:b", title="B vid")
    assert c.filter_new([a, b]) == [a, b]
    assert not c.seen("youtube:a")

    c.record(a, Verdict(8, True, "novel thing", key_points=["k1"]), "2026-06-29T10:00:00", digested=True)
    c.record(b, Verdict(3, False, "rehash", key_points=[]), "2026-06-29T10:00:00", digested=False)

    assert c.seen("youtube:a")
    # b is seen too (recorded even though rejected) -> not re-fetched next poll
    assert c.filter_new([a, b]) == []

    ctx = c.recent_context(10)
    titles = [r["title"] for r in ctx]
    assert "t" in titles and "B vid" not in titles  # only digested passes feed context
    s = c.stats()
    assert s["total"] == 2 and s["passed"] == 1


# --- digest compose ---------------------------------------------------------
def test_digest_groups_and_counts():
    scored = [
        (_item("youtube:1", "Big release"), Verdict(9, True, "new product", summary="Ships a new agent API", key_points=["does X"])),
        (_item("youtube:2", "Hype reaction"), Verdict(2, False, "no substance", key_points=[])),
    ]
    subject, body = digestmod.compose(scored, "Mon 2026-06-29")
    assert "1 pass / 2 evaluated" in subject
    assert "Worth your time" in body
    assert "Big release" in body and "Ships a new agent API" in body   # summary shown
    assert "https://y/youtube:1" in body                                # link present
    assert "Rejected" in body
    assert "Hype reaction" in body and "no substance" in body           # reject reason
    assert "https://y/youtube:2" in body                                # rejects have links too
    assert "### YouTube" not in body                                     # no per-source subheader


def test_digest_html_renders_and_escapes():
    scored = [
        (_item("youtube:1", "Big <release> & stuff"), Verdict(9, True, "new product", summary="A big new release", key_points=["does X"])),
        (_item("youtube:2", "Hype reaction"), Verdict(2, False, "no substance", key_points=[])),
    ]
    html = digestmod.compose_html(scored, "Mon 2026-06-29")
    assert html.startswith("<div") and html.endswith("</div>")
    assert "<table" in html and "<th " in html           # rendered as tables
    assert 'href="https://y/youtube:1"' in html          # pass linked
    assert 'href="https://y/youtube:2"' in html          # REJECT linked too
    assert "youtu.be/youtube:2" not in html              # short-url only for real v= links
    assert "Big &lt;release&gt; &amp; stuff" in html     # escaped, not raw
    assert "9/10" in html and "Worth your time" in html
    assert "Rejected" in html and "Hype reaction" in html
    assert "YouTube" not in html                          # no per-source subheader now
    assert "<script" not in html.lower()


def test_digest_empty_passes():
    scored = [(_item("youtube:1"), Verdict(1, False, "meh", key_points=[]))]
    subject, body = digestmod.compose(scored, "Mon 2026-06-29")
    assert "0 pass" in subject
    assert "No items cleared" in body


# --- scoring (mock gemini) --------------------------------------------------
def test_score_threshold_split(monkeypatch):
    payloads = iter([
        {"score": 8, "reason": "novel pattern", "key_points": ["a", "b"],
         "dimensions": {"novelty": 9}},
        {"score": 4, "reason": "rehash", "key_points": [], "dimensions": {}},
    ])
    monkeypatch.setattr(scoremod, "generate_json", lambda *a, **k: next(payloads))
    items = [_item("youtube:1"), _item("youtube:2")]
    v1 = scoremod.score_item(items[0], items, [], model="m", api_key="k",
                             threshold=7, transcript_max_chars=1000)
    v2 = scoremod.score_item(items[1], items, [], model="m", api_key="k",
                             threshold=7, transcript_max_chars=1000)
    assert v1.passed and v1.score == 8 and v1.key_points == ["a", "b"]
    assert not v2.passed and v2.score == 4


def test_score_clamps_and_survives_bad_json(monkeypatch):
    monkeypatch.setattr(scoremod, "generate_json", lambda *a, **k: {"score": 99})
    v = scoremod.score_item(_item("youtube:1"), [], [], model="m", api_key="k",
                            threshold=7, transcript_max_chars=10)
    assert v.score == 10  # clamped

    def boom(*a, **k):
        from ai_digest.gemini import GeminiError
        raise GeminiError("429")
    monkeypatch.setattr(scoremod, "generate_json", boom)
    v = scoremod.score_item(_item("youtube:2"), [], [], model="m", api_key="k",
                            threshold=7, transcript_max_chars=10)
    assert not v.passed and v.error and "429" in v.reason


# --- recency: corpus run tracking + cutoff filter ----------------------------
def test_corpus_last_run_roundtrip(tmp_path):
    c = Corpus(tmp_path / "corpus.db")
    assert c.get_last_run("youtube") is None
    c.set_last_run("youtube", "2026-06-30T12:00:00+00:00")
    assert c.get_last_run("youtube") == "2026-06-30T12:00:00+00:00"
    c.set_last_run("youtube", "2026-06-30T18:00:00+00:00")  # replace
    assert c.get_last_run("youtube") == "2026-06-30T18:00:00+00:00"


def test_list_candidates_scans_all_and_filters_seen(monkeypatch):
    """Stage 1: titles only, all channels, unseen filter — NO transcript calls."""
    from ai_digest import youtube as yt
    monkeypatch.setattr(yt, "list_recent",
                        lambda h, n: [{"id": h + "1", "title": "t1", "url": "u1"},
                                      {"id": h + "2", "title": "t2", "url": "u2"}])
    # transcript/date must NEVER be called in stage 1
    monkeypatch.setattr(yt, "fetch_transcript", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no transcripts in scan")))
    seen = {"youtube:@a2"}
    cands, warns = yt.list_candidates(
        [{"name": "A", "handle": "@a"}, {"name": "B", "handle": "@b"}],
        is_seen=lambda uid: uid in seen, scan_per_channel=5, channel_delay_sec=0)
    uids = {c["uid"] for c in cands}
    assert uids == {"youtube:@a1", "youtube:@b1", "youtube:@b2"}   # @a2 filtered as seen


def test_collect_metadata_recency_and_description(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from ai_digest import youtube as yt
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    cands = [{"uid": f"youtube:v{i}", "id": f"v{i}", "title": f"t{i}", "producer": "P", "url": f"u{i}"}
             for i in range(3)]
    meta = {"v0": (now - timedelta(hours=2), "fresh desc"),
            "v1": (now - timedelta(hours=40), "old desc"),   # too old
            "v2": (None, "no date desc")}
    monkeypatch.setattr(yt, "fetch_metadata", lambda vid: meta[vid])
    results, warns = yt.collect_metadata(cands, cutoff_ts=now - timedelta(hours=24), request_delay_sec=0)
    by = {r["cand"]["id"]: r for r in results}
    assert by["v0"]["status"] == "ok" and by["v0"]["description"] == "fresh desc"
    assert by["v1"]["status"] == "old"                       # recency-skipped, no transcript
    assert by["v2"]["status"] == "ok"                        # unknown date -> fail open


def test_fetch_transcripts_and_block(monkeypatch):
    from ai_digest import youtube as yt
    kept = [{"cand": {"uid": f"youtube:v{i}", "id": f"v{i}", "title": "t", "producer": "P", "url": "u"},
             "description": "d", "published": ""} for i in range(3)]
    # first ok, then a block -> aborts, third never attempted
    seq = iter(["transcript-0"])
    def fake(vid, **kw):
        if vid == "v0":
            return "transcript-0"
        raise yt.TranscriptBlocked("IpBlocked")
    monkeypatch.setattr(yt, "fetch_transcript", fake)
    results, warns, blocked = yt.fetch_transcripts(kept, transcript_max_chars=999, min_interval_sec=0)
    oks = [r for r in results if r["status"] == "ok"]
    assert len(oks) == 1 and oks[0]["item"].description == "d"
    assert blocked and any("ABORTED" in w for w in warns)


def test_refine_by_description(monkeypatch):
    from ai_digest import score as sc
    survivors = [{"cand": {"uid": f"u{i}", "producer": "P", "title": f"t{i}"}, "description": f"d{i}"}
                 for i in range(4)]
    monkeypatch.setattr(sc, "generate_json", lambda *a, **k: {"keep": [2, 0]})
    kept, dropped = sc.refine_by_description(survivors, model="m", api_key="k")
    assert [s["cand"]["uid"] for s in kept] == ["u2", "u0"]
    assert {s["cand"]["uid"] for s in dropped} == {"u1", "u3"}


def test_transcripts_hourly_window(tmp_path):
    from datetime import datetime, timezone, timedelta
    c = Corpus(tmp_path / "corpus.db")
    t0 = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    c.log_transcripts(10, t0.isoformat())
    c.log_transcripts(5, (t0 + timedelta(minutes=90)).isoformat())   # 1.5h later
    at = (t0 + timedelta(minutes=90)).isoformat()
    assert c.transcripts_in_window(at, 1) == 5        # only the recent 5 in the last hour
    assert c.transcripts_in_window(at, 24) == 15       # all 15 in the last day


def test_prefilter_relevance_ranked_no_budget(monkeypatch):
    """Relevance gate returns ALL relevant (ranked), not budget-limited."""
    from ai_digest import score as sc
    cands = [{"uid": f"u{i}", "producer": "P", "title": f"t{i}"} for i in range(5)]
    monkeypatch.setattr(sc, "generate_json", lambda *a, **k: {"keep": [3, 0, 3, 99, 4]})  # dupes/oob ignored
    relevant, irrelevant = sc.prefilter(cands, model="m", api_key="k")
    assert [c["uid"] for c in relevant] == ["u3", "u0", "u4"]     # ranked, no cap
    assert {c["uid"] for c in irrelevant} == {"u1", "u2"}


def test_prefilter_propagates_llm_error(monkeypatch):
    """On LLM rate-limit the prefilter must RAISE (caller defers) — not fail open."""
    import pytest as _pytest
    from ai_digest import score as sc
    from ai_digest.gemini import GeminiError
    cands = [{"uid": f"u{i}", "producer": "P", "title": f"t{i}"} for i in range(5)]
    def boom(*a, **k):
        raise GeminiError("429")
    monkeypatch.setattr(sc, "generate_json", boom)
    with _pytest.raises(GeminiError):
        sc.prefilter(cands, model="m", api_key="k")


def test_daily_transcript_limiter(tmp_path):
    from datetime import datetime, timezone, timedelta
    c = Corpus(tmp_path / "corpus.db")
    t0 = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    assert c.transcripts_last_24h(t0.isoformat()) == 0
    c.log_transcripts(5, t0.isoformat())
    assert c.transcripts_last_24h(t0.isoformat()) == 5
    c.log_transcripts(3, (t0 + timedelta(hours=1)).isoformat())
    assert c.transcripts_last_24h((t0 + timedelta(hours=1)).isoformat()) == 8
    # 25h later the first batch has aged out of the rolling window
    later = (t0 + timedelta(hours=25)).isoformat()
    assert c.transcripts_last_24h(later) == 3


def test_cooldown_state_roundtrip(tmp_path):
    c = Corpus(tmp_path / "corpus.db")
    assert c.get_state("cooldown_until") is None
    c.set_state("cooldown_until", "2026-07-01T00:00:00+00:00")
    assert c.get_state("cooldown_until") == "2026-07-01T00:00:00+00:00"
    c.set_state("cooldown_until", None)        # clear
    assert c.get_state("cooldown_until") is None


def test_build_session_from_cookies(tmp_path):
    from ai_digest import youtube as yt
    assert yt.build_session(None) is None
    assert yt.build_session(str(tmp_path / "nope.txt")) is None
    cookies = tmp_path / "cookies.txt"
    cookies.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t9999999999\tLOGIN_INFO\tabc123\n")
    s = yt.build_session(str(cookies))
    assert s is not None
    assert any(ck.name == "LOGIN_INFO" for ck in s.cookies)


def test_classify_interests_maps_uid_to_topic(monkeypatch):
    from ai_digest import score as sc
    cands = [{"uid": f"u{i}", "producer": "P", "title": f"t{i}"} for i in range(4)]
    topics = ["make money with agentic video", "agentic micro-products", "new agent patterns"]
    # index 0 -> topic 1, index 3 -> topic 3; others no match
    monkeypatch.setattr(sc, "generate_json", lambda *a, **k: {"matches": {"0": 1, "3": 3}})
    m = sc.classify_interests(cands, topics, model="m", api_key="k")
    assert m == {"u0": topics[0], "u3": topics[2]}


def test_classify_interests_empty_when_no_topics(monkeypatch):
    from ai_digest import score as sc
    calls = []
    monkeypatch.setattr(sc, "generate_json", lambda *a, **k: calls.append(1) or {"matches": {}})
    cands = [{"uid": "u0", "producer": "P", "title": "t0"}]
    assert sc.classify_interests(cands, [], model="m", api_key="k") == {}
    assert calls == []                                  # no LLM call when topics empty


def test_classify_interests_fails_closed_on_llm_error(monkeypatch):
    from ai_digest import score as sc
    from ai_digest.gemini import GeminiError
    def boom(*a, **k):
        raise GeminiError("429")
    monkeypatch.setattr(sc, "generate_json", boom)
    cands = [{"uid": "u0", "producer": "P", "title": "t0"}]
    # additive signal must NOT raise — returns empty so the poll continues
    assert sc.classify_interests(cands, ["topic"], model="m", api_key="k") == {}


def test_forget_removes_matching_seen(tmp_path):
    c = Corpus(tmp_path / "corpus.db")
    c.record(_item("youtube:a", "Make videos with Claude Code", "IndyDevDan"),
             Verdict(2, False, "off-topic"), "2026-07-07T10:00:00", digested=False)
    c.record(_item("youtube:b", "Random news", "Other"),
             Verdict(3, False, "meh"), "2026-07-07T10:00:00", digested=False)
    removed = c.forget("claude code")
    assert [r["uid"] for r in removed] == ["youtube:a"]
    assert not c.seen("youtube:a") and c.seen("youtube:b")   # only the match forgotten
    # keyword also matches producer
    assert [r["uid"] for r in c.forget("other")] == ["youtube:b"]


def test_reset_seen_clears_items_and_runs(tmp_path):
    c = Corpus(tmp_path / "corpus.db")
    c.record(_item("youtube:a"), Verdict(9, True, "x"), "2026-07-07T10:00:00", digested=True)
    c.set_last_run("youtube", "2026-07-07T10:00:00+00:00")
    c.log_transcripts(3, "2026-07-07T10:00:00")
    n = c.reset_seen()
    assert n == 1
    assert c.stats()["total"] == 0
    assert c.get_last_run("youtube") is None               # last-run reset too
    assert c.transcripts_last_24h("2026-07-07T10:30:00") == 3   # rate-limit state preserved


def test_digest_for_you_section_separate_from_passes():
    scored = [
        (_item("youtube:1", "Novel release"), Verdict(9, True, "new", summary="A novel thing")),
        (_item("youtube:2", "Agentic video money"), Verdict(5, False, "not novel", summary="How to earn")),
    ]
    imap = {"youtube:2": "Using AI agents to generate money via agentic video"}
    subject, body = digestmod.compose(scored, "Mon 2026-07-07", interest_map=imap)
    assert "★1 for you" in subject
    assert "For you" in body and "Agentic video money" in body
    # the interest item (score 5) must NOT appear under Rejected — it's pulled into For you
    rejects_section = body.split("Rejected")[1]
    assert "Agentic video money" not in rejects_section
    html = digestmod.compose_html(scored, "Mon 2026-07-07", interest_map=imap)
    assert "For you" in html and "Agentic video money" in html
    assert "★" in html                                      # topic tag rendered


def test_run_threads_interest_end_to_end(tmp_path, monkeypatch, capsys):
    """Integration: an off-topic-by-relevance, out-of-recency item that matches an
    interest topic must survive both gates, get transcripted, and land in ★ For you."""
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path / "cfg"))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    cfg.init()
    from ai_digest import cli, youtube as yt
    importlib.reload(cli)
    monkeypatch.setattr(cli.cfg, "resolve_gemini_key", lambda conf: ("k", "TEST_KEY"))

    # Two candidates: v1 normal-relevant/novel, v2 off-topic-by-title but an interest.
    cands = [
        {"uid": "youtube:v1", "id": "v1", "title": "Novel agent release", "producer": "P", "url": "u1"},
        {"uid": "youtube:v2", "id": "v2", "title": "Make videos with Claude Code", "producer": "IndyDevDan", "url": "u2"},
    ]
    monkeypatch.setattr(cli.youtube, "list_candidates", lambda *a, **k: (list(cands), []))
    # prefilter keeps ONLY v1; v2 is "off-topic"
    monkeypatch.setattr(cli, "prefilter", lambda c, **k: ([cands[0]], [cands[1]]))
    # interest gate matches v2
    monkeypatch.setattr(cli, "classify_interests",
                        lambda c, topics, **k: {"youtube:v2": topics[0]})
    # enrichment: v1 fresh, v2 OLD (out of recency) — interest must bypass this
    from datetime import datetime, timezone, timedelta
    def fake_meta(cs, cutoff, **k):
        out = []
        for c in cs:
            status = "old" if c["id"] == "v2" else "ok"
            out.append({"cand": c, "status": status, "published": "", "description": f"desc-{c['id']}"})
        return out, []
    monkeypatch.setattr(cli.youtube, "collect_metadata", fake_meta)
    # description gate DROPS v2 (interest rescue must pull it back)
    monkeypatch.setattr(cli, "refine_by_description",
                        lambda fresh, **k: ([m for m in fresh if m["cand"]["id"] == "v1"],
                                            [m for m in fresh if m["cand"]["id"] == "v2"]))
    # transcripts for whatever is passed
    def fake_tx(kept, tmax, **k):
        res = [{"cand": s["cand"], "status": "ok",
                "item": Item(uid=s["cand"]["uid"], source="youtube", producer=s["cand"]["producer"],
                             title=s["cand"]["title"], url=s["cand"]["url"], text="body",
                             description=s.get("description", ""))} for s in kept]
        return res, [], False
    monkeypatch.setattr(cli.youtube, "fetch_transcripts", fake_tx)
    # scoring: v1 passes (9); v2 scores 7 — above the interest_floor so it stays in For you
    def fake_score(it, *a, **k):
        return Verdict(9 if it.uid == "youtube:v1" else 7, it.uid == "youtube:v1",
                       "r", summary=f"summary-{it.uid}")
    monkeypatch.setattr(cli, "score_item", fake_score)
    monkeypatch.setattr(cli, "deepen", lambda *a, **k: {})   # skip deep-dive LLM calls
    monkeypatch.setattr(cli.briefmod, "synthesize", lambda *a, **k: "")  # skip brief synthesis

    res = cli.run(dry_run=True)
    body = capsys.readouterr().out
    assert res["scanned"] == 2
    # v2 reached transcript+score despite being off-topic AND out-of-recency
    assert "For you" in body
    assert "Make videos with Claude Code" in body
    # and it is NOT double-listed as a reject
    assert "Make videos with Claude Code" not in body.split("Rejected")[1]


def test_interest_floor_demotes_thin_pick(tmp_path, monkeypatch, capsys):
    """An interest match whose TRANSCRIPT scores below interest_floor loses its
    ★ spot and falls to Rejected — 'confirm it's worth sharing' after transcript."""
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path / "cfg"))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    cfg.init()
    from ai_digest import cli
    importlib.reload(cli)
    monkeypatch.setattr(cli.cfg, "resolve_gemini_key", lambda conf: ("k", "TEST_KEY"))
    cands = [{"uid": "youtube:v1", "id": "v1", "title": "sponsored fluff", "producer": "P", "url": "u1"}]
    monkeypatch.setattr(cli.youtube, "list_candidates", lambda *a, **k: (list(cands), []))
    monkeypatch.setattr(cli, "prefilter", lambda c, **k: ([], list(cands)))          # off-topic
    monkeypatch.setattr(cli, "classify_interests", lambda c, t, **k: {"youtube:v1": t[0]})
    monkeypatch.setattr(cli.youtube, "collect_metadata",
                        lambda cs, cutoff, **k: ([{"cand": c, "status": "ok", "published": "", "description": "d"} for c in cs], []))
    monkeypatch.setattr(cli, "refine_by_description", lambda fresh, **k: (list(fresh), []))
    monkeypatch.setattr(cli.youtube, "fetch_transcripts",
                        lambda kept, tmax, **k: ([{"cand": kept[0]["cand"], "status": "ok",
                                                   "item": Item(uid="youtube:v1", source="youtube", producer="P",
                                                                title="sponsored fluff", url="u1", text="body")}], [], False))
    # transcript reveals it's thin: score 3 (< floor 6) -> demoted out of ★
    monkeypatch.setattr(cli, "score_item", lambda it, *a, **k: Verdict(3, False, "sponsor spot", summary="s"))
    monkeypatch.setattr(cli, "deepen", lambda *a, **k: {})
    monkeypatch.setattr(cli.briefmod, "synthesize", lambda *a, **k: "")
    res = cli.run(dry_run=True)
    body = capsys.readouterr().out
    assert res["scanned"] == 1
    # not in ★ For you; instead shown under Rejected
    assert "For you" not in body
    assert "Rejected" in body and "sponsored fluff" in body


def test_novelty_reserve_keeps_a_lane(tmp_path, monkeypatch, capsys):
    """With many interest items, novelty_reserve guarantees non-interest items get
    transcript slots instead of being fully crowded out."""
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path / "cfg"))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    cfg.init()
    from ai_digest import cli
    importlib.reload(cli)
    monkeypatch.setattr(cli.cfg, "resolve_gemini_key", lambda conf: ("k", "TEST_KEY"))
    # budget 15; interest items (40) FAR exceed the enrich cap (~30) — this is the
    # production shape that starved the lane: without reserving enrich slots for
    # non-interest, all enriched candidates are interest and no 'n*' ever fetches.
    cands = ([{"uid": f"youtube:i{i}", "id": f"i{i}", "title": f"i{i}", "producer": "P", "url": f"ui{i}"} for i in range(40)]
             + [{"uid": f"youtube:n{i}", "id": f"n{i}", "title": f"n{i}", "producer": "P", "url": f"un{i}"} for i in range(10)])
    monkeypatch.setattr(cli.youtube, "list_candidates", lambda *a, **k: (list(cands), []))
    monkeypatch.setattr(cli, "prefilter", lambda c, **k: (list(c), []))
    monkeypatch.setattr(cli, "classify_interests",
                        lambda c, t, **k: {f"youtube:i{i}": t[0] for i in range(40)})
    monkeypatch.setattr(cli.youtube, "collect_metadata",
                        lambda cs, cutoff, **k: ([{"cand": c, "status": "ok", "published": "", "description": "d"} for c in cs], []))
    monkeypatch.setattr(cli, "refine_by_description", lambda fresh, **k: (list(fresh), []))
    fetched = {}
    def fake_tx(kept, tmax, **k):
        res = []
        for s in kept:
            c = s["cand"]; fetched[c["uid"]] = True
            res.append({"cand": c, "status": "ok",
                        "item": Item(uid=c["uid"], source="youtube", producer="P",
                                     title=c["title"], url=c["url"], text="body")})
        return res, [], False
    monkeypatch.setattr(cli.youtube, "fetch_transcripts", fake_tx)
    monkeypatch.setattr(cli, "score_item", lambda it, *a, **k: Verdict(9, True, "r", summary="s"))
    monkeypatch.setattr(cli, "deepen", lambda *a, **k: {})
    monkeypatch.setattr(cli.briefmod, "synthesize", lambda *a, **k: "")
    cli.run(dry_run=True)
    # novelty_reserve=5 -> at least 5 of the non-interest 'n*' items fetched
    n_fetched = sum(1 for u in fetched if u.startswith("youtube:n"))
    assert n_fetched >= 5
    assert len(fetched) == 15                     # exactly the budget


def test_deep_dive_renders_learnings():
    scored = [(_item("youtube:1", "Big release"), Verdict(9, True, "new", summary="s"))]
    deep = {"youtube:1": {"learnings": ["set up X via Y", "run Z to get W"],
                          "why_novel": ["first open standard for it"]}}
    subject, body = digestmod.compose(scored, "Mon 2026-07-07", deep=deep)
    assert "The learnings" in body
    assert "What you'll learn" in body and "set up X via Y" in body
    assert "Why it's novel" in body and "first open standard for it" in body
    html = digestmod.compose_html(scored, "Mon 2026-07-07", deep=deep)
    assert "skip the video" in html.lower()
    assert "set up X via Y" in html and "first open standard for it" in html


def test_deepen_fails_soft_on_llm_error(monkeypatch):
    from ai_digest import score as sc
    from ai_digest.gemini import GeminiError
    def boom(*a, **k):
        raise GeminiError("429")
    monkeypatch.setattr(sc, "generate_json", boom)
    it = Item(uid="youtube:1", source="youtube", producer="P", title="t", url="u", text="body")
    assert sc.deepen(it, model="m", api_key="k", transcript_max_chars=100) == {}


def test_transcript_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path / "cfg"))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    from ai_digest import transcripts as ts
    importlib.reload(ts)
    it = Item(uid="youtube:abc123", source="youtube", producer="P", title="T",
              url="https://y/abc123", text="the full transcript body", published="2026-07-10")
    p = ts.save(it, fetched_at="2026-07-10T07:40:00", score=9)
    assert p.exists() and p.name == "abc123.json"
    assert ts.exists("youtube:abc123")
    d = ts.load("youtube:abc123")
    assert d["text"] == "the full transcript body" and d["score"] == 9
    assert d["video_id"] == "abc123" and d["producer"] == "P"
    assert d["segments"] == []                       # reserved, empty for now
    assert ts.load("youtube:missing") is None
    # save_many skips text-less / None items
    it2 = Item(uid="youtube:def", source="youtube", producer="P", title="T2", url="u", text="")
    assert ts.save_many([it, it2, None], fetched_at="2026-07-10T07:40:00") == 1


def test_partial_block_preserves_cooldown(tmp_path, monkeypatch):
    """A run that emails the transcripts it got BEFORE a block must still leave the
    block cooldown set — clearing it would let the next poll hammer a blocked endpoint."""
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path / "cfg"))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    cfg.init()
    from ai_digest import cli
    importlib.reload(cli)
    monkeypatch.setattr(cli.cfg, "resolve_gemini_key", lambda conf: ("k", "TEST_KEY"))
    cands = [{"uid": f"youtube:v{i}", "id": f"v{i}", "title": f"t{i}", "producer": "P", "url": f"u{i}"}
             for i in range(2)]
    monkeypatch.setattr(cli.youtube, "list_candidates", lambda *a, **k: (list(cands), []))
    monkeypatch.setattr(cli, "prefilter", lambda c, **k: (list(cands), []))
    monkeypatch.setattr(cli, "classify_interests", lambda c, t, **k: {})
    monkeypatch.setattr(cli.youtube, "collect_metadata",
                        lambda cs, cutoff, **k: ([{"cand": c, "status": "ok", "published": "", "description": "d"} for c in cs], []))
    monkeypatch.setattr(cli, "refine_by_description", lambda fresh, **k: (list(fresh), []))
    # v0 transcript OK, then a BLOCK -> blocked=True, one item still scored/emailed
    def fake_tx(kept, tmax, **k):
        first = kept[0]
        item = Item(uid=first["cand"]["uid"], source="youtube", producer="P",
                    title="t0", url="u0", text="body")
        return [{"cand": first["cand"], "status": "ok", "item": item}], ["ABORTED — blocked"], True
    monkeypatch.setattr(cli.youtube, "fetch_transcripts", fake_tx)
    monkeypatch.setattr(cli, "score_item",
                        lambda it, *a, **k: Verdict(9, True, "r", summary="s"))
    monkeypatch.setattr(cli, "deepen", lambda *a, **k: {})
    monkeypatch.setattr(cli.briefmod, "synthesize", lambda *a, **k: "")
    monkeypatch.setattr(cli, "send_email", lambda *a, **k: (True, "ok"))

    res = cli.run()
    assert res["emailed"] is True
    from ai_digest.corpus import Corpus
    cd = Corpus(cfg.corpus_path()).get_state("cooldown_until")
    assert cd is not None                        # cooldown survived the emailed partial run


def test_prompt_includes_baselines():
    it = _item("youtube:1", "Candidate Title")
    sib = _item("youtube:2", "Sibling Title")
    recent = [{"title": "Old News", "producer": "X", "reason": "covered", "score": 8}]
    prompt = scoremod.build_prompt(it, [it, sib], recent, 5000)
    assert "Sibling Title" in prompt
    assert "Old News" in prompt
    assert "Candidate Title" in prompt


# --- digest learn (playlist learnings mode) ---------------------------------
def test_list_playlist_shape(monkeypatch):
    from ai_digest import youtube as yt
    class _Fake:
        def __init__(self, o): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False):
            return {"entries": [
                {"id": "vid1", "title": "How to X", "uploader": "ChanA", "duration": 3600},
                {"id": None, "title": "skip me"},
                {"id": "vid2", "title": "How to Y", "channel": "ChanB"}]}
    monkeypatch.setattr(yt, "yt_dlp", type("m", (), {"YoutubeDL": _Fake}), raising=False)
    import sys, types
    fake = types.ModuleType("yt_dlp"); fake.YoutubeDL = _Fake
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    out = yt.list_playlist("https://youtube.com/playlist?list=PL123", 10)
    assert [v["id"] for v in out] == ["vid1", "vid2"]          # None id skipped
    assert out[0]["producer"] == "ChanA" and out[0]["duration"] == 3600
    assert out[1]["producer"] == "ChanB"


def test_summarize_learnings_parse(monkeypatch):
    from ai_digest import score as sc
    from ai_digest.record import Item
    monkeypatch.setattr(sc, "generate_json",
                        lambda *a, **k: {"headline": "Use tool X", "summary_md": "- do this\n- then that"})
    it = Item(uid="learn:v1", source="learn", producer="P", title="T", url="u", text="transcript here")
    r = sc.summarize_learnings(it, min_words=200, max_words=500, model="m", api_key="k", transcript_max_chars=1000)
    assert r["headline"] == "Use tool X" and "do this" in r["summary_md"]


def test_summarize_learnings_llm_fail_returns_none(monkeypatch):
    from ai_digest import score as sc
    from ai_digest.gemini import GeminiError
    from ai_digest.record import Item
    def boom(*a, **k): raise GeminiError("429")
    monkeypatch.setattr(sc, "generate_json", boom)
    it = Item(uid="learn:v1", source="learn", producer="P", title="T", url="u", text="x")
    assert sc.summarize_learnings(it, min_words=200, max_words=500, model="m", api_key="k", transcript_max_chars=10) is None


def test_compose_learn_html():
    from ai_digest.digest import compose_learn_html
    from ai_digest.record import Item
    it = Item(uid="learn:v1", source="learn", producer="ChanA", title="Big <Course>", url="https://y/v1")
    html = compose_learn_html(it, "The one takeaway", "Thesis.\n\n- point A\n- point **B**", duration=5400, playlist="Personal")
    assert html.startswith("<div") and 'href="https://y/v1"' in html
    assert "Big &lt;Course&gt;" in html                    # escaped
    assert "<li " in html and "<strong>B" in html          # markdown rendered
    assert "1h 30m" in html and "Personal" in html         # duration + playlist meta


# --- weekly brief (hero) -----------------------------------------------------
def test_gdocs_markdown_to_doc_builds_requests(monkeypatch):
    from ai_digest import gdocs
    calls = []
    def fake_gws(args, body=None, params=None):
        calls.append((args, body, params))
        if args[:3] == ["docs", "documents", "create"]:
            return {"documentId": "DOC1"}
        return {}                                    # batchUpdate ok
    monkeypatch.setattr(gdocs, "_gws", fake_gws)
    url = gdocs.markdown_to_doc("T", "# H1\n\n## H2\n\n- b1\n- b2\n\nplain [x](u) **bold**\n")
    assert url == "https://docs.google.com/document/d/DOC1/edit"
    # the batchUpdate request set: one insertText + heading styles + bullets
    bu = [b for a, b, p in calls if a[:3] == ["docs", "documents", "batchUpdate"]][0]
    reqs = bu["requests"]
    assert reqs[0]["insertText"]["text"].startswith("H1\n")     # markers stripped
    kinds = [list(r.keys())[0] for r in reqs]
    assert "updateParagraphStyle" in kinds and "createParagraphBullets" in kinds
    # link + bold flattened into the inserted text
    assert "x (u)" in reqs[0]["insertText"]["text"] and "**" not in reqs[0]["insertText"]["text"]


def test_gdocs_returns_none_when_create_fails(monkeypatch):
    from ai_digest import gdocs
    monkeypatch.setattr(gdocs, "_gws", lambda *a, **k: {"_error": "boom"})
    assert gdocs.markdown_to_doc("T", "# hi") is None


def test_brief_synthesize_and_failsoft(monkeypatch):
    from ai_digest import brief as b
    it = Item(uid="youtube:1", source="youtube", producer="P", title="T",
              url="u", text="a real transcript body")
    monkeypatch.setattr(b, "generate_json", lambda *a, **k: {"markdown": "# Brief\n\ncontent"})
    md = b.synthesize([it], style="dense", model="m", api_key="k", date_label="Fri")
    assert md.startswith("# Brief")
    assert b.synthesize([], style="dense", model="m", api_key="k", date_label="Fri") == ""
    # text-less items are skipped -> empty
    empty = Item(uid="youtube:2", source="youtube", producer="P", title="T", url="u", text="")
    assert b.synthesize([empty], style="verbose", model="m", api_key="k", date_label="Fri") == ""
    def boom(*a, **k):
        from ai_digest.gemini import GeminiError
        raise GeminiError("429")
    monkeypatch.setattr(b, "generate_json", boom)
    assert b.synthesize([it], style="dense", model="m", api_key="k", date_label="Fri") == ""


def test_brief_hero_renders_links_at_top():
    scored = [(_item("youtube:1", "X"), Verdict(9, True, "r", summary="s"))]
    links = {"verbose": "https://docs.google.com/document/d/V/edit",
             "dense": "https://docs.google.com/document/d/D/edit"}
    html = digestmod.compose_html(scored, "Fri", brief_links=links)
    assert "This week's briefing" in html
    assert 'href="https://docs.google.com/document/d/V/edit"' in html
    assert 'href="https://docs.google.com/document/d/D/edit"' in html
    # hero appears before the "Worth your time" section
    assert html.index("This week's briefing") < html.index("Worth your time")
    # no links -> no hero
    assert "This week's briefing" not in digestmod.compose_html(scored, "Fri")
