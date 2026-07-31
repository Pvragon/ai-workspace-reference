"""Offline unit tests for the concept ledger + primer ranking. No network.

These cover the parts that must be deterministic and auditable: the ranking
arithmetic, the two-lane split, ledger novelty/velocity accounting, earned
prescience, and the code-enforced word budget. The LLM boundaries (extract /
cluster / link / compose) are exercised separately against real transcripts.
"""
from ai_digest import concepts as cm
from ai_digest import primer as pm
from ai_digest.corpus import Corpus


def _c(label, producer, uid, impact=5, statement="s", topic="agent-tooling"):
    return {"label": label, "statement": statement, "kind": "technique",
            "topic": topic, "specifics": [], "impact": impact,
            "impact_reason": "", "uid": uid, "producer": producer, "title": "t",
            "url": "http://x/" + uid}


# --- ranking: the load-bearing behaviour ------------------------------------

def test_trusted_solo_pioneer_outranks_converging_crowd():
    """A trusted creator alone with a NEW idea must beat a confirmed trend.

    This is the whole point of the `pioneer` axis: a pure source-diversity score
    buries early single-source insight, which is the most valuable signal in the
    feed when it is right.
    """
    concepts = [
        _c("idea a", "Crowd1", "u1", impact=8),
        _c("idea a", "Crowd2", "u2", impact=8),
        _c("idea a", "Crowd3", "u3", impact=8),
        _c("idea b", "IndyDevDan", "u4", impact=8),
    ]
    clusters = [
        {"key": "idea-a", "label": "idea a", "members": [0, 1, 2]},
        {"key": "idea-b", "label": "idea b", "members": [3]},
    ]
    history = {"idea-a": {"prior_mentions": 4, "first_seen": "2026-01-01"},
               "idea-b": {"prior_mentions": 0, "first_seen": None}}
    ranked = cm.rank(clusters, concepts, history,
                     trusted={"IndyDevDan"}, converge_at=3)
    assert ranked[0]["key"] == "idea-b", "solo trusted pioneer should rank first"
    assert ranked[0]["lane"] == cm.LANE_EARLY
    assert ranked[1]["lane"] == cm.LANE_CONVERGING
    assert ranked[0]["pioneer"] == 1.0


def test_untrusted_solo_is_not_promoted_as_pioneer():
    """A lone voice with no track record stays in the noise lane."""
    concepts = [_c("idea x", "RandomChannel", "u1", impact=5)]
    clusters = [{"key": "idea-x", "label": "idea x", "members": [0]}]
    history = {"idea-x": {"prior_mentions": 0, "first_seen": None}}
    ranked = cm.rank(clusters, concepts, history, trusted=set(), converge_at=3)
    assert ranked[0]["lane"] == cm.LANE_SINGLE
    assert ranked[0]["pioneer"] == 0.0


def test_pioneer_requires_novelty_not_just_authority():
    """Authority alone is not pioneering — a trusted source repeating an old
    idea gets no pioneer credit, or every mention by a favourite would rank."""
    concepts = [_c("old idea", "IndyDevDan", "u1", impact=7)]
    clusters = [{"key": "old-idea", "label": "old idea", "members": [0]}]
    history = {"old-idea": {"prior_mentions": 6, "first_seen": "2026-01-01"}}
    ranked = cm.rank(clusters, concepts, history,
                     trusted={"IndyDevDan"}, converge_at=3)
    assert ranked[0]["pioneer"] == 0.0
    assert ranked[0]["is_new"] is False


def test_velocity_uses_prior_baseline_only():
    concepts = [_c("i", "A", "u1"), _c("i", "B", "u2")]
    clusters = [{"key": "i", "label": "i", "members": [0, 1]}]
    ranked = cm.rank(clusters, concepts,
                     {"i": {"prior_mentions": 1, "first_seen": "2026-01-01"}})
    assert ranked[0]["velocity"] == 2.0          # 2 now vs 1 before
    assert ranked[0]["n_sources"] == 2


