#!/usr/bin/env python3
"""ONE Mahjong tile-render harness — self-evaluating convergence to spec.

Generates a near-orthographic SIDE ELEVATION, measures depth/length ratio +
colored-cap fraction from pixels (self-calibrating: the side face IS the
32x18.9 rectangle), and re-prompts until the ratio locks at target, then
renders the matching perspective HERO shot. Surfaces only the converged winner.

Usage: python3 tile_render_harness.py <outdir>
Env:   GEMINI_AGENTIC_MEDIA_API_KEY
Ref:   color-swatch-ref.png must sit next to this script.
"""
import os, sys, json, base64, urllib.request
from PIL import Image

KEY = os.environ["GEMINI_AGENTIC_MEDIA_API_KEY"]
HERE = os.path.dirname(os.path.abspath(__file__))
SWATCH = os.path.join(HERE, "color-swatch-ref.png")
OUTDIR = sys.argv[1] if len(sys.argv) > 1 else HERE

MODEL = "gemini-3-pro-image"
TARGET, TOL = 0.59, 0.02          # depth / length
CAP_TARGET, CAP_TOL = 0.20, 0.05  # colored back-cap / length
MAX_ITER = 12
MIN_FILL = 0.84                   # reject non-orthographic (tilted) draws

def gen(prompt, out, ref=SWATCH):
    b = base64.b64encode(open(ref, "rb").read()).decode()
    body = json.dumps({"contents": [{"parts": [
        {"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": b}}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]}}).encode()
    u = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}"
    for attempt in range(2):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(
                u, data=body, headers={"Content-Type": "application/json"}), timeout=240))
            for p in r["candidates"][0]["content"]["parts"]:
                d = p.get("inlineData") or p.get("inline_data")
                if d:
                    open(out, "wb").write(base64.b64decode(d["data"])); return True
        except Exception as e:
            print(f"    gen error ({e}); retry");
    return False

