#!/usr/bin/env python3
"""WCAG 2.x contrast ratio — verify text/UI contrast by MATH, never by eye.
Usage:  python3 contrast.py "#F5EFE3" "#A62639" [--ui]
  text needs >= 4.5:1 (AA) / 7:1 (AAA); large text >= 3:1; UI/graphics >= 3:1 (--ui).
Exit 0 if it passes the applicable threshold, 1 if it fails — so it can gate a build.
"""
import sys


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(hexstr):
    h = hexstr.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg, bg):
    la, lb = _lum(fg), _lum(bg)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    ui = '--ui' in sys.argv
    large = '--large' in sys.argv
    if len(args) < 2:
        print(__doc__)
        sys.exit(2)
    r = ratio(args[0], args[1])
    need = 3.0 if (ui or large) else 4.5
    label = 'UI/large' if (ui or large) else 'AA text'
    ok = r >= need
    print(f"{args[0]} on {args[1]}: {r:.2f}:1  ({'PASS' if ok else 'FAIL'} {label} >= {need})")
    sys.exit(0 if ok else 1)