# --- prescience -------------------------------------------------------------

def test_prescience_requires_a_volume_floor():
    """One lucky early call must not mint permanent authority."""
    stats = {"Lucky": {"firsts": 1, "corroborated": 1},
             "Proven": {"firsts": 4, "corroborated": 3}}
    out = cm.prescience_scores(stats, min_firsts=3)
    assert "Lucky" not in out
    assert out["Proven"] == 0.75


def test_earned_prescience_grants_authority_without_trust_list():
    assert cm.authority("X", set(), {"X": 0.8}) == 0.8
    assert cm.authority("X", {"X"}, {}) == 1.0
    assert cm.authority("Y", set(), {}) == 0.0


# --- ledger ----------------------------------------------------------------

def test_ledger_roundtrip_novelty_and_idempotency(tmp_path):
    c = Corpus(tmp_path / "c.db")
    ranked = [{"key": "k1", "label": "idea one",
               "concepts": [_c("idea one", "A", "u1"), _c("idea one", "B", "u2")]}]
    assert c.concept_history(["k1"])["k1"]["prior_mentions"] == 0   # unseen
    n = c.record_concepts(ranked, "2026-07-01T00:00:00+00:00")
    assert n == 2
    h = c.concept_history(["k1"])["k1"]
    assert h["prior_mentions"] == 2 and h["first_seen"].startswith("2026-07-01")

    # Re-recording the same (key, uid) pairs must not inflate the trend.
    again = c.record_concepts(ranked, "2026-07-02T00:00:00+00:00")
    assert again == 0
    assert c.concept_history(["k1"])["k1"]["prior_mentions"] == 2
    # first_seen must not drift forward on re-record
    assert c.concept_history(["k1"])["k1"]["first_seen"].startswith("2026-07-01")


def test_first_raise_stats_credits_the_earliest_producer(tmp_path):
    c = Corpus(tmp_path / "c.db")
    c.record_concepts([{"key": "k", "label": "l",
                        "concepts": [_c("l", "Early", "u1")]}],
                      "2026-07-01T00:00:00+00:00")
    c.record_concepts([{"key": "k", "label": "l",
                        "concepts": [_c("l", "Later", "u2")]}],
                      "2026-07-08T00:00:00+00:00")
    stats = c.first_raise_stats(converge_at=2)
    assert stats["Early"]["firsts"] == 1
    assert stats["Early"]["corroborated"] == 1     # Later picked it up
    assert "Later" not in stats                    # never a first-raiser


def test_uncorroborated_first_is_not_counted_as_right(tmp_path):
    c = Corpus(tmp_path / "c.db")
    c.record_concepts([{"key": "k", "label": "l",
                        "concepts": [_c("l", "Solo", "u1")]}],
                      "2026-07-01T00:00:00+00:00")
    stats = c.first_raise_stats(converge_at=2)
    assert stats["Solo"] == {"firsts": 1, "corroborated": 0}


# --- clustering safety ------------------------------------------------------

def test_cluster_never_silently_drops_a_concept(monkeypatch):
    """A model reply that forgets some indices must not lose those concepts."""
    concepts = [_c(f"i{i}", "P", f"u{i}") for i in range(4)]
    monkeypatch.setattr(cm, "generate_json",
                        lambda *a, **k: {"clusters": [{"label": "g", "members": [0, 1]}]})
    out = cm.cluster(concepts, model="m", api_key="k")
    covered = sorted(i for cl in out for i in cl["members"])
    assert covered == [0, 1, 2, 3]


def test_cluster_ignores_out_of_range_and_duplicate_indices(monkeypatch):
    concepts = [_c("i0", "P", "u0"), _c("i1", "P", "u1")]
    monkeypatch.setattr(cm, "generate_json", lambda *a, **k: {"clusters": [
        {"label": "g", "members": [0, 0, 99, -3]}]})
    out = cm.cluster(concepts, model="m", api_key="k")
    covered = sorted(i for cl in out for i in cl["members"])
    assert covered == [0, 1]


