"""CLI input validation + clean-error paths (no network).

These lock in the robustness fixes: bad inputs must produce a clean exit code,
never a raw Python traceback, and invalid numeric/age args must be rejected at
parse time before any work happens.
"""
import argparse

import pytest

from deals import cli


# ---- argparse type validators ----
@pytest.mark.parametrize("fn,bad", [
    (cli._pos_int, "0"), (cli._pos_int, "-3"), (cli._pos_int, "x"),
    (cli._nonneg_int, "-1"), (cli._nonneg_int, "x"),
    (cli._pos_float, "0"), (cli._pos_float, "-2"), (cli._pos_float, "x"),
    (cli._age_spec, "forever"), (cli._age_spec, "2"), (cli._age_spec, "2026-06-01"),
])
def test_validator_rejects(fn, bad):
    with pytest.raises(argparse.ArgumentTypeError):
        fn(bad)


@pytest.mark.parametrize("fn,good,exp", [
    (cli._pos_int, "10", 10), (cli._nonneg_int, "0", 0),
    (cli._pos_float, "40", 40.0), (cli._age_spec, "2mo", "2mo"),
])
def test_validator_accepts(fn, good, exp):
    assert fn(good) == exp


def test_validate_out_path_dir(tmp_path):
    with pytest.raises(ValueError, match="directory"):
        cli._validate_out_path(str(tmp_path))


def test_validate_out_path_missing_parent(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        cli._validate_out_path(str(tmp_path / "nope" / "x.csv"))


# ---- main(): bad args rejected at parse time (SystemExit from argparse) ----
@pytest.mark.parametrize("argv", [
    ["scrape", "--query", "x", "--max-pages", "-1"],
    ["scrape", "--query", "x", "--concurrency", "0"],
    ["scrape", "--query", "x", "--radius", "0"],
    ["scrape", "--query", "x", "--max-age", "forever"],
    ["ls", "--since", "forever"],
    ["ls", "--limit", "-5"],
])
def test_bad_args_exit_2(argv):
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    assert e.value.code == 2   # argparse usage error


# ---- main(): clean error (exit 1, no traceback) for runtime bad input ----
def test_ls_missing_in_file(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DEALS_CONFIG_DIR", str(tmp_path))
    rc = cli.main(["ls", "--in", str(tmp_path / "nope.csv")])
    assert rc == 1
    assert "catalog not found" in capsys.readouterr().err


def test_export_malformed_catalog(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DEALS_CONFIG_DIR", str(tmp_path))
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n")
    rc = cli.main(["export", "--in", str(bad), "--out", str(tmp_path / "o.csv")])
    assert rc == 1
    assert "does not look like a deals catalog" in capsys.readouterr().err


def test_scrape_without_config(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DEALS_CONFIG_DIR", str(tmp_path))   # empty -> no config
    rc = cli.main(["scrape", "--query", "x"])
    assert rc == 1
    assert "deals init" in capsys.readouterr().err
