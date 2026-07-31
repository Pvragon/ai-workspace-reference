"""SQLite corpus — new-item detection + rolling-corpus baseline.

Two jobs:
  1. Dedupe: ``seen(uid)`` tells the adapter which items are new since last run.
  2. Rolling baseline: ``recent_context(n)`` returns the last N digested items
     (title + one-line novelty reason) so the judge can score "did we already
     cover this three weeks ago?" against real history.

Rejected items are persisted too (so the same low-novelty video isn't re-judged
every poll), but only passes carry ``digested_at`` and feed the rolling context.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .record import Item, Verdict

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    uid           TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    producer      TEXT,
    title         TEXT,
    url           TEXT,
    published     TEXT,
    fetched_at    TEXT,            -- ISO; when we first saw it
    score         INTEGER,
    passed        INTEGER,         -- 0/1
    reason        TEXT,
    summary       TEXT,            -- <=50-word content summary
    key_points    TEXT,            -- json
    dimensions    TEXT,            -- json
    digested_at   TEXT             -- ISO; set only when included in a sent digest
);
CREATE INDEX IF NOT EXISTS idx_items_digested ON items(digested_at);
CREATE TABLE IF NOT EXISTS runs (
    source        TEXT PRIMARY KEY,
    last_run_ts   TEXT             -- ISO (UTC); when this source was last polled
);
CREATE TABLE IF NOT EXISTS state (
    key           TEXT PRIMARY KEY,
    value         TEXT
);
-- Concept ledger (see ai_digest.concepts). `concepts` is the identity table:
-- one row per idea ever tracked, so `first_seen` gives real novelty rather than
-- "the LLM phrased it differently this week". `concept_mentions` is the evidence
-- log: one row per (idea, video), which is what makes source-diversity,
-- velocity and per-producer track record computable arithmetic instead of vibes.
CREATE TABLE IF NOT EXISTS concepts (
    key           TEXT PRIMARY KEY,
    label         TEXT,
    topic         TEXT,            -- concepts.TOPICS bucket; scopes ledger linking
    first_seen    TEXT,            -- ISO; first run this idea ever appeared
    last_seen     TEXT
);
CREATE TABLE IF NOT EXISTS concept_mentions (
    key           TEXT NOT NULL,
    uid           TEXT NOT NULL,   -- the item that mentioned it
    producer      TEXT,
    ts            TEXT,            -- ISO run stamp
    statement     TEXT,
    impact        INTEGER,
    PRIMARY KEY (key, uid)
);
CREATE INDEX IF NOT EXISTS idx_cm_key ON concept_mentions(key);
CREATE INDEX IF NOT EXISTS idx_cm_ts  ON concept_mentions(ts);
CREATE INDEX IF NOT EXISTS idx_cm_prod ON concept_mentions(producer);
"""


