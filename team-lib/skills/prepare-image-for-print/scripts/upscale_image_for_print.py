#!/usr/bin/env python3
# ---
# template: execution
# version: 2.0.1
# summary: Upscale a low-resolution photo into a print-ready file at a target print size and DPI.
#          Real-ESRGAN super-resolution (GPU, via the ncnn binary) followed by a Lanczos
#          downsample, exact-aspect cropping, DPI tagging and sRGB embedding for photo labs.
#          Reports upscale factor and % reconstructed so the honesty of a size is visible.
# created: 2026-07-25
# last_updated: 2026-08-01
# maintainer: your-agent
# dependencies: [python>=3.9, pillow, real-esrgan-ncnn (optional - see --bootstrap)]
# tags: [image, print, upscaling, super-resolution, real-esrgan]
# ---
"""Print-prep upscaler (tiers 1-2 of the fidelity ladder -- see SKILL.md).

Two-stage by design: ESRGAN 4x, then Lanczos DOWN to target. Shrinking the model
output tightens edges and averages away its characteristic waxy texture, so at the
same final pixel count this beats upscaling straight to target in one step.

Binary resolution order:
  1. $REALESRGAN_BIN
  2. known-good locations (see CANDIDATES)
  3. --bootstrap downloads the release into ~/.local/share/realesrgan
Without a binary it still runs, falling back to plain Lanczos with a loud warning --
bigger pixels, zero new detail.

On WSL: use the WINDOWS .exe. There is no WSL Vulkan ICD, so a Linux-native ncnn
build finds no GPU. The .exe reaches the host GPU through interop. Do NOT
`pip install realesrgan` -- ~2GB of PyTorch for the same result.

CLI:
    upscale_image_for_print.py photo.jpg --width-in 18 --height-in 12
    upscale_image_for_print.py photo.jpg --width-in 24 --height-in 18 --dpi 215
    upscale_image_for_print.py --bootstrap

Programmatic:
    from upscale_image_for_print import run
    report = run("photo.jpg", 18, 12, out_dir="./out")
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from fractions import Fraction
from pathlib import Path

try:
    from PIL import Image, ImageCms
except ImportError as e:  # actionable, not a bare traceback
    raise ImportError(
        f"prepare-image-for-print needs '{e.name}'. Install with:  pip install pillow"
    ) from e

PHOTO_MODEL = "realesrgan-x4plus"  # general photo model; *-anime is for illustration
NATIVE_SCALE = 4                   # the model's trained scale factor
RELEASE_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
               "realesrgan-ncnn-vulkan-20220424-{plat}.zip")

CANDIDATES = [
    Path.home() / ".local/share/realesrgan/realesrgan-ncnn-vulkan",
    Path("/mnt/c/Users") / os.environ.get("WIN_USER", "") / "tools/realesrgan/realesrgan-ncnn-vulkan.exe",
    Path("/opt/realesrgan/realesrgan-ncnn-vulkan"),
]


def _is_wsl() -> bool:
    return "microsoft" in platform.uname().release.lower()


def find_binary() -> Path | None:
    """Locate the Real-ESRGAN ncnn binary, or None."""
    if (env := os.environ.get("REALESRGAN_BIN")):
        p = Path(env)
        if p.exists():
            return p
    for c in CANDIDATES:
        if c.exists():
            return c
    # on WSL, scan Windows user profiles for the standard tools dir
    if _is_wsl():
        for home in Path("/mnt/c/Users").glob("*"):
            p = home / "tools/realesrgan/realesrgan-ncnn-vulkan.exe"
            if p.exists():
                return p
    return None


def bootstrap(dest: Path | None = None) -> Path:
    """Download + extract the ncnn release. On WSL this fetches the WINDOWS build."""
    import urllib.request

    plat = "windows" if _is_wsl() or os.name == "nt" else (
        "macos" if sys.platform == "darwin" else "ubuntu")
    if dest is None:
        dest = (Path("/mnt/c/Users") / os.environ.get("WIN_USER", os.environ.get("USER", ""))
                / "tools/realesrgan") if plat == "windows" and _is_wsl() else \
               (Path.home() / ".local/share/realesrgan")
    dest.mkdir(parents=True, exist_ok=True)
    zp = dest / "release.zip"
    url = RELEASE_URL.format(plat=plat)
    print(f"downloading {url}")
    urllib.request.urlretrieve(url, zp)
    with zipfile.ZipFile(zp) as z:
        z.extractall(dest)
    zp.unlink()
    for junk in ("input.jpg", "input2.jpg", "onepiece_demo.mp4"):
        (dest / junk).unlink(missing_ok=True)
    exe = next((p for p in dest.rglob("realesrgan-ncnn-vulkan*")
                if p.is_file() and p.suffix in ("", ".exe")), None)
    if exe is None:
        raise RuntimeError(f"extracted to {dest} but found no binary")
    exe.chmod(0o755)
    print(f"installed: {exe}\nexport REALESRGAN_BIN={exe}")
    return exe


def _esrgan(src: Path, binary: Path) -> Image.Image:
    """Run Real-ESRGAN at its native scale. cwd must be the binary dir (models/ is relative)."""
    d = binary.parent
    stage_in = d / f".tmp_in_{os.getpid()}{src.suffix}"
    stage_out = d / f".tmp_out_{os.getpid()}.png"
    shutil.copy(src, stage_in)
    try:
        subprocess.run(
            [f"./{binary.name}", "-i", stage_in.name, "-o", stage_out.name,
             "-n", PHOTO_MODEL, "-s", str(NATIVE_SCALE)],
            cwd=d, check=True, capture_output=True,
        )
        return Image.open(stage_out).convert("RGB").copy()
    finally:
        stage_in.unlink(missing_ok=True)
        stage_out.unlink(missing_ok=True)


def _crop_to_exact_aspect(im: Image.Image, w_in: float, h_in: float) -> Image.Image:
    """Center-crop to the target aspect EXACTLY, so the resample introduces zero distortion."""
    target = Fraction(w_in).limit_denominator(1000) / Fraction(h_in).limit_denominator(1000)
    w, h = im.size
    if Fraction(w, h) == target:
        return im
    new_w = int(h * target)
    new_h = h if new_w <= w else int(w / target)
    if new_w > w:
        new_w = w
    while Fraction(new_w, new_h) != target and new_h > 1:
        new_h -= 1
        new_w = int(new_h * target)
    left, top = (w - new_w) // 2, (h - new_h) // 2
    return im.crop((left, top, left + new_w, top + new_h))


def needed_dpi(viewing_distance_in: float) -> float:
    """DPI the eye can actually resolve at a distance (1 arcminute acuity)."""
    return 3438 / viewing_distance_in


def run(src_path: str, width_in: float, height_in: float, dpi: int = 300,
        out_dir: str = ".", basename: str | None = None, tiff: bool = True,
        binary: Path | None = None) -> dict:
    """Upscale src to width_in x height_in inches at dpi. Returns a report dict."""
    src, out = Path(src_path), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = basename or f"{src.stem}-{width_in:g}x{height_in:g}-{dpi}dpi"

    orig = Image.open(src).convert("RGB")
    target_px = (int(round(width_in * dpi)), int(round(height_in * dpi)))
    factor = target_px[0] / orig.size[0]

    binary = binary or find_binary()
    used_ai = False
    if factor > 1.0 and binary is not None:
        big = _esrgan(src, binary)
        used_ai = True
    else:
        if factor > 1.0:
            print("WARNING: no Real-ESRGAN binary found -- falling back to plain Lanczos.\n"
                  "         This adds pixels but ZERO detail. Run with --bootstrap to install.",
                  file=sys.stderr)
        big = orig

    cropped = _crop_to_exact_aspect(big, width_in, height_in)
    final = cropped.resize(target_px, Image.LANCZOS)

    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    files = []
    jpg = out / f"{stem}.jpg"
    final.save(jpg, quality=100, subsampling=0, dpi=(dpi, dpi), icc_profile=icc)
    files.append(str(jpg))
    if tiff:
        tif = out / f"{stem}.tif"
        final.save(tif, compression="tiff_lzw", dpi=(dpi, dpi), icc_profile=icc)
        files.append(str(tif))

    return {
        "source_px": orig.size,
        "source_mp": round(orig.size[0] * orig.size[1] / 1e6, 2),
        "engine": "real-esrgan-x4plus" if used_ai else "lanczos-only",
        "intermediate_px": big.size,
        "final_px": final.size,
        "upscale_factor": round(factor, 2),
        "reconstructed_pct": round((1 - 1 / max(factor, 1) ** 2) * 100, 1),
        "print_size_in": (width_in, height_in),
        "dpi": dpi,
        "comfortable_viewing_distance_in": round(3438 / dpi, 1),
        "files": files,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src", nargs="?")
    p.add_argument("--width-in", type=float)
    p.add_argument("--height-in", type=float)
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--out-dir", default=".")
    p.add_argument("--basename")
    p.add_argument("--no-tiff", action="store_true")
    p.add_argument("--bootstrap", action="store_true", help="download + install the binary, then exit")
    a = p.parse_args()

    if a.bootstrap:
        bootstrap()
        return 0
    if not (a.src and a.width_in and a.height_in):
        p.error("src, --width-in and --height-in are required (or use --bootstrap)")

    r = run(a.src, a.width_in, a.height_in, a.dpi, a.out_dir, a.basename, not a.no_tiff)
    for k, v in r.items():
        print(f"{k}: {v}")
    if r["upscale_factor"] > NATIVE_SCALE * 1.05:
        print(f"\nWARNING: {r['upscale_factor']}x exceeds the model's native {NATIVE_SCALE}x -- "
              "the excess is plain interpolation, so detail will look synthetic.\n"
              "         Consider a smaller print size, or a lower --dpi (large prints are "
              "viewed from further away and need far less).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
