#!/usr/bin/env python3
# ---
# template: execution-script
# version: 0.2.0
# summary: Render an HTML page, SVG or URL to PNGs at desktop, slide, phone and print surfaces (headless Chromium via Python Playwright) and report horizontal overflow, console errors and blank renders, so a visualization reviewer judges pixels, not code.
# created: 2026-10-22
# last_updated: 2026-10-22
# maintainer: pvragon
# dependencies: [python-playwright (chromium build installed), Pillow]
# usage: render_for_review.py <file.html|file.svg|URL> [--state NAME=SEL;SEL ...] [--out DIR] [--surfaces desktop,slide,phone,print] [--scheme light|dark] [--wait MS] [--full-page] | --self-check
# ---
"""Render a visualization for review.

Local files are served over a throwaway http.server (file:// is unreliable in this
environment's Chromium). Each surface writes <surface>.png (the viewport, what a reader
sees first) and, with --full-page, <surface>-full.png. report.json holds, per surface:
page width/height, horizontal overflow in px and the worst offending elements, console
errors, and whether the PNG is blank (one flat color, a known headless failure mode).

Exit code: 0 rendered, 1 a surface failed or rendered blank, 2 bad input.
"""
import argparse
import datetime as dt
import functools
import http.server
import json
import os
import shutil
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

SURFACES = {
    # name: (width, height, mobile/touch, media)
    "desktop": (1440, 900, False, "screen"),
    "slide": (1280, 720, False, "screen"),
    "phone": (390, 844, True, "screen"),
    "print": (1123, 794, False, "print"),  # A4 landscape at 96 dpi
}

OVERFLOW_JS = """() => {
  const de = document.documentElement, vw = de.clientWidth;
  const off = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > vw + 1) {
      off.push({tag: el.tagName.toLowerCase(), cls: (el.className && el.className.baseVal === undefined ? el.className : '').toString().slice(0, 60),
                right: Math.round(r.right), text: (el.innerText || '').trim().slice(0, 50)});
    }
  }
  off.sort((a, b) => b.right - a.right);
  return {scrollWidth: de.scrollWidth, clientWidth: vw, scrollHeight: de.scrollHeight,
          overflowPx: Math.max(0, de.scrollWidth - vw), offenders: off.slice(0, 5)};
}"""

