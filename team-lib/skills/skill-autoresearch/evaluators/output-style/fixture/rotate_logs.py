#!/usr/bin/env python3
"""Rotate log files in a directory: gzip files older than N days, keep the newest K archives."""
import argparse
import gzip
import os
import shutil
import time
from pathlib import Path


def find_logs(log_dir: Path, pattern: str):
    return sorted(p for p in log_dir.glob(pattern) if p.is_file())


def is_older_than(path: Path, days: int) -> bool:
    return (time.time() - path.stat().st_mtime) > days * 86400


def compress(path: Path) -> Path:
    target = path.with_suffix(path.suffix + ".gz")
    with open(path, "rb") as src, gzip.open(target, "wb") as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()
    return target


def prune_archives(log_dir: Path, keep: int):
    archives = sorted(log_dir.glob("*.gz"), key=lambda p: p.stat().st_mtime)
    for old in archives[:-keep]:
        old.unlink()


def rotate(log_dir: Path, pattern: str, days: int, keep: int, dry_run: bool = False):
    rotated = []
    for log in find_logs(log_dir, pattern):
        if not is_older_than(log, days):
            continue
        if dry_run:
            print(f"would compress {log}")
            continue
        rotated.append(compress(log))
    if not dry_run:
        prune_archives(log_dir, keep)
    return rotated


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("log_dir", type=Path)
    ap.add_argument("--pattern", default="*.log")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--keep", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.log_dir.is_dir():
        raise SystemExit(f"not a directory: {args.log_dir}")
    done = rotate(args.log_dir, args.pattern, args.days, args.keep, args.dry_run)
    print(f"compressed {len(done)} file(s)")


if __name__ == "__main__":
    main()
