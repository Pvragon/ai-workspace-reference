---
name: prepare-image-for-print
description: "Take a low-resolution or damaged photo to a print-ready file — choosing the print size, medium and upscaling tier the source can HONESTLY support, rather than the largest number the software will emit."
summary: "Method + scripts for print prep. Core rules: required DPI falls out of VIEWING DISTANCE, not a fixed 300 (so big prints often need less than small ones); print media differ enormously in how much they EXPOSE reconstructed detail (canvas forgives, acrylic prosecutes); and soft regions have two causes that must be told apart — dark+soft is compression loss (super-resolution can fill it) while bright+soft is optical defocus (NO upscaler fixes it, and sharpening around it makes it worse). Always report % reconstructed pixels; never present invented detail as recovered."
version: 1.0.1
template: skill-definition
created: 2026-07-25
last_updated: 2026-08-01
maintainer: your-agent
dependencies: [python, pillow, numpy, real-esrgan-ncnn]
tags: [image, print, upscaling, super-resolution, real-esrgan, photo, framing, dpi]
---

# Skill: Prepare Image For Print

Getting a photo printed large is **not** an upscaling problem. It is a
*budgeting* problem: a fixed amount of real information, spent across a chosen
size, on a medium that either hides or exposes the parts you had to invent.

Run the diagnosis first. Choose size and medium from what the file can support.
Upscale last.

> **Not this skill:** generating images from scratch → `render-product-image`.
> This skill only ever *restores and resizes* an existing photograph.

## Prerequisites

```bash
pip install pillow numpy                       # both scripts
python3 scripts/upscale_image_for_print.py --bootstrap   # Real-ESRGAN binary
```

`--bootstrap` downloads the correct ncnn release for the platform (the **Windows**
build when on WSL — see Environment below) and prints the `REALESRGAN_BIN` export.
It's optional: without the binary the upscaler still runs, falling back to plain
Lanczos with a loud warning that it is adding pixels and no detail. The diagnostic
script needs no binary at all.

Missing Python packages raise a named, actionable ImportError rather than a bare
traceback. Both scripts follow the execution standard — CLI plus an importable
`run()` returning a report dict, so they chain without re-parsing stdout.

## The two questions, in order

### 1. How much real detail is in here, and where is it missing?

```bash
python3 scripts/diagnose_image_detail.py photo.jpg \
  --region 900 380 1120 560 --label "shadow foliage" \
  --region 430 760 700 850  --label "foreground rock"
```

Soft regions have **two causes that look identical and behave oppositely**.
Brightness is the discriminator, because JPEG cannot gut a well-lit region:

| Symptom | Cause | Can upscaling help? |
|---|---|---|
| Dark + soft | JPEG quantisation crushed it | Yes — plausibly, but the texture is invented |
| Bright + soft | Optical defocus or motion blur | **No.** Ever. |

Real-ESRGAN inverts *downsampling and compression*. Reversing lens blur is
deconvolution — a different inverse problem the model has no mechanism for. Worse,
sharpening everything *around* a defocused region makes it **more** conspicuous
than it was at small size.

Often that's correct and should be left alone: a soft foreground against a sharp
subject is a depth cue. Sharpen it past what the focal plane allows and the image
reads as composited.

Also check **chroma subsampling**. A 4:2:0 source has half colour resolution, so
regions distinguished by hue rather than brightness (foliage, especially in shadow)
took the hit twice and will be the worst areas in the frame.

### 2. What can it honestly print at?

Required DPI comes from **viewing distance**, not habit. Human acuity is about one
arcminute, so:

```
required DPI ≈ 3438 / viewing distance in inches
```

| Viewing distance | DPI needed |
|---|---|
| 10 in (hand-held) | 300 |
| 24 in (2 ft) | 143 |
| 36 in (3 ft) | 95 |
| 48 in (4 ft) | 72 |

**This is why bigger is often safer.** People stand further back from large prints,
so required DPI falls faster than achievable DPI does. A 4× upscale that yields 215
DPI at 24″ wide has *more* perceptual headroom than 300 DPI at 12″ wide.

So DPI is rarely the binding constraint. The real one is **how physically large the
invented detail gets printed** — a weak region occupying 17% of frame width prints
2″ wide at 12″, and 4″ wide at 24″. Same softness, double the size. Judge the weak
regions at the intended size, not the DPI number.

## The fidelity ladder

Stop at the lowest tier that meets the need. Each step down trades truth for
apparent detail.

| Tier | Method | Behaviour | Use when |
|---|---|---|---|
| 1 | Lanczos / bicubic | Adds pixels, zero information. Honest. | Source is sharp; ≤1.5× |
| 2 | **Real-ESRGAN** | Regression model; reconstructs, deterministic | **Default for photographs** |
| 3 | ControlNet-Tile / SUPIR | Diffusion; fabricates texture, structure locked by conditioning | Tier 2 insufficient and fidelity still matters |
| 4 | General image models | Repaints the scene; structure merely *suggested* | Almost never for real photographs |

**Tier 2 is not generative.** It is a feed-forward regression model — same input,
same output, every time. That's why it cannot iterate: run it on its own output and
it invents detail *about the invention*, compounding artefacts, and its own clean
output is out-of-distribution for a model trained on degraded photos.

**Tier 4 is measurably wrong for restoration.** Verified 2026-07-25 against Gemini
3 Pro Image: composition drifted (rock shapes, tree position, waterfall silhouette
all changed), saturation rose 57%, depth of field was silently removed, and the
output came back at 1195×896 — *smaller than the 1292×968 input*. General image
models render at their own fixed budget regardless of input. They are not upscalers.

