# ---
# template: execution
# version: 0.2.0
# summary: Tests for guard_outbound_mail.py — the self-only exemption read from per-user config, the
#   empty default (no exemption at all), and the cases that must still ask or deny, so the exemption
#   cannot quietly widen.
# created: 2026-10-16
# last_updated: 2026-10-16
# maintainer: your-agent
# ---
import json

import pytest

import guard_outbound_mail as g
from guard_outbound_mail import decide

ME = "me@example.com"
ME_TOO = "Me.Too@example.org"   # mixed case on purpose: matching is case-insensitive
OTHER = "colleague@example.net"

CASES = [
    (f"gws gmail +send --html --to {ME} --subject x --body '<p>x</p>'", None),
    (f"gws gmail +send --html --to 'Me <{ME}>,{ME_TOO}' --body '<p>x</p>'", None),
    (f"gws gmail +send --html --to {ME} --cc {OTHER} --body '<p>x</p>'", "ask"),
    (f"gws gmail +send --html --to {ME} --bcc x@y.com --body '<p>x</p>'", "ask"),
    (f"gws gmail +send --html --to {OTHER} --body '<p>x</p>'", "ask"),
    ("gws gmail +reply --html --message-id 123 --body '<p>x</p>'", "ask"),
    (f"gws gmail +reply --html --message-id 123 --to {ME} --body '<p>x</p>'", "ask"),
    (f"gws gmail +send --html --to {ME} --body '<p>a</p>' && gws gmail +send --html --to x@y.com --body '<p>b</p>'", "ask"),
    (f"gws gmail +send --to {ME} --body 'plain'", "deny"),
    ("gws gmail +send --html --body '<p>x</p>'", "ask"),
    (f"gws gmail +send --html --to {ME} --body 'x' --dry-run", None),
]


@pytest.mark.parametrize("cmd,expected", CASES)
def test_decide_with_configured_self(monkeypatch, cmd, expected):
    monkeypatch.setenv(g.SELF_ADDRESSES_ENV, f"{ME}, {ME_TOO.lower()}")
    assert decide(cmd)[0] == expected


def test_default_is_no_exemption(monkeypatch, tmp_path):
    """Nothing configured: a send to anyone, including the would-be self, asks."""
    monkeypatch.delenv(g.SELF_ADDRESSES_ENV, raising=False)
    monkeypatch.setattr(g, "_workspace_root", lambda: str(tmp_path))
    assert g.load_self_addresses() == frozenset()
    assert decide(f"gws gmail +send --html --to {ME} --body '<p>x</p>'")[0] == "ask"


def test_config_file(monkeypatch, tmp_path):
    monkeypatch.delenv(g.SELF_ADDRESSES_ENV, raising=False)
    cfg = tmp_path / "personal" / "config"
    cfg.mkdir(parents=True)
    (cfg / "mail-guard.json").write_text(json.dumps({"self_addresses": [ME]}))
    monkeypatch.setattr(g, "_workspace_root", lambda: str(tmp_path))
    assert decide(f"gws gmail +send --html --to {ME} --body '<p>x</p>'")[0] is None
    assert decide(f"gws gmail +send --html --to {OTHER} --body '<p>x</p>'")[0] == "ask"


def test_malformed_config_falls_back_to_no_exemption(monkeypatch, tmp_path):
    monkeypatch.delenv(g.SELF_ADDRESSES_ENV, raising=False)
    cfg = tmp_path / "personal" / "config"
    cfg.mkdir(parents=True)
    (cfg / "mail-guard.json").write_text("{not json")
    monkeypatch.setattr(g, "_workspace_root", lambda: str(tmp_path))
    assert decide(f"gws gmail +send --html --to {ME} --body '<p>x</p>'")[0] == "ask"