def test_link_never_invents_a_ledger_key(monkeypatch):
    clusters = [{"label": "a", "members": [0]}]
    monkeypatch.setattr(cm, "generate_json", lambda *a, **k: {
        "links": [{"cluster": 0, "existing_key": "not-in-ledger"}]})
    out = cm.link(clusters, [{"key": "real-key", "label": "real"}],
                  model="m", api_key="k")
    assert out[0]["key"] != "not-in-ledger"


def test_link_reuses_existing_key_to_prevent_fake_novelty(monkeypatch):
    clusters = [{"label": "agents approve prs", "members": [0]}]
    monkeypatch.setattr(cm, "generate_json", lambda *a, **k: {
        "links": [{"cluster": 0, "existing_key": "agent-self-approval"}]})
    out = cm.link(clusters, [{"key": "agent-self-approval", "label": "x"}],
                  model="m", api_key="k")
    assert out[0]["key"] == "agent-self-approval"
    assert out[0]["matched_existing"] is True


# --- word budget ------------------------------------------------------------

def test_budget_drops_lowest_ranked_dives_and_keeps_the_scan():
    heads = [{"key": f"k{i}", "text": "word " * 10} for i in range(5)]     # 50
    dives = [{"key": f"k{i}", "title": "t", "what": "word " * 100,
              "why": "word " * 20} for i in range(4)]                      # ~484
    h, d, trimmed = pm._enforce_budget(heads, dives, max_words=200)
    assert trimmed is True
    assert len(h) == 5, "headlines (the 30-second scan) must survive"
    assert len(d) < 4


def test_budget_leaves_a_short_primer_untouched():
    heads = [{"key": "k", "text": "a b c"}]
    dives = [{"key": "k", "title": "t", "what": "a b", "why": "c"}]
    h, d, trimmed = pm._enforce_budget(heads, dives, max_words=1000)
    assert trimmed is False and len(h) == 1 and len(d) == 1


# --- regressions ------------------------------------------------------------

def test_velocity_counts_videos_not_concept_rows():
    """One video phrasing the same idea four ways is ONE mention.

    Regression: ranking originally counted concept rows, so a single talkative
    video inflated velocity 4x and manufactured a fake trend.
    """
    concepts = [_c("i", "Solo", "same-uid") for _ in range(4)]
    clusters = [{"key": "i", "label": "i", "members": [0, 1, 2, 3]}]
    ranked = cm.rank(clusters, concepts,
                     {"i": {"prior_mentions": 1, "first_seen": "2026-01-01"}})
    assert ranked[0]["n_mentions"] == 1
    assert ranked[0]["velocity"] == 1.0
    assert ranked[0]["n_sources"] == 1


def test_source_links_dedupe_by_video():
    cl = {"concepts": [
        {"uid": "u1", "producer": "A", "url": "http://a"},
        {"uid": "u1", "producer": "A", "url": "http://a"},
        {"uid": "u2", "producer": "B", "url": "http://b"},
    ]}
    assert [m["uid"] for m in pm._sources(cl)] == ["u1", "u2"]


def test_cold_ledger_withholds_novelty_and_pioneer_credit():
    """With no history, everything looks new — so novelty/pioneer must not fire.

    Otherwise run #1 ranks purely on "which of my trusted channels talked", which
    is what the first real run actually produced before this guard.
    """
    concepts = [_c("a", "IndyDevDan", "u1", impact=5),
                _c("b", "Crowd1", "u2", impact=9),
                _c("b", "Crowd2", "u3", impact=9)]
    clusters = [{"key": "a", "label": "a", "members": [0]},
                {"key": "b", "label": "b", "members": [1, 2]}]
    history = {"a": {"prior_mentions": 0, "first_seen": None},
               "b": {"prior_mentions": 0, "first_seen": None}}
    ranked = cm.rank(clusters, concepts, history, trusted={"IndyDevDan"},
                     converge_at=3, ledger_cold=True)
    assert all(c["pioneer"] == 0.0 for c in ranked)
    # high-impact, multi-source idea should now win on merit
    assert ranked[0]["key"] == "b"


