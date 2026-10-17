"""Domain pack engine: load, extract (+ guardrails), value, score, verify-tier."""
import pytest

from deals import packs
from deals.record import Listing


def _L(title="", desc=None, price=None):
    return Listing(listing_id="x", site="offerup", url="u", title=title,
                   description=desc, price=price)


@pytest.fixture
def gp():
    # the shipped reference pack
    return packs.load_pack("gaming-pc")


def test_pack_loads(gp):
    assert gp.name == "gaming-pc"
    assert "gpu" in gp.regex
    assert gp.value_table["gpu"]["rtx 4070"] == (400, 480, 560)
    assert gp.verify_tier_threshold == 0.55


def test_extract_gpu_cpu(gp):
    a = packs.extract(gp, _L("Gaming PC RTX 4070 Ryzen 5 5600 16GB RAM 1tb ssd"))
    assert a["gpu"] == "rtx 4070"
    assert "ryzen 5 5600" in a["cpu"]


def test_extract_skips_aspirational_phrasing(gp):
    # "upgrade to RTX 4090" must NOT be extracted as the card it has
    a = packs.extract(gp, _L("Gaming PC RTX 3060", desc="Plenty of room, upgrade to RTX 4090 later"))
    assert a.get("gpu") == "rtx 3060"


def test_extract_prefers_title(gp):
    a = packs.extract(gp, _L("RTX 3070 gaming rig", desc="also compatible with RTX 4080"))
    assert a["gpu"] == "rtx 3070"


def test_value_sums_components_plus_base(gp):
    a = {"gpu": "rtx 4070", "cpu": "ryzen 5 5600"}
    mn, av, mx = packs.value(gp, a)
    # base(90,130,170) + rtx4070(400,480,560) + ryzen5600(80,105,130)
    assert av == 130 + 480 + 105


def test_value_requires_a_recognized_component(gp):
    # no recognized component -> not valued off base alone (avoids the
    # controller-looks-like-a-deal false positive)
    assert packs.value(gp, {"gpu": "totally unknown card"}) == (None, None, None)
    assert packs.value(gp, {}) == (None, None, None)


def test_in_domain_gate(gp):
    assert packs.in_domain(gp, _L("Gaming PC RTX 4070")) is True
    assert packs.in_domain(gp, _L("Xbox Series X Wireless Controller")) is False
    assert packs.in_domain(gp, _L("27in Gaming Monitor 165Hz")) is False
    assert packs.in_domain(gp, _L("Lot of 46 Pc Vintage Barbie")) is False  # 'lot of'/'barbie'


def test_apply_pack_gates_out_of_domain(gp):
    ctrl = _L("Xbox Series X Wireless Controller", price=20)
    packs.apply_pack(gp, [ctrl])
    assert ctrl.flags.get("out_of_domain") is True
    assert ctrl.est_value_avg is None
    assert ctrl.deal_score is None          # NOT scored as a $130 'deal'


def test_deal_score():
    assert packs.deal_score(300, 600) == 0.5
    assert packs.deal_score(600, 600) == 0.0
    assert packs.deal_score(900, 600) == -0.5
    assert packs.deal_score(None, 600) is None
    assert packs.deal_score(300, 0) is None


def test_apply_pack_sets_fields_and_verify_tier(gp):
    cheap = _L("Gaming PC RTX 4070 Ryzen 5 5600", price=200)   # est ~715 -> score ~0.72
    fair = _L("Gaming PC RTX 3060", price=300)                 # est ~350 -> score ~0.14
    packs.apply_pack(gp, [cheap, fair])
    assert cheap.est_value_avg == 715
    assert cheap.deal_score is not None and cheap.deal_score >= 0.55
    assert cheap.flags.get("verify_tier") is True              # high-reward/high-verify
    assert "verify_tier" not in (fair.flags or {})            # normal deal, no flag


def test_missing_pack_raises():
    with pytest.raises(packs.PackError):
        packs.load_pack("no-such-domain")
