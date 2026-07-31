#!/usr/bin/env python3
"""Generalized Gemini image generator (render-product-image skill).

Usage:
  python3 gemini_image.py --out out.png --prompt "..." [--model gemini-3-pro-image]
                          [--ref composition.png] [--ref swatch.png]

- Pass a solid-hex SWATCH as a --ref to lock exact brand colors.
- Pass a prior good image as a --ref to hold composition.
- To CHANGE geometry, generate fresh (no composition ref) with numeric ratios
  in the prompt — editing a reference preserves its geometry.
Env: GEMINI_AGENTIC_MEDIA_API_KEY
"""
import os, sys, json, base64, urllib.request, argparse

def generate(prompt, out, model="gemini-3-pro-image", refs=None, timeout=240):
    key = os.environ["GEMINI_AGENTIC_MEDIA_API_KEY"]
    parts = [{"text": prompt}]
    for r in (refs or []):
        b = base64.b64encode(open(r, "rb").read()).decode()
        parts.append({"inline_data": {"mime_type": "image/png", "data": b}})
    body = json.dumps({"contents": [{"parts": parts}],
                       "generationConfig": {"responseModalities": ["IMAGE"]}}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    for _ in range(2):
        try:
            resp = json.load(urllib.request.urlopen(urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}), timeout=timeout))
            for p in resp["candidates"][0]["content"]["parts"]:
                d = p.get("inlineData") or p.get("inline_data")
                if d:
                    open(out, "wb").write(base64.b64decode(d["data"])); return True
        except Exception as e:
            print(f"gen error ({e}); retry")
    return False

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--prompt", required=True)
    ap.add_argument("--model", default="gemini-3-pro-image")
    ap.add_argument("--ref", action="append", default=[])
    a = ap.parse_args()
    print("saved", a.out) if generate(a.prompt, a.out, a.model, a.ref) else sys.exit("no image")