# --- bucketed clustering ----------------------------------------------------

def test_cluster_buckets_by_topic_and_maps_indices_back(monkeypatch):
    """Local->global index mapping must be exact.

    The model sees per-bucket numbering 0..n-1; a mapping bug would attribute an
    idea to the wrong video and silently corrupt every downstream trend metric.
    """
    concepts = [
        _c("a", "P1", "u1", topic="agent-autonomy"),
        _c("b", "P2", "u2", topic="model-efficiency"),
        _c("a again", "P3", "u3", topic="agent-autonomy"),
    ]
    calls = []

    def fake(prompt, **kw):
        calls.append(prompt)
        # merge the two locals in whichever bucket has 2 members
        return {"clusters": [{"label": "merged", "members": [0, 1]}]}

    monkeypatch.setattr(cm, "generate_json", fake)
    out = cm.cluster(concepts, model="m", api_key="k")
    assert len(calls) == 1, "only the 2-member bucket needs an LLM call"
    merged = [c for c in out if c["label"] == "merged"][0]
    # global indices 0 and 2 are the agent-autonomy pair — NOT 0 and 1
    assert sorted(merged["members"]) == [0, 2]
    assert merged["topic"] == "agent-autonomy"
    solo = [c for c in out if c["topic"] == "model-efficiency"][0]
    assert solo["members"] == [1]


def test_cluster_covers_every_concept_across_buckets(monkeypatch):
    concepts = [_c(f"i{i}", f"P{i}", f"u{i}",
                   topic="agent-autonomy" if i < 3 else "gtm-marketing")
                for i in range(6)]
    monkeypatch.setattr(cm, "generate_json",
                        lambda *a, **k: {"clusters": [{"label": "g",
                                                       "members": [0]}]})
    out = cm.cluster(concepts, model="m", api_key="k")
    covered = sorted(i for cl in out for i in cl["members"])
    assert covered == [0, 1, 2, 3, 4, 5]


def test_single_member_bucket_needs_no_llm_call(monkeypatch):
    concepts = [_c("a", "P", "u1", topic="voice-multimodal")]
    called = []
    monkeypatch.setattr(cm, "generate_json",
                        lambda *a, **k: called.append(1) or {"clusters": []})
    out = cm.cluster(concepts, model="m", api_key="k")
    assert called == [] and out[0]["members"] == [0]


def test_bucket_failure_is_isolated(monkeypatch):
    """One bucket's LLM failure must not cost the other bucket its clustering."""
    concepts = [
        _c("a", "P1", "u1", topic="agent-autonomy"),
        _c("a2", "P2", "u2", topic="agent-autonomy"),
        _c("b", "P3", "u3", topic="gtm-marketing"),
        _c("b2", "P4", "u4", topic="gtm-marketing"),
    ]

    def fake(prompt, **kw):
        if "agent-autonomy" in prompt:
            raise cm.GeminiError("boom")
        return {"clusters": [{"label": "gtm merged", "members": [0, 1]}]}

    monkeypatch.setattr(cm, "generate_json", fake)
    out = cm.cluster(concepts, model="m", api_key="k")
    assert any(c["label"] == "gtm merged" and sorted(c["members"]) == [2, 3]
               for c in out)
    assert sum(1 for c in out if c["topic"] == "agent-autonomy") == 2


def test_unknown_topic_from_model_is_coerced(monkeypatch):
    from ai_digest.record import Item
    monkeypatch.setattr(cm, "generate_json", lambda *a, **k: {"concepts": [
        {"label": "l", "statement": "s", "kind": "technique",
         "topic": "made-up-bucket", "impact": 5}]})
    out = cm.extract(Item(uid="u", source="youtube", producer="P", title="t",
                          url="x", text="body"), model="m", api_key="k")
    assert out[0]["topic"] == "other"