Tier 3 is not yet wired up here — see the backlog item
`my-lib/backlog/260725-tier3-structure-preserving-upscale.md`.

## Medium forgiveness — this decides more than DPI

Print surfaces differ enormously in how much they *expose* reconstructed detail.
Gloss and acrylic are chosen precisely because they boost micro-contrast, which is
exactly the property that prosecutes invented texture.

| Medium | Forgiveness | DPI wanted | Notes |
|---|---|---|---|
| Canvas | Highest | 150–200 | Weave physically camouflages softness |
| Matte / cotton rag (giclée) | High | 240 | Diffuses; but mutes saturation |
| Lustre / satin / E-Surface | Good | 300 | **Best default** — near-gloss colour, forgiving |
| Glossy photographic | Lower | 300 | Two reflective layers when framed under glass |
| Metallic paper | Low | 300 | Pearlescent base; deep blacks harden soft areas |
| Dye-sub aluminium | Low | 300 | High gloss, high micro-contrast |
| Acrylic face-mount | Lowest | 300 | Bonded sheet acts as a light pipe; magnifies everything |

Two traps worth naming:

- **Giclée is not automatically the premium answer.** It's a marketing term with no
  technical standard — any inkjet qualifies. Fine-art matte papers forgive softness
  but mute saturated colour, and the process wants 300+ DPI for a detail rendition
  a reconstructed file cannot supply. You pay for a capability you can't use.
- **Metallic paper is paper**, not a metal panel — same chromogenic process. Judge
  it on optics (gloss, Dmax, micro-contrast), not substrate.

## Reconciling aspect ratio with stock print sizes

Most photographs are 4:3 or 3:2; most stock print sizes are 3:2 or 4:5. Check the
lab's actual size list *before* rendering.

1. Prefer a stock size matching the source aspect — zero crop.
2. Otherwise crop the **short** axis and report exactly what is lost, in inches and
   as a percentage. Show the user the crop bands over the image; do not describe
   them in prose.
3. Bias the crop away from content that carries the picture. Centred is the default,
   not the answer.
4. Letterboxing onto a larger sheet is nearly always worse than a small crop.

## Pipeline

```bash
# one-time
python3 scripts/upscale_image_for_print.py --bootstrap
export REALESRGAN_BIN=/path/to/realesrgan-ncnn-vulkan[.exe]

# per image
python3 scripts/upscale_image_for_print.py photo.jpg --width-in 24 --height-in 18 --dpi 215
```

Stages: **ESRGAN at native 4× → crop to exact print aspect → Lanczos DOWN to target
→ tag DPI + embed sRGB.**

The downsample is load-bearing, not a formality. Shrinking the model output tightens
edges and averages away its waxy texture, so at identical final pixel count this
beats upscaling straight to target. Crop to the exact aspect *before* resampling so
nothing is stretched.

Always embed **sRGB** — consumer labs assume it and will mangle unflagged Adobe RGB.
Deliver max-quality JPEG for upload plus a TIFF as the editing master; note that a
TIFF from an 8-bit lossy source protects the pixels but adds no latent quality.

Never exceed the model's native 4×. Beyond that the excess is plain interpolation
wearing an AI badge — better to accept lower DPI, which large prints don't need.

## Environment

Real-ESRGAN ncnn needs **Vulkan**. On WSL there is no Vulkan ICD, so a Linux-native
build finds no GPU — use the **Windows `.exe`** through interop and it reaches the
host GPU (~1 min for a 1.3 MP 4× job). Works on Intel Arc, AMD and NVIDIA alike;
CUDA is not required and is unavailable on Intel hardware anyway.

**Do not `pip install realesrgan`** — it pulls ~2 GB of PyTorch for the same result.

## Presentation guidance

Once a file is right, the mounting decides whether it survives.

- **Nothing may touch the glass.** Photographic emulsion bonds to glazing over years
  of humidity cycling, permanently. Use a mat, or **spacers** — thin strips hidden
  under the frame lip that hold glass off while covering none of the image.
- **A mat costs ~¼″ per side** and needs a frame larger than the print. Ask for a
  ⅛″ overlap, or float-mount, when edge content matters.
- **Large prints need mounting or they ripple.** Above ~16″, RC paper waves inside a
  frame. Lab mounting is cheap; matboard (~⅛″) suits framed work and shallow
  rebates, foam core (~³⁄₁₆″) is stiffer but dents and eats frame depth.
- **Lab mounting ≠ lab framing.** Mounting is a cheap print add-on; framing is often
  5–10× the cost of a standard-size frame bought separately.
- Check rebate depth: glass + spacer + mounted print ≈ ½″.

## Honest reporting — required

Every run reports `upscale_factor` and `reconstructed_pct`. **Surface both.** At 4×,
only 1 pixel in 16 traces to the original — about 94% is reconstructed.

- Never describe invented detail as *recovered*.
- Name which regions are weakest and how large they print at the chosen size.
- If the source is a resized export (`*resize*` in the filename, stripped EXIF,
  suspiciously small for its era), **say so and push to find the original first.**
  A genuine 8 MP original beats any amount of processing, and this is the single
  highest-value step in the whole workflow.
- Recommend a cheap test print before an expensive medium. A $15 lustre proof
  settles arguments that neither party can win by estimation.

## Worked reference

`my-lib/runtime/.tmp/260725-upscaling-experiments/` — a 1.25 MP 2007 compact-camera
JPEG (4:2:0, quality ~78) taken to an 18×24 print: tier comparisons, the
defocus-vs-compression diagnosis, the tier-4 failure, and the crop visualisation.
