"""ai-digest — command-line entrypoint.

  digest init [--force]      scaffold ~/.config/ai-digest (+ seed channels)
  digest channels [--list]   show configured channels
  digest poll [--dry-run] [--no-email] [--limit N] [--model M]
                             run the pipeline: ingest -> score -> digest -> email
  digest doctor [--probe]    health check: config, secrets, cookies, cooldown
  digest stats               corpus counts
  digest export              re-print the most recent digest
  digest forget <keyword>    drop seen items matching keyword so they can resurface
  digest reset --seen [--yes]  clear the whole seen-set for a one-time clean-slate rerun
  digest learn [--dry-run]   summarize NEW videos in your learnings playlists —
                             one concise "learnings" email per video (no filtering)
  digest primer [--dry-run] [-n N]
                             concept-level rapid primer (<=5 min read) over the N
                             most recent STORED transcripts — no network calls

`poll --dry-run` scores and prints the digest but neither emails nor writes to
the corpus, so it is freely repeatable while tuning. A normal poll records every
scored item (passes feed the rolling-corpus baseline) and emails the digest.

`doctor` is offline by default (zero network). `doctor --probe` makes exactly ONE
transcript request to check whether YouTube is currently blocking us — safe, since
bans come from request *volume*, not a single call.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__, config as cfg
from .corpus import Corpus
from . import youtube
from . import transcripts as tstore
from .score import (score_item, prefilter, refine_by_description, classify_interests,
                    deepen, summarize_learnings)
from .gemini import GeminiError
from .digest import compose, compose_html, compose_learn_html
from .mailer import send_email
from . import brief as briefmod
from . import concepts as conceptmod
from . import primer as primermod
from . import gdocs


def _err(msg: str) -> int:
    print(f"digest: {msg}", file=sys.stderr)
    return 1


def _channels(conf: dict) -> list[dict]:
    return ((conf.get("youtube") or {}).get("channels")) or []


def cmd_init(args) -> int:
    p = cfg.init(force=args.force)
    n = len(_channels(cfg.load()))
    print(f"Config ready: {p}\nSeeded {n} YouTube channels. Edit the file to curate.")
    print(f"Set GEMINI_FREE_API_KEY in {cfg.SECRETS_ENV} (already present in this workspace).")
    return 0


def cmd_channels(args) -> int:
    chans = _channels(cfg.load())
    if not chans:
        print("No channels configured. Run `digest init`.")
        return 0
    for c in chans:
        print(f"  {c.get('name','?'):22} {c.get('handle','?')}")
    print(f"\n{len(chans)} channels.")
    return 0


def _cookie_report(cookies_file):
    """(status_str, ok_bool) describing the cookies.txt without any network."""
    if not cookies_file:
        return ("not set — transcript requests are unauthenticated (block-prone)", False)
    from pathlib import Path as _P
    p = _P(cookies_file).expanduser()
    if not p.exists():
        return (f"configured but MISSING at {p}", False)
    import http.cookiejar
    jar = http.cookiejar.MozillaCookieJar(str(p))
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except Exception as e:
        return (f"unparseable ({type(e).__name__}) — re-export cookies.txt", False)
    yt = [c for c in jar if "youtube" in (c.domain or "")]
    auth = [c for c in yt if c.name in ("LOGIN_INFO", "SID", "__Secure-1PSID", "__Secure-3PSID")]
    import time as _t
    expired = [c for c in auth if c.expires and c.expires < _t.time()]
    if not yt:
        return (f"{p.name}: no youtube.com cookies found — wrong export?", False)
    if not auth:
        return (f"{p.name}: {len(yt)} youtube cookies but no login cookie — export while logged IN", False)
    if expired:
        return (f"{p.name}: login cookies EXPIRED — re-export", False)
    return (f"{p.name}: {len(yt)} youtube cookies incl. login ✓", True)


def cmd_doctor(args) -> int:
    ok = "✓"; bad = "✗"; warn = "⚠"
    try:
        conf = cfg.load()
    except FileNotFoundError:
        return _err("no config — run `digest init` first")
    sc = conf.get("scoring", {}); rc = conf.get("recency", {}); yt = conf.get("youtube", {})
    dg = conf.get("digest", {})
    chans = _channels(conf)

    print("ai-digest doctor\n" + "─" * 48)
    # --- config ---
    print(f"  {ok} config: {cfg.config_path()}")
    print(f"     channels={len(chans)}  threshold={sc.get('threshold','?')}  "
          f"model={sc.get('model','?')}")
    print(f"     recency: since-last-run, {rc.get('min_window_hours','?')}h floor  |  "
          f"delays {sc.get('request_delay_sec','?')}s/{sc.get('channel_delay_sec','?')}s(+jitter)")
    print(f"     transcript caps: {sc.get('max_transcripts_per_poll','?')}/poll · "
          f"{sc.get('max_transcripts_per_hour','?')}/hr · {sc.get('max_transcripts_per_day','?')}/day · "
          f"~{sc.get('transcript_min_interval_sec','?')}s apart · scan {sc.get('scan_per_channel','?')}/ch")

    # --- secrets / email ---
    key, key_src = cfg.resolve_gemini_key(conf)
    print(f"  {ok if key else bad} Gemini key: {key_src if key else 'MISSING'}")
    gws = shutil.which("gws")
    print(f"  {ok if gws else bad} gws (email): {'on PATH' if gws else 'NOT on PATH'} "
          f"→ {dg.get('recipient','(no recipient)')}")

    # --- cookies ---
    cstat, cok = _cookie_report(yt.get("cookies_file") or None)
    print(f"  {ok if cok else warn} cookies: {cstat}")

    # --- cooldown / corpus ---
    corpus = Corpus(cfg.corpus_path())
    now = datetime.now(timezone.utc)
    cd = corpus.get_state("cooldown_until")
    cd_active = False
    if cd:
        try:
            cd_ts = datetime.fromisoformat(cd)
            if now < cd_ts:
                cd_active = True
                mins = int((cd_ts - now).total_seconds() // 60)
                print(f"  {warn} cooldown: ACTIVE ~{mins} min left (until "
                      f"{cd_ts.astimezone().strftime('%Y-%m-%d %H:%M')}) — poll will skip unless --force")
        except ValueError:
            pass
    if not cd_active:
        print(f"  {ok} cooldown: none active")
    s = corpus.stats()
    lr = corpus.get_last_run(youtube.SOURCE)
    print(f"  {ok} corpus: {s['total']} seen / {s['passed']} passed  |  last_run={lr or 'never'}")
    # tx_log stamps are logged naive-local (see run()); match that convention here
    # so the rolling-window report lines up with the actual limiter.
    now_naive = datetime.now().isoformat()
    tx_hr = corpus.transcripts_in_window(now_naive, 1)
    tx24 = corpus.transcripts_in_window(now_naive, 24)
    hr_cap = int(sc.get("max_transcripts_per_hour", 30))
    day_cap = int(sc.get("max_transcripts_per_day", 120))
    mark = warn if (tx_hr >= hr_cap or tx24 >= day_cap) else ok
    print(f"  {mark} transcript budget: {tx_hr}/{hr_cap} last hour · {tx24}/{day_cap} last 24h")

    # --- optional single-request live probe ---
    if args.probe:
        print("─" * 48 + "\n  probe: ONE transcript request (checking block status)...")
        session = youtube.build_session(yt.get("cookies_file") or None)
        vid = None
        if chans:
            try:
                recent = youtube.list_recent(chans[0]["handle"], 1)   # 1 flat listing (not transcript-blocked)
                vid = recent[0]["id"] if recent else None
            except Exception as e:
                print(f"     {warn} channel listing failed: {type(e).__name__}")
        vid = vid or "dQw4w9WgXcQ"
        try:
            text = youtube.fetch_transcript(
                vid, session=session, cookies_file=yt.get("cookies_file") or None,
                cookies_from_browser=yt.get("cookies_from_browser") or None,
                js_runtime=yt.get("js_runtime") or None)
            if text:
                print(f"     {ok} NOT blocked — transcript fetched ({len(text)} chars). Safe to `digest poll`.")
            else:
                print(f"     {ok} not blocked (that video had no captions, but the request went through).")
        except youtube.TranscriptBlocked as e:
            print(f"     {bad} STILL BLOCKED ({e}). Add cookies_file or wait. Not polling.")
    else:
        print("─" * 48 + "\n  (run `digest doctor --probe` for a single-request live block check)")
    return 0


def cmd_stats(args) -> int:
    c = Corpus(cfg.corpus_path())
    s = c.stats()
    print(f"corpus: {s['total']} items seen, {s['passed']} passed (digested)")
    k = c.concept_stats()
    print(f"ledger: {k['concepts']} concepts, {k['mentions']} mentions")
    if k["concepts"]:
        # A young ledger cannot support novelty/velocity claims, so say so
        # rather than letting an empty history read as "nothing is new".
        presc = conceptmod.prescience_scores(c.first_raise_stats(converge_at=2))
        if presc:
            top = sorted(presc.items(), key=lambda kv: -kv[1])[:5]
            print("  earned prescience: "
                  + ", ".join(f"{p} {v:.2f}" for p, v in top))
        else:
            print("  earned prescience: none yet (needs more runs to accrue)")
    else:
        print("  (no primer runs yet — novelty/velocity not meaningful)")
    return 0


def cmd_export(args) -> int:
    d = cfg.digests_dir()
    files = sorted(d.glob("*.md")) if d.exists() else []
    if not files:
        return _err("no digests found yet")
    print(files[-1].read_text())
    return 0


def run(*, dry_run: bool = False, no_email: bool = False,
        limit: int | None = None, model: str | None = None,
        force: bool = False) -> dict:
    """Programmatic entrypoint (chainable). Returns a summary dict."""
    conf = cfg.load()
    sc = conf.get("scoring", {})
    dg = conf.get("digest", {})
    model = model or sc.get("model", "gemini-2.5-flash")
    threshold = int(sc.get("threshold", 7))
    scan_per_channel = int(sc.get("scan_per_channel", sc.get("max_new_per_channel", 8)))
    max_transcripts = int(sc.get("max_transcripts_per_poll", sc.get("max_total_items", 15)))
    max_tx_hour = int(sc.get("max_transcripts_per_hour", 30))
    max_tx_day = int(sc.get("max_transcripts_per_day", 120))
    tx_interval = float(sc.get("transcript_min_interval_sec", 20))
    enrich_mult = int(sc.get("enrich_multiple", 2))
    tmax = int(sc.get("transcript_max_chars", 24000))
    ctx_n = int(sc.get("corpus_context_n", 40))
    req_delay = float(sc.get("request_delay_sec", 4.0))
    chan_delay = float(sc.get("channel_delay_sec", 4.0))
    cooldown_h = float(sc.get("cooldown_hours", 12))
    novelty_reserve = int(sc.get("novelty_reserve", 5))    # transcript slots kept for non-interest
    interest_floor = int(sc.get("interest_floor", 6))      # min transcript score for ★ For you
    persist_tx = bool(sc.get("persist_transcripts", True)) # keep raw transcripts on disk
    rc = conf.get("recency", {})
    min_window_h = float(rc.get("min_window_hours", 24))
    init_window_h = float(rc.get("initial_window_hours", 24))
    yt = conf.get("youtube", {})
    cookies_file = yt.get("cookies_file") or None
    cookies_from_browser = yt.get("cookies_from_browser") or None
    js_runtime = yt.get("js_runtime") or None
    recipient = dg.get("recipient")

    api_key, key_src = cfg.resolve_gemini_key(conf)
    if not api_key:
        raise RuntimeError(f"No Gemini API key found in secrets/.env (tried {key_src})")
    print(f"LLM key: {key_src}")

    corpus = Corpus(cfg.corpus_path())

    # Cooldown gate: after a block we refuse to poll until it lapses (retrying
    # only deepens a YouTube ban). --force / dry-run may override.
    now = datetime.now(timezone.utc)
    cd = corpus.get_state("cooldown_until")
    if cd and not force:
        try:
            cd_ts = datetime.fromisoformat(cd)
        except ValueError:
            cd_ts = None
        if cd_ts and now < cd_ts:
            mins = int((cd_ts - now).total_seconds() // 60)
            print(f"In transcript-block cooldown for ~{mins} more min (until "
                  f"{cd_ts.astimezone().strftime('%Y-%m-%d %H:%M')}). Skipping poll. "
                  f"Add cookies_file to config or pass force=True to override.")
            return {"scanned": 0, "passed": 0, "warnings": ["cooldown"], "emailed": False, "cooldown": True}

    chans = _channels(conf)
    if limit:
        chans = chans[:limit]

    # Recency cutoff: since last run, but never a window shorter than min_window_h.
    last_run = corpus.get_last_run(youtube.SOURCE)
    if last_run:
        try:
            lr = datetime.fromisoformat(last_run)
            cutoff = min(lr, now - timedelta(hours=min_window_h))
        except ValueError:
            cutoff = now - timedelta(hours=init_window_h)
    else:
        cutoff = now - timedelta(hours=init_window_h)

    auth = "cookies" if cookies_file else "no-auth"
    now_iso = datetime.now().isoformat(timespec="seconds")

    # ── Stage 1: cheap scan of ALL channels (titles only; safe endpoint) ──────
    print(f"[1/3] Scanning {len(chans)} channels for new titles "
          f"(since={cutoff.astimezone().strftime('%Y-%m-%d %H:%M')}, {auth})...")
    candidates, warnings = youtube.list_candidates(
        chans, corpus.seen, scan_per_channel, channel_delay_sec=chan_delay, log=print)
    for w in warnings:
        print(f"  ! {w}")
    if not candidates:
        print("No new uploads since last poll.")
        if not dry_run:
            corpus.set_last_run(youtube.SOURCE, now.isoformat())
        return {"scanned": 0, "passed": 0, "warnings": warnings, "emailed": False}

    # ── Stage 2: title RELEVANCE gate (no YouTube requests) ───────────────────
    # Relevance and budget are separate axes. Only OFF-TOPIC is dropped here;
    # relevant-but-over-budget items DEFER (left unseen), never discarded.
    print(f"[2/4] Relevance-filtering {len(candidates)} titles...")
    try:
        relevant, irrelevant = prefilter(candidates, model=model, api_key=api_key)
    except GeminiError as e:
        # LLM rate-limited/down: defer the WHOLE poll (don't fail open, don't advance
        # last_run) so it retries next poll — nothing marked seen, no email.
        print(f"  LLM unavailable ({e}) — deferring this poll, nothing sent. "
              f"(Gemini free-tier rate limit; retries next run.)")
        return {"scanned": len(candidates), "passed": 0, "warnings": warnings,
                "emailed": False, "llm_error": True}
    # ── Personal-interest gate (additive) ────────────────────────────────────
    # Interest matches are NEVER dropped as off-topic and are PRIORITIZED for the
    # transcript budget; they surface in a dedicated "★ For you" digest section.
    topics = (conf.get("interests") or {}).get("topics") or []
    interest_map: dict[str, str] = {}
    if topics:
        try:
            interest_map = classify_interests(candidates, topics, model=model, api_key=api_key)
        except GeminiError:
            interest_map = {}                              # additive — never blocks the poll
        if interest_map:
            # Interest matches go to the FRONT (prioritized) and are protected from
            # the off-topic drop; the prefilter's best-first ranking is preserved for
            # the remaining relevant items. interest_items and rest are disjoint.
            irrelevant = [c for c in irrelevant if c["uid"] not in interest_map]
            interest_items = [c for c in candidates if c["uid"] in interest_map]
            rest = [c for c in relevant if c["uid"] not in interest_map]
            relevant = interest_items + rest
            print(f"  ★ personal-interest matches: {len(interest_map)} "
                  f"(protected from off-topic drop, prioritized)")

    if not dry_run:
        for c in irrelevant:
            corpus.mark_seen(c, "skipped on title (off-topic)", now_iso)

    # Proactive RATE limit (research: transcript endpoint soft-blocks ~100-200/hr).
    # budget = min(per-poll, hourly-remaining, daily-remaining). Overflow defers.
    tx_hr = corpus.transcripts_in_window(now_iso, 1)
    tx_day = corpus.transcripts_in_window(now_iso, 24)
    budget = max(0, min(max_transcripts, max_tx_hour - tx_hr, max_tx_day - tx_day))
    print(f"  relevant {len(relevant)} · off-topic {len(irrelevant)} · "
          f"transcript budget {budget} (poll {max_transcripts}, "
          f"hour {tx_hr}/{max_tx_hour}, day {tx_day}/{max_tx_day})")
    if budget == 0:
        print("  rate budget exhausted — deferring ALL this run to protect against blocks.")
        if not dry_run:
            corpus.set_last_run(youtube.SOURCE, now.isoformat())
        return {"scanned": len(candidates), "passed": 0, "warnings": warnings,
                "emailed": False, "rate_limited": True, "skipped": len(skipped_audit)}

    # ── Stage 3: metadata enrichment (page GETs; NOT the transcript endpoint) ──
    # Pull description+date for up to budget*enrich_mult top candidates, then a
    # DESCRIPTION gate drops off-topic/marketing the title missed BEFORE any
    # transcript is spent. Recency is applied here too.
    # Build the enrichment set so the NOVELTY LANE actually has candidates. Because
    # `relevant` is interest-first, naively enriching relevant[:enrich_n] fills every
    # slot with interest items → zero non-interest reach the reserve downstream (this
    # silently starved the lane: every fetched item came back interest-matched). So
    # explicitly reserve enrich slots for non-interest, mirroring novelty_reserve.
    enrich_n = min(len(relevant), max(budget * enrich_mult, budget))
    rel_i = [c for c in relevant if c["uid"] in interest_map]
    rel_n = [c for c in relevant if c["uid"] not in interest_map]
    n_slots = min(len(rel_n), novelty_reserve * enrich_mult)      # non-interest enrich reserve
    i_slots = max(0, enrich_n - n_slots)
    to_enrich = rel_i[:i_slots] + rel_n[:n_slots]
    print(f"[3/4] Enriching {len(to_enrich)} candidates ({len(rel_i[:i_slots])} interest + "
          f"{len(rel_n[:n_slots])} novelty-lane) with description (page metadata)...")
    meta, wm = youtube.collect_metadata(to_enrich, cutoff, request_delay_sec=req_delay, log=print)
    for w in wm:
        print(f"  ! {w}"); warnings.append(w)
    # Interest items bypass the recency drop too (they surface even if not brand-new).
    fresh = [m for m in meta if m["status"] == "ok" or m["cand"]["uid"] in interest_map]
    if not dry_run:
        for m in meta:
            if m["status"] == "old" and m["cand"]["uid"] not in interest_map:
                corpus.mark_seen(m["cand"], "out of recency window", now_iso)

    try:
        kept, desc_dropped = refine_by_description(fresh, model=model, api_key=api_key)
    except GeminiError as e:
        print(f"  LLM unavailable ({e}) — deferring this poll, nothing sent.")
        return {"scanned": len(candidates), "passed": 0, "warnings": warnings,
                "emailed": False, "llm_error": True}
    if interest_map:
        # Rescue interest items from the description gate; keep them at the front.
        rescued = [m for m in desc_dropped if m["cand"]["uid"] in interest_map]
        desc_dropped = [m for m in desc_dropped if m["cand"]["uid"] not in interest_map]
        kept_uids = {m["cand"]["uid"] for m in kept}
        kept = ([m for m in rescued if m["cand"]["uid"] not in kept_uids]
                + [m for m in kept if m["cand"]["uid"] in interest_map]
                + [m for m in kept if m["cand"]["uid"] not in interest_map])
    if not dry_run:
        for m in desc_dropped:
            corpus.mark_seen(m["cand"], "skipped on description (off-topic/thin)", now_iso)

    # Budget allocation with a NOVELTY LANE: reserve up to novelty_reserve slots for
    # non-interest items so a big interest backlog can't starve pure-novelty finds.
    # Interest items still take the majority (they're prioritized), just not all of it.
    ik = [m for m in kept if m["cand"]["uid"] in interest_map]
    nk = [m for m in kept if m["cand"]["uid"] not in interest_map]
    reserve = min(novelty_reserve, len(nk), budget)
    picked_i = ik[:max(0, budget - reserve)]
    picked_n = nk[:budget - len(picked_i)]
    picked_uids = {m["cand"]["uid"] for m in picked_i + picked_n}
    to_fetch = picked_i + picked_n
    deferred = [m for m in kept if m["cand"]["uid"] not in picked_uids]
    print(f"  fresh {len(fresh)} · description-dropped {len(desc_dropped)} · "
          f"fetching {len(to_fetch)} · deferring {len(deferred)}")

    # ── Stage 4: transcripts for the vetted+budgeted shortlist (rate-paced) ────
    print(f"[4/4] Fetching {len(to_fetch)} transcripts (~{tx_interval:g}s apart)...")
    results, w2, blocked = youtube.fetch_transcripts(
        to_fetch, tmax, min_interval_sec=tx_interval,
        cookies_file=cookies_file, cookies_from_browser=cookies_from_browser,
        js_runtime=js_runtime, log=print)
    tx_hits = sum(1 for r in results if r["status"] in ("ok", "nocaps"))
    if not dry_run:
        corpus.log_transcripts(tx_hits, now_iso)
        for r in results:
            if r["status"] == "nocaps":
                corpus.mark_seen(r["cand"], "no captions", now_iso)
    for w in w2:
        print(f"  ! {w}"); warnings.append(w)

    items = [r["item"] for r in results if r["status"] == "ok"]
    # "skipped on title" audit = title off-topic + description-gate drops
    skipped_audit = list(irrelevant) + [m["cand"] for m in desc_dropped]

    if blocked and not dry_run:
        until = now + timedelta(hours=cooldown_h)
        corpus.set_state("cooldown_until", until.isoformat())
        fix = ("Fix: add a youtube.cookies_file; then polls authenticate."
               if not cookies_file else
               "Cookies ARE set (auth got some through before the 429) — this IP is "
               "rate-flagged on the transcript endpoint; durable fix = audio→Gemini or a proxy.")
        print(f"Entered cooldown until {until.astimezone().strftime('%Y-%m-%d %H:%M')} "
              f"(~{cooldown_h:g}h). {fix}")

    if not items:
        print("No transcript-worthy new items this poll.")
        if not dry_run and not blocked:
            corpus.set_last_run(youtube.SOURCE, now.isoformat())
        return {"scanned": len(candidates), "passed": 0, "warnings": warnings,
                "emailed": False, "blocked": blocked, "skipped": len(skipped_audit)}

    # ── Score the shortlist's transcripts (full novelty judgment) ─────────────
    recent = corpus.recent_context(ctx_n)
    print(f"Scoring {len(items)} transcripts...")
    scored = []
    for it in items:
        v = score_item(it, items, recent, model=model, api_key=api_key,
                       threshold=threshold, transcript_max_chars=tmax)
        scored.append((it, v))
        print(f"  [{v.score:>2}/10 {'PASS' if v.passed else 'skip'}] {it.producer}: {it.title[:60]}")

    # If EVERY score errored (LLM rate-limited), don't email a broken 0-pass digest.
    # Defer: don't advance last_run and don't record, so the poll retries cleanly.
    if scored and all(v.error for _, v in scored):
        print("All scoring calls failed (LLM rate-limited) — deferring, not sending a broken digest.")
        return {"scanned": len(candidates), "passed": 0, "warnings": warnings,
                "emailed": False, "llm_error": True}

    # Re-confirm interest picks against their TRANSCRIPT: an interest match earns a
    # ★ For you spot only if the transcript scores >= interest_floor. Marketing/thin
    # ones (the rubric caps those <=3) drop out of ★ and fall to the normal reject
    # bucket — "reassess once we have the transcript, then confirm it's worth sharing."
    demoted = {it.uid for it, v in scored if it.uid in interest_map and v.score < interest_floor}
    if demoted:
        interest_map = {u: t for u, t in interest_map.items() if u not in demoted}
        print(f"  ★ demoted {len(demoted)} interest pick(s) below transcript floor "
              f"{interest_floor} → moved to Rejected")

    # ── Deep-dive: a "skip the video" learnings briefing for each CHOSEN item ──
    # Chosen = ★ For you (interest, >= floor) + novelty passes (>= threshold).
    chosen = [(it, v) for it, v in scored
              if (it.uid in interest_map) or v.passed]
    deep: dict[str, dict] = {}
    if chosen:
        print(f"Writing deep-dive briefings for {len(chosen)} chosen item(s)...")
        for it, v in chosen:
            d = deepen(it, model=model, api_key=api_key, transcript_max_chars=tmax)
            if not d and v.key_points:
                # deep-dive LLM call failed → fall back to the scorer's key takeaways
                # so a chosen video is never left with no learnings at all.
                d = {"learnings": list(v.key_points), "why_novel": []}
            if d:
                deep[it.uid] = d

    date_label = datetime.now().strftime("%a %Y-%m-%d")

    # ── Weekly BRIEF (hero): synthesize the chosen transcripts into ONE article,
    #    in each configured style, publish each as a Google Doc via gws, and link
    #    them at the top of the email. Degrades cleanly — a failed brief/Doc just
    #    omits that link; the per-video digest below is unaffected.
    brief_conf = conf.get("brief", {})
    brief_styles = list(brief_conf.get("styles", ["dense"])) \
        if bool(brief_conf.get("enabled", True)) else []
    brief_links: dict[str, str] = {}
    chosen_items = [it for it, _ in chosen]
    if brief_styles and chosen_items:
        stamp = datetime.now().strftime("%y%m%d-%H%M")
        print(f"Synthesizing brief(s) {brief_styles} from {len(chosen_items)} transcripts...")
        for style in brief_styles:
            md = briefmod.synthesize(chosen_items, style=style, model=model,
                                     api_key=api_key, date_label=date_label, deep=deep)
            if not md:
                print(f"  brief[{style}]: synthesis unavailable (LLM error) — skipped")
                continue
            cfg.digests_dir().mkdir(parents=True, exist_ok=True)
            (cfg.digests_dir() / f"{stamp}-brief-{style}.md").write_text(md)
            if not dry_run:
                url = gdocs.markdown_to_doc(f"AI Brief · {style} · {date_label}", md)
                if url:
                    brief_links[style] = url
                    print(f"  brief[{style}]: {url}")
                else:
                    print(f"  brief[{style}]: Google Doc creation failed (gws)")

    subject, body = compose(scored, date_label, skipped=skipped_audit,
                            interest_map=interest_map, deep=deep)

    if dry_run:
        print("\n" + "=" * 70 + "\n[DRY RUN] digest below — not emailed, corpus not written\n" + "=" * 70)
        print(body)
        passed = sum(1 for _, v in scored if v.passed)
        return {"scanned": len(scored), "passed": passed, "warnings": warnings,
                "emailed": False, "dry_run": True, "skipped": len(skipped_audit)}

    cfg.digests_dir().mkdir(parents=True, exist_ok=True)
    out = cfg.digests_dir() / f"{datetime.now().strftime('%y%m%d-%H%M')}-digest.md"
    out.write_text(body)

    emailed = False
    if recipient and not no_email:
        ok, msg = send_email(recipient, subject,
                             compose_html(scored, date_label, skipped=skipped_audit,
                                          interest_map=interest_map, deep=deep,
                                          brief_links=brief_links), html=True)
        emailed = ok
        print(f"\nEmail to {recipient}: {'sent (HTML)' if ok else 'FAILED — ' + msg}")
    else:
        print(f"\n(email skipped) digest written to {out}")

    for it, v in scored:
        corpus.record(it, v, now_iso, digested=(v.passed and emailed))
    if persist_tx:
        # Persist raw transcripts (all scored items, pass or not — we spent the
        # fetch) so digests can be re-synthesized without re-hitting the guarded
        # endpoint. Files, not the corpus DB.
        n_tx = tstore.save_many([it for it, _ in scored], fetched_at=now_iso,
                                scores={it.uid: v.score for it, v in scored})
        print(f"Persisted {n_tx} transcript(s) → {cfg.transcripts_dir()}")
    corpus.set_last_run(youtube.SOURCE, now.isoformat())
    if not blocked:
        # Only a clean (unblocked) run clears the cooldown. A partial block still
        # emails the transcripts we got, but the block cooldown MUST persist so the
        # next poll backs off instead of hammering a still-blocked endpoint.
        corpus.set_state("cooldown_until", None)

    passed = sum(1 for _, v in scored if v.passed)
    for_you = sum(1 for it, _ in scored if it.uid in interest_map)
    print(f"Done. {passed}/{len(scored)} passed · ★{for_you} for you "
          f"({len(irrelevant)} off-topic, {len(deferred)} deferred). Digest: {out}")
    return {"scanned": len(scored), "passed": passed, "for_you": for_you, "warnings": warnings,
            "emailed": emailed, "digest_file": str(out), "skipped": len(skipped_audit)}


def cmd_forget(args) -> int:
    removed = Corpus(cfg.corpus_path()).forget(args.keyword)
    if not removed:
        print(f"No seen items matched '{args.keyword}'.")
        return 0
    for r in removed:
        print(f"  forgot: {r.get('title','')} — {r.get('producer','')}")
    print(f"\nForgot {len(removed)} item(s) matching '{args.keyword}'. "
          f"They can resurface on the next poll.")
    return 0


def cmd_reset(args) -> int:
    if not args.seen:
        return _err("reset requires --seen (the only supported scope)")
    corpus = Corpus(cfg.corpus_path())
    n = corpus.stats()["total"]
    if not args.yes:
        print(f"This will clear {n} seen item(s) and reset last-run (config + rate "
              f"limits preserved).\nRe-run with `digest reset --seen --yes` to confirm.")
        return 0
    cleared = corpus.reset_seen()
    print(f"Cleared {cleared} seen item(s) + last-run. "
          f"The next poll re-considers all history under the current rules.")
    return 0


def cmd_poll(args) -> int:
    try:
        run(dry_run=args.dry_run, no_email=args.no_email, limit=args.limit,
            model=args.model, force=args.force)
        return 0
    except (RuntimeError, FileNotFoundError) as e:
        return _err(str(e))


def run_learn(*, dry_run: bool = False, no_email: bool = False,
              limit: int | None = None, model: str | None = None,
              force: bool = False) -> dict:
    """`digest learn` — summarize each NEW video in the curated learnings
    playlists (one concise email per video). No filtering; reuses the shared
    transcript rate-limiter + cookies + cooldown. Returns a summary dict."""
    conf = cfg.load()
    sc = conf.get("scoring", {})
    ln = conf.get("learn", {})
    playlists = ln.get("playlists", []) or []
    if not playlists:
        print("No [learn.playlists] configured. Add one in config.toml.")
        return {"new": 0, "emailed": 0}
    model = model or sc.get("model", "gemini-2.5-flash")
    recipient = ln.get("recipient") or (conf.get("digest", {}) or {}).get("recipient")
    # Searchable subject token — the 📝 emoji is NOT searchable (Gmail strips
    # emoji from queries), so every learn subject carries a plain-ASCII tag.
    # Search it as a quoted phrase: subject:"AI Summary".
    subject_tag = str(ln.get("subject_tag", "AI Summary:")).strip()
    tag_prefix = f"{subject_tag} " if subject_tag else ""
    min_w = int(ln.get("summary_min_words", 200))
    max_w = int(ln.get("summary_max_words", 500))
    l_tmax = int(ln.get("transcript_max_chars", 200000))
    max_per_run = int(ln.get("max_per_run", 10))
    max_tx_hour = int(sc.get("max_transcripts_per_hour", 30))
    max_tx_day = int(sc.get("max_transcripts_per_day", 120))
    tx_interval = float(sc.get("transcript_min_interval_sec", 20))
    cooldown_h = float(sc.get("cooldown_hours", 12))
    persist_tx = bool(sc.get("persist_transcripts", True))
    yt = conf.get("youtube", {})
    cookies_file = yt.get("cookies_file") or None
    cookies_from_browser = yt.get("cookies_from_browser") or None
    js_runtime = yt.get("js_runtime") or None

    api_key, key_src = cfg.resolve_gemini_key(conf)
    if not api_key:
        raise RuntimeError(f"No Gemini API key found in secrets/.env (tried {key_src})")
    print(f"LLM key: {key_src}")

    corpus = Corpus(cfg.corpus_path())
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    # Shared block cooldown (learn and poll both hit the transcript endpoint).
    cd = corpus.get_state("cooldown_until")
    if cd and not force:
        try:
            cd_ts = datetime.fromisoformat(cd)
        except ValueError:
            cd_ts = None
        if cd_ts and now < cd_ts:
            mins = int((cd_ts - now).total_seconds() // 60)
            print(f"In transcript-block cooldown ~{mins} more min. Skipping. (--force overrides.)")
            return {"new": 0, "emailed": 0, "cooldown": True}

    # ── Stage 1: list each playlist, collect NEW videos (uid = learn:<id>) ────
    new = []
    for pl in playlists:
        name = pl.get("name") or "?"
        url = pl.get("url")
        if not url:
            continue
        try:
            vids = youtube.list_playlist(url, 50)
        except Exception as e:
            print(f"  ! playlist '{name}' list failed — {type(e).__name__}; skipped")
            continue
        fresh = 0
        for v in vids:
            uid = f"learn:{v['id']}"
            if corpus.seen(uid):
                continue
            new.append({"cand": {"id": v["id"], "uid": uid, "title": v["title"],
                                 "url": v["url"], "producer": v.get("producer", ""), "source": "learn"},
                        "published": "", "description": "",
                        "playlist": name, "duration": v.get("duration")})
            fresh += 1
        print(f"  {name}: {len(vids)} in playlist, {fresh} new")
    if limit:
        new = new[:limit]
    if not new:
        print("No new videos in any learnings playlist.")
        return {"new": 0, "emailed": 0}

    # Rate budget (shared hourly/daily transcript cap).
    tx_hr = corpus.transcripts_in_window(now_iso, 1)
    tx_day = corpus.transcripts_in_window(now_iso, 24)
    budget = max(0, min(max_per_run, max_tx_hour - tx_hr, max_tx_day - tx_day))
    to_do = new[:budget]
    deferred = new[budget:]
    print(f"{len(new)} new → summarizing {len(to_do)} "
          f"(hour {tx_hr}/{max_tx_hour}, day {tx_day}/{max_tx_day}); deferring {len(deferred)}")
    if budget == 0:
        print("Rate budget exhausted — deferring all to next run (protects against blocks).")
        return {"new": len(new), "emailed": 0, "deferred": len(new)}

    # ── Stage 2: transcripts, rate-paced ─────────────────────────────────────
    results, warns, blocked = youtube.fetch_transcripts(
        to_do, l_tmax, min_interval_sec=tx_interval, cookies_file=cookies_file,
        cookies_from_browser=cookies_from_browser, js_runtime=js_runtime, log=print)
    tx_hits = sum(1 for r in results if r["status"] in ("ok", "nocaps"))
    if not dry_run:
        corpus.log_transcripts(tx_hits, now_iso)
    for w in warns:
        print(f"  ! {w}")
    meta_by_uid = {n["cand"]["uid"]: n for n in to_do}

    # ── Stage 3: summarize each + one email per video ────────────────────────
    sent = nocaps = failed = 0
    for r in results:
        cand = r["cand"]
        nmeta = meta_by_uid.get(cand["uid"], {})
        if r["status"] == "nocaps":
            nocaps += 1
            print(f"  – no transcript: {cand['title'][:60]}")
            if not dry_run:
                if recipient and not no_email:
                    body = (f'<div style="font-family:sans-serif;font-size:14px;">Couldn\'t get a '
                            f'transcript (no captions) for <a href="{cand["url"]}">{cand["title"]}</a>. '
                            f'<a href="{cand["url"]}">Watch on YouTube</a>.</div>')
                    send_email(recipient, f"📝 {tag_prefix}(no transcript) {cand['title']}",
                               body, html=True)
                corpus.mark_seen(cand, "learn: no captions", now_iso)
            continue
        item = r["item"]
        s = summarize_learnings(item, min_words=min_w, max_words=max_w,
                                model=model, api_key=api_key, transcript_max_chars=l_tmax)
        if not s:
            failed += 1                       # LLM failed -> do NOT mark seen; retries next run
            print(f"  … summarize deferred (LLM) : {item.title[:55]}")
            continue
        print(f"  ✓ {item.title[:62]} — {s['headline'][:50]}")
        if dry_run:
            print("     [dry-run] " + s["summary_md"][:200].replace("\n", " "))
            continue
        html = compose_learn_html(item, s["headline"], s["summary_md"],
                                  duration=nmeta.get("duration"), playlist=nmeta.get("playlist", ""))
        if recipient and not no_email:
            ok, msg = send_email(recipient, f"📝 {tag_prefix}{item.title}", html, html=True)
            print(f"     email → {recipient}: {'sent' if ok else 'FAILED — ' + msg}")
        if persist_tx:
            try:
                tstore.save(item, fetched_at=now_iso)
            except Exception:
                pass
        corpus.mark_seen(cand, "learn: summarized", now_iso)
        sent += 1

    if blocked and not dry_run:
        until = now + timedelta(hours=cooldown_h)
        corpus.set_state("cooldown_until", until.isoformat())
        print(f"Entered cooldown until {until.astimezone().strftime('%Y-%m-%d %H:%M')} (~{cooldown_h:g}h).")

    print(f"Done. {sent} summarized+emailed · {nocaps} no-transcript · "
          f"{failed + len(deferred)} deferred.")
    return {"new": len(new), "emailed": sent, "nocaps": nocaps,
            "deferred": failed + len(deferred), "blocked": blocked}


def run_primer(*, dry_run: bool = False, no_email: bool = False,
               n: int = 12, since: str | None = None,
               model: str | None = None, save: bool = True,
               refresh: bool = False) -> dict:
    """`digest primer` — concept-level rapid primer over recent transcripts.

    Reads the stored transcripts (no network, no YouTube rate-limit exposure),
    extracts concepts per video, clusters them across videos, links them to the
    persistent ledger, ranks by convergence AND early-authority, then composes a
    hard-capped primer. Safe and cheap to re-run while tuning.
    """
    conf = cfg.load()
    sc = conf.get("scoring", {})
    pr = conf.get("primer", {}) or {}
    model = model or sc.get("model", "gemini-2.5-flash")
    recipient = pr.get("recipient") or (conf.get("digest", {}) or {}).get("recipient")
    tmax = int(sc.get("transcript_max_chars", 24000))
    max_words = int(pr.get("max_words", 1000))
    n_head = int(pr.get("n_headlines", 8))
    n_dives = int(pr.get("n_dives", 4))
    converge_at = int(pr.get("converge_at", 3))
    min_firsts = int(pr.get("min_firsts", 3))
    trusted = set(pr.get("trusted_sources", []) or [])
    weights = dict(pr.get("weights", {}) or {})

    api_key, key_src = cfg.resolve_gemini_key(conf)
    if not api_key:
        raise RuntimeError(f"No Gemini API key found in secrets/.env (tried {key_src})")
    print(f"LLM key: {key_src}")

    recs = tstore.load_recent(n, since_iso=since)
    if not recs:
        print("No stored transcripts to build a primer from.")
        return {"concepts": 0, "clusters": 0, "emailed": 0}
    items = [tstore.as_item(r) for r in recs]
    print(f"Building primer from {len(items)} stored transcript(s):")
    for it in items:
        print(f"  · {it.producer}: {it.title[:58]}")

    # ── Stage 1: per-video concept extraction (small prompt each) ────────────
    # Cached per video: extraction is deterministic, so only NEW transcripts cost
    # an LLM call. This is what makes a wide window affordable, and a wide window
    # is what produces convergence (measured: 24 converging ideas at 136 videos
    # vs 1 at 30).
    all_concepts: list[dict] = []
    n_cached = n_fresh = 0
    for it in items:
        cs = None if refresh else conceptmod.load_cached(
            it.uid, version=conceptmod.EXTRACT_VERSION)
        if cs is None:
            cs = conceptmod.extract(it, model=model, api_key=api_key,
                                    transcript_max_chars=tmax, log=print)
            if cs:
                conceptmod.save_cached(it.uid, cs,
                                       version=conceptmod.EXTRACT_VERSION)
            n_fresh += 1
            if not cs:
                print(f"  ! no concepts extracted: {it.title[:48]}")
        else:
            n_cached += 1
        all_concepts.extend(cs)
    print(f"  extraction: {n_fresh} fresh, {n_cached} cached")
    if not all_concepts:
        raise RuntimeError("No concepts extracted from any transcript — aborting.")
    print(f"Extracted {len(all_concepts)} concepts from {len(items)} videos.")

    # ── Stage 2: cluster the same idea across videos ─────────────────────────
    clusters = conceptmod.cluster(all_concepts, model=model, api_key=api_key,
                                  log=print)
    print(f"Clustered into {len(clusters)} distinct ideas.")

    # ── Stage 3: link to the ledger (prevents fake-novelty from key drift) ───
    corpus = Corpus(cfg.corpus_path())
    known_all = corpus.known_concepts(limit=100000)
    clusters = conceptmod.link_all(
        clusters, lambda tp: corpus.known_concepts(limit=2000, topic=tp),
        model=model, api_key=api_key, log=print)
    n_matched = sum(1 for c in clusters if c.get("matched_existing"))
    print(f"Ledger: {len(known_all)} known ideas · {n_matched} matched · "
          f"{len(clusters) - n_matched} new")

    # ── Stage 4: rank (arithmetic only — reproducible) ───────────────────────
    # history BEFORE recording this run, or this run inflates its own baseline.
    history = corpus.concept_history([c["key"] for c in clusters])
    presc = conceptmod.prescience_scores(
        corpus.first_raise_stats(converge_at=2), min_firsts=min_firsts)
    if presc:
        top = sorted(presc.items(), key=lambda kv: -kv[1])[:5]
        print("Earned prescience: " + ", ".join(f"{k} {v:.2f}" for k, v in top))
    else:
        print("Earned prescience: none yet (ledger too young) — "
              f"using {len(trusted)} trusted_sources to seed authority")
    ledger_cold = not known_all
    if ledger_cold:
        print("  ledger is COLD (no prior runs) — novelty + pioneer credit "
              "withheld this run; ranking on sources/impact only")
    ranked = conceptmod.rank(clusters, all_concepts, history, weights=weights,
                             trusted=trusted, prescience=presc,
                             converge_at=converge_at, ledger_cold=ledger_cold)
    lanes = {}
    for c in ranked:
        lanes[c["lane"]] = lanes.get(c["lane"], 0) + 1
    print("Lanes: " + ", ".join(f"{k}={v}" for k, v in sorted(lanes.items())))

    # ── Stage 5: compose + render (word cap enforced in code) ────────────────
    date_label = datetime.now().strftime("%a %Y-%m-%d")
    p = primermod.compose(ranked, model=model, api_key=api_key,
                          date_label=date_label, n_headlines=n_head,
                          n_dives=n_dives, max_words=max_words)
    if not p:
        raise RuntimeError("Primer composition produced nothing.")
    md = primermod.render_markdown(p, date_label=date_label)
    read_min = max(1, round(p["words"] / 220))
    print(f"Primer: {p['words']} words (~{read_min} min, cap {max_words})"
          + (" [trimmed to fit]" if p["trimmed"] else ""))

    if dry_run:
        print("\n" + md)
        return {"concepts": len(all_concepts), "clusters": len(ranked),
                "emailed": 0, "words": p["words"], "dry_run": True}

    if save:
        out = cfg.digests_dir() / f"{datetime.now().strftime('%y%m%d-%H%M')}-primer.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md)
        print(f"saved: {out}")
    if recipient and not no_email:
        html = primermod.render_html(p, date_label=date_label)
        ok, msg = send_email(recipient, f"⚡ AI Primer — {date_label}", html,
                             html=True)
        print(f"email → {recipient}: {'sent' if ok else 'FAILED — ' + msg}")
    written = corpus.record_concepts(ranked, datetime.now(timezone.utc)
                                    .isoformat(timespec="seconds"))
    print(f"ledger: +{written} mentions · {corpus.concept_stats()}")
    return {"concepts": len(all_concepts), "clusters": len(ranked),
            "emailed": 1 if (recipient and not no_email) else 0,
            "words": p["words"]}


def cmd_primer(args) -> int:
    try:
        run_primer(dry_run=args.dry_run, no_email=args.no_email, n=args.n,
                   since=args.since, model=args.model, refresh=args.refresh)
        return 0
    except (RuntimeError, FileNotFoundError, primermod.PrimerError) as e:
        return _err(str(e))


def cmd_learn(args) -> int:
    try:
        run_learn(dry_run=args.dry_run, no_email=args.no_email, limit=args.limit,
                  model=args.model, force=args.force)
        return 0
    except (RuntimeError, FileNotFoundError) as e:
        return _err(str(e))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="digest", description="Novelty-scored AI content digest")
    p.add_argument("--version", action="version", version=f"ai-digest {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="scaffold config + seed channels")
    pi.add_argument("--force", action="store_true", help="overwrite existing config")
    pi.set_defaults(func=cmd_init)

    pc = sub.add_parser("channels", help="list configured channels")
    pc.add_argument("--list", action="store_true")
    pc.set_defaults(func=cmd_channels)

    pp = sub.add_parser("poll", help="run the ingest->score->digest->email pipeline")
    pp.add_argument("--dry-run", action="store_true", help="score+print, no email, no corpus write")
    pp.add_argument("--no-email", action="store_true", help="write digest file but don't email")
    pp.add_argument("--limit", type=int, default=None, help="only poll the first N channels")
    pp.add_argument("--model", default=None, help="override scoring model")
    pp.add_argument("--force", action="store_true", help="ignore the block cooldown and poll anyway")
    pp.set_defaults(func=cmd_poll)

    pd = sub.add_parser("doctor", help="health check (offline; --probe = 1 live request)")
    pd.add_argument("--probe", action="store_true", help="make ONE transcript request to check block status")
    pd.set_defaults(func=cmd_doctor)

    ps = sub.add_parser("stats", help="corpus counts")
    ps.set_defaults(func=cmd_stats)

    pf = sub.add_parser("forget", help="remove seen items matching a keyword so they can resurface")
    pf.add_argument("keyword", help="substring matched (case-insensitive) against title or channel")
    pf.set_defaults(func=cmd_forget)

    pr = sub.add_parser("reset", help="clear the seen-set for a one-time clean-slate rerun")
    pr.add_argument("--seen", action="store_true", help="clear the seen-set + last-run (required scope)")
    pr.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    pr.set_defaults(func=cmd_reset)

    pe = sub.add_parser("export", help="print the most recent digest")
    pe.set_defaults(func=cmd_export)

    pl = sub.add_parser("learn", help="summarize new videos in your learnings playlists (1 email/video)")
    pl.add_argument("--dry-run", action="store_true", help="list + summarize to stdout, no email, no seen-write")
    pl.add_argument("--no-email", action="store_true")
    pl.add_argument("--limit", type=int, default=None, help="cap videos this run")
    pl.add_argument("--model", default=None)
    pl.add_argument("--force", action="store_true", help="ignore the block cooldown")
    pl.set_defaults(func=cmd_learn)

    pm = sub.add_parser("primer",
                        help="concept-level rapid primer over recent transcripts "
                             "(<=5 min read; no network)")
    pm.add_argument("--dry-run", action="store_true",
                    help="print the primer, no email, no ledger write")
    pm.add_argument("--no-email", action="store_true",
                    help="save + record but don't email")
    pm.add_argument("-n", type=int, default=12,
                    help="how many recent stored transcripts to draw from")
    pm.add_argument("--since", default=None,
                    help="only transcripts fetched on/after this ISO stamp")
    pm.add_argument("--model", default=None)
    pm.add_argument("--refresh", action="store_true",
                    help="ignore the concept cache and re-extract every video")
    pm.set_defaults(func=cmd_primer)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