def test_tag_credits_the_authoritative_producer_not_the_alphabetical_first():
    """Regression: `producers` is sorted, so the tag used to credit whichever
    name sorted first — misattributing the call to the wrong creator — and hid
    any corroborating source entirely."""
    concepts = [_c("i", "Zeta Channel", "u1", topic="agent-autonomy"),
                _c("i", "AAA Channel", "u2", topic="agent-autonomy")]
    clusters = [{"key": "i", "label": "i", "members": [0, 1]}]
    ranked = cm.rank(clusters, concepts,
                     {"i": {"prior_mentions": 0, "first_seen": None}},
                     trusted={"Zeta Channel"}, converge_at=3)
    cl = ranked[0]
    assert cl["top_producer"] == "Zeta Channel"       # not "AAA Channel"
    tag = pm._tag(cl)
    assert "Zeta Channel" in tag and "+1" in tag      # second source disclosed


# --- extraction cache -------------------------------------------------------

def test_concept_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    importlib.reload(cm)
    assert cm.load_cached("youtube:abc", version=1) is None
    cm.save_cached("youtube:abc", [{"label": "x"}], version=1)
    assert cm.load_cached("youtube:abc", version=1) == [{"label": "x"}]


def test_cache_version_bump_invalidates(tmp_path, monkeypatch):
    """Changing the extraction prompt must not silently serve concepts
    extracted under the OLD rules."""
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    importlib.reload(cm)
    cm.save_cached("youtube:abc", [{"label": "old"}], version=1)
    assert cm.load_cached("youtube:abc", version=2) is None


def test_corrupt_cache_entry_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DIGEST_CONFIG_DIR", str(tmp_path))
    import importlib
    from ai_digest import config as cfg
    importlib.reload(cfg)
    importlib.reload(cm)
    p = cm.cache_path("youtube:abc")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json")
    assert cm.load_cached("youtube:abc") is None


def test_link_all_scopes_ledger_lookup_to_the_clusters_topic(monkeypatch):
    """Each bucket must be linked against ITS OWN ledger slice.

    A flat global cap drops older ideas out of the prompt, and anything the
    linker cannot see comes back NEW — manufacturing novelty.
    """
    clusters = [{"label": "a", "members": [0], "topic": "agent-autonomy"},
                {"label": "b", "members": [1], "topic": "gtm-marketing"}]
    asked = []

    def known_for(topic):
        asked.append(topic)
        return [{"key": f"{topic}-key", "label": "known"}]

    monkeypatch.setattr(cm, "generate_json", lambda *a, **k: {
        "links": [{"cluster": 0, "existing_key": "agent-autonomy-key"}]})
    out = cm.link_all(clusters, known_for, model="m", api_key="k")
    assert sorted(asked) == ["agent-autonomy", "gtm-marketing"]
    assert len(out) == 2
    # the linker only ever sees keys from its own topic
    assert all(c["key"].startswith(c["topic"]) or not c["matched_existing"]
               for c in out)


# --- end-to-end ledger cycle ------------------------------------------------