def _safe_dt(s):
    """Parse an ISO stamp to a NAIVE datetime (tzinfo stripped) so naive and
    tz-aware stamps in the same tx_log can be compared without a TypeError."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


@contextmanager
def _conn(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    try:
        c.executescript(_SCHEMA)
        # migrate older DBs that predate the summary column
        cols = {r[1] for r in c.execute("PRAGMA table_info(items)")}
        if "summary" not in cols:
            c.execute("ALTER TABLE items ADD COLUMN summary TEXT")
        # migrate ledgers created before topic-scoped linking
        ccols = {r[1] for r in c.execute("PRAGMA table_info(concepts)")}
        if ccols and "topic" not in ccols:
            c.execute("ALTER TABLE concepts ADD COLUMN topic TEXT")
        yield c
        c.commit()
    finally:
        c.close()


class Corpus:
    def __init__(self, path: Path):
        self.path = path

    def seen(self, uid: str) -> bool:
        with _conn(self.path) as c:
            return c.execute("SELECT 1 FROM items WHERE uid=?", (uid,)).fetchone() is not None

    def filter_new(self, items: list[Item]) -> list[Item]:
        if not items:
            return []
        with _conn(self.path) as c:
            have = {r["uid"] for r in c.execute("SELECT uid FROM items")}
        return [it for it in items if it.uid not in have]

    def record(self, item: Item, verdict: Verdict, now_iso: str, digested: bool) -> None:
        with _conn(self.path) as c:
            c.execute(
                """INSERT OR REPLACE INTO items
                   (uid,source,producer,title,url,published,fetched_at,
                    score,passed,reason,summary,key_points,dimensions,digested_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (item.uid, item.source, item.producer, item.title, item.url,
                 item.published, now_iso, verdict.score, int(verdict.passed),
                 verdict.reason, verdict.summary, json.dumps(verdict.key_points),
                 json.dumps(verdict.dimensions),
                 now_iso if digested else None),
            )

    def mark_seen(self, cand: dict, reason: str, now_iso: str) -> None:
        """Record a candidate we did NOT transcript (title-dropped / out-of-window /
        no-captions) so it is never re-scanned. score/passed left null-ish."""
        with _conn(self.path) as c:
            c.execute(
                """INSERT OR REPLACE INTO items
                   (uid,source,producer,title,url,fetched_at,score,passed,reason,digested_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (cand["uid"], cand.get("source", "youtube"), cand.get("producer"),
                 cand.get("title"), cand.get("url"), now_iso, None, 0, reason, None))

    def recent_context(self, n: int) -> list[dict]:
        """Last N digested (passed) items, newest first — for the judge baseline."""
        with _conn(self.path) as c:
            rows = c.execute(
                """SELECT title, producer, reason, score FROM items
                   WHERE digested_at IS NOT NULL
                   ORDER BY digested_at DESC LIMIT ?""", (n,)).fetchall()
        return [dict(r) for r in rows]

    def get_last_run(self, source: str) -> Optional[str]:
        with _conn(self.path) as c:
            r = c.execute("SELECT last_run_ts FROM runs WHERE source=?", (source,)).fetchone()
        return r["last_run_ts"] if r else None

    def set_last_run(self, source: str, ts_iso: str) -> None:
        with _conn(self.path) as c:
            c.execute("INSERT OR REPLACE INTO runs (source,last_run_ts) VALUES (?,?)",
                      (source, ts_iso))

    def get_state(self, key: str) -> Optional[str]:
        with _conn(self.path) as c:
            r = c.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def set_state(self, key: str, value: Optional[str]) -> None:
        with _conn(self.path) as c:
            if value is None:
                c.execute("DELETE FROM state WHERE key=?", (key,))
            else:
                c.execute("INSERT OR REPLACE INTO state (key,value) VALUES (?,?)", (key, value))

    def transcripts_in_window(self, now_iso: str, hours: float) -> int:
        """Count transcript requests logged in the trailing ``hours`` (pruning
        anything older than 24h). Persisted across poll invocations so repeated
        runs can't burst into a block — the proactive complement to abort-on-block.
        Rate-limit primary window is hourly; 24h is a backstop + prune horizon."""
        import json as _json
        from datetime import datetime, timedelta
        now = _safe_dt(now_iso) or datetime.now()          # naive, tz-consistent with stamps
        raw = self.get_state("tx_log")
        stamps = _json.loads(raw) if raw else []
        prune = now - timedelta(hours=24)
        stamps = [s for s in stamps if _safe_dt(s) and _safe_dt(s) >= prune]
        self.set_state("tx_log", _json.dumps(stamps))
        window = now - timedelta(hours=hours)
        return sum(1 for s in stamps if _safe_dt(s) >= window)

    def transcripts_last_24h(self, now_iso: str) -> int:
        return self.transcripts_in_window(now_iso, 24)

    def log_transcripts(self, n: int, now_iso: str) -> None:
        """Record ``n`` transcript requests at now (for the rolling-24h limiter)."""
        if n <= 0:
            return
        import json as _json
        raw = self.get_state("tx_log")
        stamps = _json.loads(raw) if raw else []
        stamps.extend([now_iso] * n)
        self.set_state("tx_log", _json.dumps(stamps))

    def forget(self, keyword: str) -> list[dict]:
        """Delete seen rows whose title OR producer contains ``keyword`` (case-
        insensitive) so a skipped/off-topic video can resurface on the next poll.
        Returns the rows removed (for the caller to report)."""
        kw = f"%{keyword.lower()}%"
        with _conn(self.path) as c:
            rows = c.execute(
                "SELECT uid,title,producer FROM items "
                "WHERE lower(title) LIKE ? OR lower(producer) LIKE ?", (kw, kw)).fetchall()
            c.execute("DELETE FROM items WHERE lower(title) LIKE ? OR lower(producer) LIKE ?",
                      (kw, kw))
        return [dict(r) for r in rows]

    def reset_seen(self) -> int:
        """Clear the entire seen-set (items table) AND last-run marks so the next
        poll re-considers all history from scratch under the current rules. Rate-
        limit state (tx_log) and cooldown are preserved. Returns rows cleared."""
        with _conn(self.path) as c:
            n = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            c.execute("DELETE FROM items")
            c.execute("DELETE FROM runs")
        return n

    def stats(self) -> dict:
        with _conn(self.path) as c:
            total = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            passed = c.execute("SELECT COUNT(*) FROM items WHERE passed=1").fetchone()[0]
        return {"total": total, "passed": passed}

    # --- concept ledger -----------------------------------------------------

    def known_concepts(self, limit: int = 400,
                       topic: str | None = None) -> list[dict]:
        """Ledger entries for LLM re-identification, most recent first.

        Fed to ``concepts.link`` so the same idea reuses its existing key instead
        of minting a new slug every run (which would make everything look NEW).

        ``topic`` scopes the lookup to one bucket. This matters as the ledger
        grows: a flat ``limit`` means older ideas drop out of the link prompt and
        resurface as fake NEW — the exact failure linking exists to prevent.
        Scoping by topic keeps each prompt small AND complete for its bucket.

        Rows written before the topic column existed carry NULL and are included
        in EVERY bucket rather than none. Excluding them silently un-links an
        entire pre-migration ledger: measured on the first real two-run test,
        546 known ideas matched 0 and all 502 clusters came back "new".
        """
        q = "SELECT key, label, topic, first_seen, last_seen FROM concepts"
        args: list = []
        if topic:
            q += " WHERE (topic = ? OR topic IS NULL)"
            args.append(topic)
        q += " ORDER BY last_seen DESC LIMIT ?"
        args.append(limit)
        with _conn(self.path) as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def concept_history(self, keys: list[str]) -> dict:
        """{key: {"prior_mentions": n, "first_seen": iso|None}} for ranking.

        ``prior_mentions`` counts mentions ALREADY on the ledger — call this
        BEFORE ``record_concepts`` for the current run, or this run's own
        mentions inflate the baseline and every velocity reads as 1.0.
        """
        if not keys:
            return {}
        out = {}
        with _conn(self.path) as c:
            qs = ",".join("?" * len(keys))
            for r in c.execute(
                    f"SELECT key, COUNT(*) n FROM concept_mentions "
                    f"WHERE key IN ({qs}) GROUP BY key", keys):
                out.setdefault(r["key"], {})["prior_mentions"] = r["n"]
            for r in c.execute(
                    f"SELECT key, first_seen FROM concepts WHERE key IN ({qs})",
                    keys):
                out.setdefault(r["key"], {})["first_seen"] = r["first_seen"]
        for k in keys:
            out.setdefault(k, {"prior_mentions": 0, "first_seen": None})
            out[k].setdefault("prior_mentions", 0)
            out[k].setdefault("first_seen", None)
        return out

    def record_concepts(self, ranked: list[dict], now_iso: str) -> int:
        """Persist this run's clusters + their per-video mentions. Idempotent per
        (key, uid), so re-running a poll cannot double-count a mention and
        silently inflate a trend. Returns mentions written."""
        n = 0
        with _conn(self.path) as c:
            for cl in ranked:
                key, label = cl.get("key"), cl.get("label", "")
                if not key:
                    continue
                row = c.execute("SELECT first_seen FROM concepts WHERE key=?",
                                (key,)).fetchone()
                topic = cl.get("topic") or "other"
                if row is None:
                    c.execute("INSERT INTO concepts "
                              "(key,label,topic,first_seen,last_seen) "
                              "VALUES (?,?,?,?,?)",
                              (key, label, topic, now_iso, now_iso))
                else:
                    c.execute("UPDATE concepts SET last_seen=?, "
                              "label=COALESCE(label,?), topic=COALESCE(topic,?) "
                              "WHERE key=?", (now_iso, label, topic, key))
                for m in cl.get("concepts", []):
                    cur = c.execute(
                        "INSERT OR IGNORE INTO concept_mentions "
                        "(key,uid,producer,ts,statement,impact) VALUES (?,?,?,?,?,?)",
                        (key, m.get("uid"), m.get("producer"), now_iso,
                         m.get("statement"), int(m.get("impact", 0) or 0)))
                    n += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        return n

    def first_raise_stats(self, converge_at: int = 2) -> dict:
        """{producer: {"firsts": n, "corroborated": n}} — earned track record.

        For each concept, whoever mentioned it earliest gets a "first". If that
        concept later reached ``converge_at`` or more DISTINCT producers, the
        first-raiser's call is counted as corroborated. Feeds
        ``concepts.prescience_scores``, which turns this into the authority that
        lets a lone high-signal creator outrank a crowd.

        Aggregated in Python rather than SQL: the mention log is small, and the
        first-raiser-at-min(ts) logic reads far more clearly this way.
        """
        with _conn(self.path) as c:
            rows = [dict(r) for r in c.execute(
                "SELECT key, producer, ts FROM concept_mentions "
                "WHERE producer IS NOT NULL AND producer != '' ORDER BY ts ASC")]
        by_key: dict[str, list[dict]] = {}
        for r in rows:
            by_key.setdefault(r["key"], []).append(r)
        out: dict[str, dict] = {}
        for key, ms in by_key.items():
            first = ms[0]["producer"]
            distinct = {m["producer"] for m in ms}
            d = out.setdefault(first, {"firsts": 0, "corroborated": 0})
            d["firsts"] += 1
            # corroborated = someone OTHER than the first-raiser picked it up
            if len(distinct) >= max(2, converge_at):
                d["corroborated"] += 1
        return out

    def concept_stats(self) -> dict:
        with _conn(self.path) as c:
            n = c.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
            m = c.execute("SELECT COUNT(*) FROM concept_mentions").fetchone()[0]
        return {"concepts": n, "mentions": m}