RUNTIME_TMP = Path.home() / "ai-workspace/my-lib/runtime/.tmp"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve_dir(directory):
    """Serve a directory on a free localhost port; returns (server, base_url)."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def is_blank(png_path):
    """True when the image is one flat color (every channel has min == max)."""
    from PIL import Image
    with Image.open(png_path) as im:
        return all(lo == hi for lo, hi in im.convert("RGB").getextrema())


def run(target, out=None, surfaces=("desktop", "slide", "phone", "print"), scheme="light",
        wait_ms=800, full_page=False, states=()):
    """Render `target` on each surface, in the default state and in each (name, [selectors]) state. Returns the report dict (also written to out/report.json)."""
    from playwright.sync_api import sync_playwright

    srv = None
    if target.startswith(("http://", "https://")):
        url, slug = target, target.rstrip("/").split("/")[-1] or "page"
    else:
        p = Path(target).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(target)
        srv, base = serve_dir(p.parent)
        url, slug = f"{base}/{p.name}", p.stem
    stamp = dt.date.today().strftime("%y%m%d")
    out = Path(out) if out else RUNTIME_TMP / f"{stamp}-render-{slug[:40]}"
    out.mkdir(parents=True, exist_ok=True)

    report = {"target": target, "url": url, "scheme": scheme, "out": str(out), "surfaces": {}}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for name in surfaces:
                w, h, mobile, media = SURFACES[name]
                ctx = browser.new_context(viewport={"width": w, "height": h}, is_mobile=mobile,
                                          has_touch=mobile, device_scale_factor=2 if mobile else 1,
                                          color_scheme=scheme)
                page = ctx.new_page()
                errors = []
                page.on("console", lambda m, e=errors: e.append(m.text[:200]) if m.type == "error" else None)
                page.on("pageerror", lambda exc, e=errors: e.append(str(exc)[:200]))
                for state, clicks in [("default", [])] + list(states):
                    key = name if state == "default" else f"{name}-{state}"
                    entry = {"viewport": f"{w}x{h}", "media": media, "state": state, "clicks": clicks}
                    del errors[:]
                    try:
                        page.emulate_media(media=media, color_scheme=scheme)
                        page.goto(url, wait_until="networkidle", timeout=30000)
                        page.wait_for_timeout(wait_ms)
                        for sel in clicks:
                            page.click(sel, timeout=5000)
                            page.wait_for_timeout(wait_ms)
                        png = out / f"{key}.png"
                        page.screenshot(path=str(png))
                        entry["png"] = str(png)
                        entry["blank"] = is_blank(png)
                        if full_page:
                            fpng = out / f"{key}-full.png"
                            page.screenshot(path=str(fpng), full_page=True)
                            entry["png_full"] = str(fpng)
                        entry.update(page.evaluate(OVERFLOW_JS))
                    except Exception as exc:  # report and continue with other surfaces/states
                        entry["error"] = str(exc)[:300]
                    entry["console_errors"] = list(errors)
                    report["surfaces"][key] = entry
                ctx.close()
            browser.close()
    finally:
        if srv:
            srv.shutdown()
            srv.server_close()
    (out / "report.json").write_text(json.dumps(report, indent=2))
    return report


def summarize(report):
    lines = [f"Rendered {report['target']} -> {report['out']}"]
    for name, e in report["surfaces"].items():
        if "error" in e:
            lines.append(f"  {name:8s} ERROR {e['error']}")
            continue
        flags = []
        if e.get("blank"):
            flags.append("BLANK RENDER")
        if e.get("overflowPx"):
            flags.append(f"h-overflow {e['overflowPx']}px")
        if e.get("console_errors"):
            flags.append(f"{len(e['console_errors'])} console errors")
        lines.append(f"  {name:8s} {e['viewport']:9s} page {e.get('scrollWidth')}x{e.get('scrollHeight')}  "
                     f"{'; '.join(flags) or 'ok'}  {e['png']}")
    return "\n".join(lines)


def failed(report):
    return any("error" in e or e.get("blank") for e in report["surfaces"].values())


def self_check():
    """Render two fixtures: a clean chart page must pass with no overflow; a page with a
    900px-wide element must be flagged on phone. Asserts PNGs exist and are not blank."""
    base = RUNTIME_TMP if RUNTIME_TMP.exists() else None
    tmp = Path(tempfile.mkdtemp(prefix="render-selfcheck-", dir=base))
    try:
        (tmp / "ok.html").write_text(
            "<!doctype html><meta name=viewport content='width=device-width'>"
            "<body style='margin:16px;background:#fff;font:16px sans-serif'><h1>Rides by week</h1>"
            "<svg viewBox='0 0 300 120' style='width:100%;max-width:600px'>"
            "<rect x='0' y='10' width='240' height='20' fill='#888'/>"
            "<rect x='0' y='40' width='150' height='20' fill='#888'/>"
            "<rect x='0' y='70' width='90' height='20' fill='#d55e00'/></svg>"
            "<button id=t onclick=\"document.body.style.background='#123'\">Tab 2</button></body>")
        (tmp / "wide.html").write_text(
            "<!doctype html><meta name=viewport content='width=device-width'>"
            "<body style='margin:0;background:#fff'><div class='too-wide' style='width:900px;height:50px;"
            "background:#369'>wide</div></body>")
        ok = run(str(tmp / "ok.html"), out=tmp / "out-ok", surfaces=("desktop", "phone", "print"), wait_ms=100,
                 states=[("tab2", ["#t"])])
        assert set(ok["surfaces"]) == {"desktop", "phone", "print", "desktop-tab2", "phone-tab2", "print-tab2"}, ok["surfaces"].keys()
        wide = run(str(tmp / "wide.html"), out=tmp / "out-wide", surfaces=("phone",), wait_ms=100)
        for name, e in ok["surfaces"].items():
            assert "error" not in e, (name, e.get("error"))
            assert Path(e["png"]).stat().st_size > 1000, f"{name} png too small"
            assert not e["blank"], f"{name} rendered blank"
            assert e["overflowPx"] == 0, f"{name} false overflow {e['overflowPx']}"
        we = wide["surfaces"]["phone"]
        assert we["overflowPx"] > 400, f"overflow not detected: {we['overflowPx']}"
        assert any(o["cls"] == "too-wide" for o in we["offenders"]), we["offenders"]
        print("self-check OK: 3 surfaces x 2 states rendered non-blank with no overflow; 900px element flagged "
              f"on phone ({we['overflowPx']}px)")
        return 0
    except AssertionError as exc:
        print(f"self-check FAILED: {exc}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", help="HTML/SVG file or http(s) URL")
    ap.add_argument("--out", help="output dir (default my-lib/runtime/.tmp/YYMMDD-render-<name>)")
    ap.add_argument("--surfaces", default="desktop,slide,phone,print")
    ap.add_argument("--scheme", choices=["light", "dark"], default="light")
    ap.add_argument("--wait", type=int, default=800, help="ms to wait after load for charts to draw")
    ap.add_argument("--full-page", action="store_true", help="also save full-page PNGs")
    ap.add_argument("--state", action="append", default=[], metavar="NAME=SEL[;SEL...]",
                    help="extra state: click these CSS/Playwright selectors in order after load, e.g. "
                         "--state demand='text=Demand' --state crisis='text=Demand;text=Crisis'. Repeatable.")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        return self_check()
    if not a.target:
        ap.error("target required (or --self-check)")
    surfaces = [s.strip() for s in a.surfaces.split(",") if s.strip()]
    bad = [s for s in surfaces if s not in SURFACES]
    if bad:
        ap.error(f"unknown surfaces {bad}; choose from {list(SURFACES)}")
    try:
        states = []
        for st in a.state:
            if "=" not in st:
                ap.error(f"--state needs NAME=SELECTOR[;SELECTOR...]: {st}")
            n, sels = st.split("=", 1)
            states.append((n.strip(), [x.strip() for x in sels.split(";") if x.strip()]))
        rep = run(a.target, a.out, surfaces, a.scheme, a.wait, a.full_page, states)
    except FileNotFoundError as exc:
        print(f"not found: {exc}")
        return 2
    print(summarize(rep))
    return 1 if failed(rep) else 0


if __name__ == "__main__":
    sys.exit(main())