def test_two_run_cycle_turns_new_into_recurring(tmp_path, monkeypatch):
    """The behaviour the whole ledger exists for, exercised offline.

    Run 1 on a cold ledger: nothing may claim novelty. Run 2 with the same idea
    re-linked to its existing key: it is no longer NEW, has a real prior baseline,
    and velocity is computed against that baseline rather than against nothing.
    """
    c = Corpus(tmp_path / "c.db")
    concepts1 = [_c("agents self-approve", "A", "u1", topic="agent-autonomy")]
    clusters1 = [{"key": "agents-self-approve", "label": "agents self-approve",
                  "members": [0], "topic": "agent-autonomy"}]

    known = c.known_concepts()
    assert known == []                                   # cold
    hist1 = c.concept_history([cl["key"] for cl in clusters1])
    ranked1 = cm.rank(clusters1, concepts1, hist1, ledger_cold=not known)
    assert ranked1[0]["pioneer"] == 0.0                  # no novelty on a cold ledger
    c.record_concepts(ranked1, "2026-07-01T00:00:00+00:00")

    # --- run 2: two more creators pick the same idea up -------------------
    concepts2 = [_c("agents self-approve", "B", "u2", topic="agent-autonomy"),
                 _c("agents self-approve", "C", "u3", topic="agent-autonomy")]
    clusters2 = [{"label": "agents approving their own changes",
                  "members": [0, 1], "topic": "agent-autonomy"}]
    known2 = c.known_concepts(topic="agent-autonomy")
    assert [k["key"] for k in known2] == ["agents-self-approve"]

    # linker re-identifies the renamed cluster as the SAME ledger idea
    monkeypatch.setattr(cm, "generate_json", lambda *a, **k: {
        "links": [{"cluster": 0, "existing_key": "agents-self-approve"}]})
    linked = cm.link_all(clusters2, lambda tp: known2, model="m", api_key="k")
    assert linked[0]["key"] == "agents-self-approve", "must reuse the ledger key"

    hist2 = c.concept_history([cl["key"] for cl in linked])
    assert hist2["agents-self-approve"]["prior_mentions"] == 1
    ranked2 = cm.rank(linked, concepts2, hist2, ledger_cold=False, converge_at=3)
    assert ranked2[0]["is_new"] is False, "a re-linked idea is not new"
    assert ranked2[0]["prior_mentions"] == 1
    assert ranked2[0]["velocity"] == 2.0                 # 2 videos now vs 1 before

    c.record_concepts(ranked2, "2026-07-08T00:00:00+00:00")
    # first-raiser credit goes to A, and it was corroborated by B and C
    stats = c.first_raise_stats(converge_at=2)
    assert stats["A"] == {"firsts": 1, "corroborated": 1}
    assert c.concept_stats() == {"concepts": 1, "mentions": 3}


def test_cold_ledger_does_not_assert_novelty_in_the_output():
    """`NEW` on a cold ledger is an unverifiable claim.

    Ranking already withheld novelty CREDIT when cold, but the rendered tag still
    said NEW — so the very first primer labelled all 546 ideas new. Novelty is now
    reported as unknown rather than asserted.
    """
    concepts = [_c("a", "P", "u1")]
    clusters = [{"key": "a", "label": "a", "members": [0]}]
    hist = {"a": {"prior_mentions": 0, "first_seen": None}}
    cold = cm.rank(clusters, concepts, hist, ledger_cold=True)[0]
    assert cold["is_new"] is False and cold["novelty_known"] is False
    assert "NEW" not in pm._tag(cold)
    warm = cm.rank(clusters, concepts, hist, ledger_cold=False)[0]
    assert warm["is_new"] is True and "NEW" in pm._tag(warm)


def test_pre_migration_ledger_rows_stay_linkable(tmp_path):
    """Rows written before the topic column existed carry NULL.

    Excluding them from topic-scoped lookups un-links the entire pre-migration
    ledger — measured live: 546 known ideas matched 0, every cluster came back
    "new", which is the fake novelty this step exists to prevent.
    """
    import sqlite3
    c = Corpus(tmp_path / "c.db")
    c.record_concepts([{"key": "k", "label": "legacy", "topic": "agent-autonomy",
                        "concepts": [_c("legacy", "A", "u1")]}],
                      "2026-07-01T00:00:00+00:00")
    # simulate a row written before the migration
    con = sqlite3.connect(tmp_path / "c.db")
    con.execute("UPDATE concepts SET topic = NULL"); con.commit(); con.close()

    assert [k["key"] for k in c.known_concepts(topic="agent-autonomy")] == ["k"]
    assert [k["key"] for k in c.known_concepts(topic="gtm-marketing")] == ["k"]
    assert len(c.known_concepts()) == 1
