#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: Diagnose how much REAL detail a photo carries before you upscale or print it.
#          Separates optical defocus (bright + soft) from compression loss (dark + soft),
#          estimates JPEG damage, and tables which print sizes the file can honestly support.
# created: 2026-07-25
# last_updated: 2026-07-25
# maintainer: your-agent
# dependencies: [python>=3.9, pillow, numpy]
# tags: [image, print, diagnostics, detail, defocus, jpeg, upscaling]
# ---
"""Detail diagnostics for print prep.

Run this BEFORE upscaling. It answers the two questions that decide everything:

1. How much true detail is in here, and where is it missing?
   Soft regions have two very different causes and the fix differs:
     - DARK + soft  -> JPEG quantisation crushed it. Super-resolution can plausibly
       reconstruct texture here, though it will be invented.
     - BRIGHT + soft -> optical defocus or motion blur. NO upscaler fixes this;
       ESRGAN inverts downsampling/compression, not lens blur (that's deconvolution).
       Sharpening everything around it makes it MORE conspicuous, not less.
   Compression cannot gut a well-lit region, so brightness is the discriminator.

2. What can it honestly print at?
   Required DPI falls out of viewing distance (~1 arcminute of visual acuity), it is
   not a fixed 300. Big prints are viewed from further away, so they often need LESS
   resolution than a small print does -- see the size table this emits.

CLI:
    diagnose_image_detail.py photo.jpg
    diagnose_image_detail.py photo.jpg --region 900 380 1120 560 --label "shadow foliage"
    diagnose_image_detail.py photo.jpg --crops ./out    # 100% inspection crops
"""
from __future__ import annotations

import argparse
import statistics
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as e:  # actionable, not a bare traceback
    raise ImportError(
        f"prepare-image-for-print needs '{e.name}'. Install with:  pip install pillow numpy"
    ) from e

# viewing distance in inches typically used for a print of a given long edge (inches)
TYPICAL_VIEWING = [(9, 24), (12, 30), (18, 36), (24, 45), (36, 60), (60, 96)]
DARK_LUMA = 60.0      # below this, compression crush is the likely cause
SOFT_DETAIL = 8.0     # mean gradient magnitude below this reads as soft
NATIVE_SCALE = 4      # Real-ESRGAN's trained scale factor


def viewing_distance_for(long_edge_in: float) -> float:
    for edge, dist in TYPICAL_VIEWING:
        if long_edge_in <= edge:
            return dist
    return TYPICAL_VIEWING[-1][1]


