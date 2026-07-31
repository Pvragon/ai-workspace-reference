#!/usr/bin/env python3
"""Self-calibrating measurement for the render-product-image skill.

Two tools, both refusing to eyeball:
  ratio(img)  -> depth/length from a NEAR-ORTHOGRAPHIC elevation. The object's
                 side face renders as its true rectangle, so bbox height/width IS
                 the real ratio. Rejects non-orthographic (tilted) frames.
  color(img, box, target_hex) -> (sampled_hex, deltaE) over an evenly-lit patch.

Usage: python3 measure_dims.py ratio elevation.png
       python3 measure_dims.py color hero.png 0.30 0.30 0.40 0.45 C9B8E8
"""
import sys
from PIL import Image

MIN_FILL = 0.84  # bbox fill below this => tilted/perspective => not a clean elevation

def ratio(path):
    im = Image.open(path).convert("RGB"); W, H = im.size; px = im.load()
    bg = px[8, 8]
    def is_obj(p): return sum((a-b)**2 for a, b in zip(p, bg))**0.5 > 45
    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if is_obj(px[x, y]): xs.append(x); ys.append(y)
    if not xs: return None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    tw, th = x1 - x0, y1 - y0
    fill = (len(xs) * 4) / (tw * th) if tw and th else 0
    if fill < MIN_FILL: return None          # not orthographic — discard
    return th / tw

def _d(h1, h2):
    a = [int(h1[i:i+2], 16) for i in (0, 2, 4)]
    b = [int(h2[i:i+2], 16) for i in (0, 2, 4)]
    return round(sum((x-y)**2 for x, y in zip(a, b))**0.5, 1)

def color(path, fbox, target):
    im = Image.open(path).convert("RGB"); W, H = im.size
    b = [int(fbox[0]*W), int(fbox[1]*H), int(fbox[2]*W), int(fbox[3]*H)]
    px = [im.getpixel((x, y)) for x in range(b[0], b[2], 2) for y in range(b[1], b[3], 2)]
    hexv = "%02X%02X%02X" % tuple(sorted(p[i] for p in px)[len(px)//2] for i in range(3))
    return "#" + hexv, _d(hexv, target.lstrip("#").upper())

if __name__ == "__main__":
    if sys.argv[1] == "ratio":
        r = ratio(sys.argv[2])
        print(f"depth/length = {r:.3f}" if r else "not a clean orthographic elevation (rejected)")
    elif sys.argv[1] == "color":
        box = tuple(map(float, sys.argv[3:7])); tgt = sys.argv[7]
        h, d = color(sys.argv[2], box, tgt)
        print(f"sampled {h}  deltaE->#{tgt.lstrip('#').upper()} = {d}")
