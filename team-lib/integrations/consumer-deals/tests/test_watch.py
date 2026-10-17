"""`deals watch` — incremental/full polling, sold-state reclassification, the
per-query state pointer, and the notify/email sink. All offline (fake adapter)."""
import argparse

from deals import cli, config, watchstate, notify, diff
from deals.record import Listing
from deals.adapters.offerup import OfferUpAdapter


def _L(lid, price=None, title="Gaming PC", state="LISTED"):
    return Listing(listing_id=lid, site="offerup", url=f"https://offerup.com/item/detail/{lid}",
                   title=title, price=price, state=state, distance_mi=5.0,
                   posted_at="2026-06-24T10:00:00+00:00")


# ---------------------------------------------------------------- watchstate
def test_watchstate_roundtrip(tmp_path):
    k = watchstate.key("offerup", "Gaming PC", "92124")
    assert k == "offerup|gaming pc|92124"
    cat = tmp_path / "c.csv"; cat.write_text("x")
    watchstate.save(k, cat, 42)
    rec = watchstate.load(k)
    assert rec["seen_count"] == 42 and rec["last_catalog"] == str(cat)
    assert watchstate.last_catalog(k) == cat


def test_watchstate_last_catalog_missing_file(tmp_path):
    k = watchstate.key("offerup", "q", "z")
    watchstate.save(k, tmp_path / "gone.csv", 1)   # path doesn't exist
    assert watchstate.last_catalog(k) is None


# ---------------------------------------------------------------- notify
def test_format_alert_lists_new_and_drops():
    old = [_L("a", 500)]
    new = [_L("a", 400), _L("b", 250)]
    r = diff.diff_catalogs(old, new)
    subject, body = notify.format_alert(r, "Gaming PC", location="92124")
    assert "1 new" in subject and "1 price drops" in subject
    assert "NEW (1)" in body and "PRICE DROPS (1)" in body
    assert "$500->$400" in body
    assert "verify any too-good deal in person" in body


def test_send_email_soft_fails_without_gws(monkeypatch):
    monkeypatch.setattr(notify.shutil, "which", lambda _: None)
    assert notify.send_email("s", "b", "x@y.com") is False     # no raise


def test_dispatch_email_requires_recipient(capsys):
    r = diff.DiffResult(new=[_L("a", 100)])
    out = notify.dispatch(r, "q", sink="email", email_to=None)
    assert out["sent"] is False
    assert "needs --email-to" in capsys.readouterr().out


# ---------------------------------------------------------------- adapter bits
def test_search_params_includes_sort():
    p = OfferUpAdapter._search_params("pc", "92124", 40, "", sort="newest")
    assert {"key": "sort", "value": "newest"} in p
    p2 = OfferUpAdapter._search_params("pc", "92124", 40, "")
    assert not any(x["key"] == "sort" for x in p2)


def test_lookup_states_maps_and_nulls(monkeypatch):
    a = OfferUpAdapter.__new__(OfferUpAdapter)        # skip __init__/network
    a.last_throttled = False
    responses = {
        "sold1": {"data": {"listing": {"listingId": "sold1", "state": "sold"}}},
        "gone1": {"data": {"listing": None}},
    }
    monkeypatch.setattr(a, "_post", lambda op, q, v: responses[v["id"]])
    out = a.lookup_states(["sold1", "gone1"])
    assert out == {"sold1": "SOLD", "gone1": None}


# ---------------------------------------------------------------- cmd_watch
def _write_config(catalogs_dir):
    p = config.config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '[location]\nzip = "92124"\nlat = 32.8\nlon = -117.1\nname = "SD"\n'
        '[defaults]\nradius_mi = 40\nmax_age = "6mo"\nsite = "offerup"\n'
        f'[output]\ncatalogs_dir = "{catalogs_dir}"\n')


class _FakeAdapter:
    """Returns a scripted list of listings per scrape() call; canned states."""
    def __init__(self, scrapes, states=None):
        self._scrapes = list(scrapes)
        self._states = states or {}
        self.last_throttled = False

    def scrape(self, queries, radius, **kw):
        return self._scrapes.pop(0)

    def lookup_states(self, ids):
        return {i: self._states.get(i) for i in ids}


def _args(**kw):
    base = dict(site=None, query=["Gaming PC"], queries_file=None, location=None,
                radius=None, max_age=None, full=False, pages=2, pack=None,
                notify="none", email_to=None, min_drop=None, concurrency=3,
                rps=3.0, no_cache=False, exit_on_change=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _patch(monkeypatch, adapter):
    monkeypatch.setattr(cli.auth_mod, "ensure", lambda site: {})
    monkeypatch.setattr(cli, "get_adapter_cls", lambda site: (lambda *a, **k: adapter))


def test_watch_baseline_then_incremental(tmp_path, monkeypatch, capsys):
    _write_config(tmp_path / "catalogs")
    fa = _FakeAdapter(scrapes=[
        [_L("a", 500), _L("b", 300)],            # baseline
        [_L("a", 400), _L("c", 250)],            # incremental head: a dropped, c new
    ])
    _patch(monkeypatch, fa)

    assert cli.cmd_watch(_args()) == 0
    assert "baseline established: 2 listings" in capsys.readouterr().out

    assert cli.cmd_watch(_args(exit_on_change=True)) == cli.CHANGE_EXIT_CODE
    out = capsys.readouterr().out
    assert "NEW (1)" in out and "c" in out      # c surfaced as new
    assert "$500->$400" in out                  # a's drop surfaced
    assert "GONE" not in out                     # incremental never claims gone


def test_watch_full_reclassifies_gone(tmp_path, monkeypatch, capsys):
    _write_config(tmp_path / "catalogs")
    fa = _FakeAdapter(
        scrapes=[
            [_L("a", 500), _L("b", 300), _L("c", 200)],   # baseline
            [_L("a", 500)],                                # full: b,c departed
        ],
        states={"b": "SOLD", "c": None},                  # b sold, c truly gone
    )
    _patch(monkeypatch, fa)

    assert cli.cmd_watch(_args()) == 0          # baseline
    capsys.readouterr()
    assert cli.cmd_watch(_args(full=True)) == 0
    err = capsys.readouterr().err
    assert "x1 sold" in err and "-1 gone" in err