def detail_map(im: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Return (luminance, high-frequency energy) arrays."""
    g = np.asarray(im.convert("L"), dtype=np.float32)
    gy, gx = np.gradient(g)
    return g, np.hypot(gx, gy)


def classify(luma: float, detail: float) -> str:
    if detail >= SOFT_DETAIL:
        return "sharp"
    return "compression-crushed" if luma < DARK_LUMA else "DEFOCUS (unfixable)"


def run(path: str, regions: list[tuple[str, tuple[int, int, int, int]]] | None = None,
        crops_dir: str | None = None) -> dict:
    """Importable entry point. Prints a human report and returns the findings dict.

    Returns:
        size, megapixels, subsampling, jpeg_qtable_mean, soft_dark_tiles,
        soft_bright_tiles, regions (name -> {luma, detail, diagnosis}),
        max_honest_long_edge_in.
    """
    im = Image.open(path)
    report: dict = {"subsampling": None, "jpeg_qtable_mean": None, "regions": {}}
    w, h = im.size
    print(f"file        : {path}")
    print(f"dimensions  : {w} x {h}  ({w*h/1e6:.2f} MP)   aspect {w/h:.4f}")

    if im.format == "JPEG":
        try:
            from PIL.JpegImagePlugin import get_sampling
            sub = get_sampling(im)
            report["subsampling"] = sub
            print(f"subsampling : {sub}  ({'4:4:4 - full colour' if sub == 0 else '4:2:0 - colour resolution HALVED'})")
        except Exception:
            pass
        if im.quantization:
            mean_q = statistics.mean(statistics.mean(t) for t in im.quantization.values())
            report["jpeg_qtable_mean"] = round(mean_q, 1)
            print(f"jpeg qtable : mean {mean_q:.1f} (lower = higher quality; >25 means real artefacts)")

    rgb = im.convert("RGB")
    g, hf = detail_map(rgb)

    # --- detail vs luminance, the discriminator ---
    T = 32
    rows = np.array([(g[y:y+T, x:x+T].mean(), hf[y:y+T, x:x+T].mean())
                     for y in range(0, h - T, T) for x in range(0, w - T, T)])
    print(f"\ndetail by luminance band ({len(rows)} tiles of {T}px)")
    print(f"  {'band':<22}{'tiles':>7}{'detail':>9}")
    for lo, hi, name in [(0, 40, "deep shadow  0-40"), (40, 80, "shadow      40-80"),
                         (80, 140, "midtone    80-140"), (140, 200, "light     140-200"),
                         (200, 256, "highlight 200-255")]:
        m = (rows[:, 0] >= lo) & (rows[:, 0] < hi)
        if m.sum():
            print(f"  {name:<22}{int(m.sum()):>7}{rows[m, 1].mean():>9.2f}")

    soft_dark = int(((rows[:, 1] < SOFT_DETAIL) & (rows[:, 0] < DARK_LUMA)).sum())
    soft_bright = int(((rows[:, 1] < SOFT_DETAIL) & (rows[:, 0] >= DARK_LUMA)).sum())
    print(f"\n  soft & dark   : {soft_dark:>5} tiles  -> compression loss (SR can plausibly fill)")
    print(f"  soft & bright : {soft_bright:>5} tiles  -> defocus / motion blur (NO upscaler fixes)")

    # --- named regions ---
    if regions:
        print(f"\n{'region':<28}{'luma':>7}{'detail':>9}   diagnosis")
        for name, (x0, y0, x1, y1) in regions:
            L, H = g[y0:y1, x0:x1].mean(), hf[y0:y1, x0:x1].mean()
            report["regions"][name] = {"luma": round(float(L), 1),
                                       "detail": round(float(H), 2),
                                       "diagnosis": classify(L, H)}
            print(f"{name:<28}{L:>7.1f}{H:>9.2f}   {classify(L, H)}")

    # --- what can it print at ---
    print(f"\nprint sizes this file can support (long edge, at native {NATIVE_SCALE}x SR)")
    print(f"  {'size':<12}{'SR px':>8}{'DPI':>7}{'eye needs':>11}{'headroom':>10}")
    sr_w = w * NATIVE_SCALE
    max_honest = None
    for long_in in (9, 12, 16, 18, 24, 30, 36):
        dpi = min(300, sr_w / long_in)
        need = 3438 / viewing_distance_for(long_in)
        ok = dpi >= need
        if ok:
            max_honest = long_in
        print(f"  {str(long_in)+'in':<12}{int(dpi*long_in):>8}{dpi:>7.0f}{need:>11.0f}"
              f"{dpi/need:>9.1f}x{'' if ok else '   <-- TOO BIG'}")
    report["max_honest_long_edge_in"] = max_honest
    print("\n  NB: headroom often RISES with size -- bigger prints are viewed from further.")
    print("      The binding constraint is usually how large the invented detail prints,")
    print("      not DPI. Check the weak regions above at your intended size.")

    if crops_dir:
        d = Path(crops_dir)
        d.mkdir(parents=True, exist_ok=True)
        for name, box in (regions or []):
            slug = name.lower().replace(" ", "-")
            rgb.crop(box).save(d / f"inspect-{slug}.png")
        print(f"\n100% crops written to {d}")

    report.update({"size": (w, h), "megapixels": round(w * h / 1e6, 2),
                   "soft_dark_tiles": soft_dark, "soft_bright_tiles": soft_bright})
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("--region", nargs=4, type=int, action="append", metavar=("X0", "Y0", "X1", "Y1"),
                   help="analyse a region; repeatable")
    p.add_argument("--label", action="append", default=[], help="name for each --region")
    p.add_argument("--crops", help="directory to write 100%% inspection crops of each region")
    a = p.parse_args()
    regions = [(a.label[i] if i < len(a.label) else f"region {i+1}", tuple(r))
               for i, r in enumerate(a.region or [])]
    run(a.src, regions, a.crops)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