def measure(path):
    """Return (depth_ratio, cap_fraction) from a side-elevation image."""
    im = Image.open(path).convert("RGB"); W, H = im.size; px = im.load()
    bg = px[8, 8]
    def is_tile(p): return sum((a-b)**2 for a, b in zip(p, bg))**0.5 > 45
    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if is_tile(px[x, y]): xs.append(x); ys.append(y)
    if not xs: return None, None
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    tw, th = x1 - x0, y1 - y0
    if th >= tw: return None, None          # thickness must be < length; bad view
    fill = (len(xs) * 4) / (tw * th)        # rounded-rect fills ~0.9; tilted/face-showing < 0.84
    if fill < MIN_FILL: return None, None    # not a clean side elevation — reject
    depth = th / tw
    # colored cap: dark-red OR lavender run, sampled over a mid band (median)
    fracs = []
    for yy in range(y0 + th // 3, y1 - th // 3, 4):
        col = [x for x in range(x0, x1)
               if (px[x, yy][0] > 55 and px[x, yy][1] < 75 and px[x, yy][2] < 80)   # burgundy
               or (px[x, yy][2] > px[x, yy][1] > 90 and px[x, yy][2] - px[x, yy][0] > 15)]  # lavender
        if col: fracs.append((max(col) - min(col)) / tw)
    cap = sorted(fracs)[len(fracs)//2] if fracs else 0.0
    return depth, cap

def side_prompt(nudge=""):
    return ("Technical product PHOTOGRAPH, PURE SIDE ELEVATION of ONE mahjong tile, "
            "camera exactly level and perpendicular to the long SIDE face — orthographic, "
            "no perspective, no tilt. The side face is a clean flat rectangle: LENGTH "
            "horizontal, THICKNESS vertical. Target geometry: thickness must be EXACTLY "
            "0.59 x the length (a stout deep rectangle ~1.7:1, NOT thin). The rectangle is "
            "creamy IVORY except a colored stripe of EXACTLY 0.20 x the length along ONE "
            "short end (deep burgundy #7C1D2C); the rest is ivory. Smooth, rounded corners. "
            + nudge +
            " Flat evenly-lit warm peach background, tile centered filling most of the frame, "
            "straight-on. Photorealistic. No text, no ruler, no other objects.")

def hero_prompt(depth, cap):
    return ("Photorealistic studio product PHOTOGRAPH of THICK chunky mahjong tiles "
            "(Riichi/Chinese style, deep heavy blocks). EXACT proportions: face 24 wide x "
            "32 long; thickness = %.2f x the length (a deep chunky block, nearly as thick as "
            "wide). The colored back layer is a THIN cap = %.2f x the length; ALL other "
            "thickness is creamy IVORY. Side walls are IVORY (color only on the flat back "
            "face, not the sides). Backs COMPLETELY SMOOTH, no emblem. Two tiles stand "
            "upright backs-to-camera (LEFT lavender back, RIGHT deep-burgundy back); two lie "
            "face-up (low angle, deep ivory side walls); one TIPPED on edge showing the "
            "chunky end. Faces: carved inked bamboo, a red character, a blue dot. SECOND "
            "image = exact swatch (left lavender #C9B8E8 bright not grey, right burgundy "
            "#7C1D2C). Warm peach backdrop, soft studio light, shallow DOF, photorealistic. "
            "No text, no watermark." % (depth, cap))

# ---- convergence loop on the side elevation ----
print(f"Converging depth->{TARGET} (tol {TOL}), cap->{CAP_TARGET} (tol {CAP_TOL}), model {MODEL}")
best = None  # (abs_err, depth, cap, path)
nudge = ""
for i in range(1, MAX_ITER + 1):
    sp = os.path.join(OUTDIR, f"side_iter{i}.png")
    if not gen(side_prompt(nudge), sp):
        print(f"  iter {i}: generation failed"); continue
    d, c = measure(sp)
    if d is None:
        print(f"  iter {i}: no tile detected"); continue
    err = abs(d - TARGET)
    flag = "OK" if err <= TOL else ("thin" if d < TARGET else "thick")
    capflag = "OK" if abs(c - CAP_TARGET) <= CAP_TOL else ("thin" if c < CAP_TARGET else "thick")
    print(f"  iter {i}: depth={d:.3f} [{flag}]  cap={c:.3f} [{capflag}]")
    if best is None or err < best[0]:
        best = (err, d, c, sp)
    if err <= TOL and abs(c - CAP_TARGET) <= CAP_TOL:
        print(f"  CONVERGED at iter {i}")
        break
    # build corrective nudge for next round
    parts = []
    if d < TARGET - TOL:
        parts.append("The last tile was TOO THIN (thickness %.2f of length; need 0.59) — "
                     "make it about %d%% THICKER." % (d, round((TARGET/d - 1) * 100)))
    elif d > TARGET + TOL:
        parts.append("The last tile was TOO THICK (thickness %.2f of length; need 0.59) — "
                     "make it about %d%% THINNER." % (d, round((1 - TARGET/d) * 100)))
    if c < CAP_TARGET - CAP_TOL:
        parts.append("The colored end-cap was too thin — make it 0.20 of the length.")
    elif c > CAP_TARGET + CAP_TOL:
        parts.append("The colored end-cap was too thick — make it 0.20 of the length.")
    nudge = " CORRECTION: " + " ".join(parts)

err, d, c, sp = best
win = os.path.join(OUTDIR, "tile-side-elevation-locked.png")
Image.open(sp).save(win)
print(f"BEST side elevation: depth={d:.3f} cap={c:.3f} -> {win}")

# ---- render the matching hero at the locked proportions ----
hero = os.path.join(OUTDIR, "tile-set-photoreal-locked.png")
print("Rendering hero at locked proportions...")
if gen(hero_prompt(d, c), hero):
    print(f"HERO -> {hero}")
print(json.dumps({"depth_ratio": round(d, 3), "cap_fraction": round(c, 3),
                  "target": TARGET, "converged": err <= TOL}))
