import os, time
from pathlib import Path
import rotate_logs


def make(tmp_path: Path, name: str, age_days: int, body=b"x" * 100):
    p = tmp_path / name
    p.write_bytes(body)
    old = time.time() - age_days * 86400
    os.utime(p, (old, old))
    return p


def test_compresses_old_logs(tmp_path):
    make(tmp_path, "a.log", 10)
    make(tmp_path, "b.log", 1)
    out = rotate_logs.rotate(tmp_path, "*.log", days=7, keep=10)
    assert [p.name for p in out] == ["a.log.gz"]
    assert (tmp_path / "b.log").exists()


def test_dry_run_touches_nothing(tmp_path):
    make(tmp_path, "a.log", 10)
    rotate_logs.rotate(tmp_path, "*.log", days=7, keep=10, dry_run=True)
    assert (tmp_path / "a.log").exists()


def test_prunes_to_keep(tmp_path):
    for i in range(5):
        make(tmp_path, f"old{i}.log", 30 + i)
    rotate_logs.rotate(tmp_path, "*.log", days=7, keep=2)
    assert len(list(tmp_path.glob("*.gz"))) == 2
