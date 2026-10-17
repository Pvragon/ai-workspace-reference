#!/usr/bin/env python3
"""Parametric DIMENSION-TRUE side elevation (render-product-image skill).

Geometry exact by construction — this is the "truth" artifact to pair with the
generative "beauty" hero. Renders an SVG (→ use headless Chromium to rasterize).
Generalize freely: any rectangular object with a thin colored layer on one face.

Example (a tile: length 32mm, thickness 0.59x length, colored back layer 0.20x
thickness on the far long edge):
  python3 spec_elevation.py out.html --length-mm 32 --depth-ratio 0.59 \
      --layer-ratio 0.20 --ivory FCF9F1 --layer 7C1D2C \
      --title "OBJECT — side elevation, dimension-true"
Then: chromium --headless=new --screenshot=out.png --window-size=1420,900 \
      --force-device-scale-factor=2 file://out.html
"""
import argparse

def rrect(x, y, w, h, r):
    return (f'M{x+r},{y} h{w-2*r} a{r},{r} 0 0 1 {r},{r} v{h-2*r} '
            f'a{r},{r} 0 0 1 {-r},{r} h{-(w-2*r)} a{r},{r} 0 0 1 {-r},{-r} '
            f'v{-(h-2*r)} a{r},{r} 0 0 1 {r},{-r} z')

def build(length_mm, depth_ratio, layer_ratio, ivory, layer, title, sub):
    L = 900
    T = round(depth_ratio * L)
    LAYER = round(layer_ratio * T)          # colored layer as fraction of THICKNESS
    x0, y0 = 260, 170; x1, y1 = x0 + L, y0 + T; r = 46
    ly = y1 - LAYER                          # colored layer = far long edge (bottom)
    W, H = 1420, 900
    mmpx = length_mm / L
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    s.append(f'''<defs>
     <linearGradient id="iv" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#{ivory}"/><stop offset="1" stop-color="#EFE6D4"/></linearGradient>
     <linearGradient id="ly" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#{layer}"/><stop offset="1" stop-color="#{layer}"/></linearGradient>
     <filter id="sh" x="-30%" y="-30%" width="160%" height="220%"><feGaussianBlur stdDeviation="12"/></filter></defs>''')
    s.append(f'<rect width="{W}" height="{H}" fill="#FBE8DC"/>')
    s.append(f'<ellipse cx="{(x0+x1)//2}" cy="{y1+18}" rx="{L*0.52:.0f}" ry="16" fill="#3a2f26" opacity="0.2" filter="url(#sh)"/>')
    s.append(f'<clipPath id="c"><path d="{rrect(x0,y0,L,T,r)}"/></clipPath>')
    s.append(f'<path d="{rrect(x0,y0,L,T,r)}" fill="url(#iv)"/>')
    s.append(f'<rect x="{x0}" y="{ly}" width="{L}" height="{LAYER}" fill="url(#ly)" clip-path="url(#c)"/>')
    s.append(f'<path d="{rrect(x0,y0,L,T,r)}" fill="none" stroke="#00000018" stroke-width="1.5"/>')
    def t(x, y, txt, sz=26, an='middle', c='#221E1A', w=700, ex=''):
        return f'<text x="{x}" y="{y}" font-family="Atkinson Hyperlegible,sans-serif" font-size="{sz}" font-weight="{w}" fill="{c}" text-anchor="{an}" {ex}>{txt}</text>'
    by = y1 + 74
    s.append(f'<line x1="{x0}" y1="{by}" x2="{x1}" y2="{by}" stroke="#5C524E" stroke-width="2"/>')
    s.append(t((x0+x1)//2, by+34, f"{length_mm:g} mm  (length)"))
    lx = x0 - 62
    s.append(f'<line x1="{lx}" y1="{y0}" x2="{lx}" y2="{y1}" stroke="#5C524E" stroke-width="2"/>')
    s.append(t(lx-16, (y0+y1)//2, f"{length_mm*depth_ratio:.1f} mm  (thickness = {depth_ratio:g} x length)", 26, 'middle', '#221E1A', 700, f'transform="rotate(-90 {lx-16} {(y0+y1)//2})"'))
    rx = x1 + 60
    s.append(f'<line x1="{rx}" y1="{ly}" x2="{rx}" y2="{y1}" stroke="#{layer}" stroke-width="2"/>')
    s.append(t(rx+16, (ly+y1)//2+8, "colored layer", 20, 'start', f'#{layer}', 700))
    s.append(t(rx+16, (ly+y1)//2+34, f"{length_mm*depth_ratio*layer_ratio:.1f} mm ({layer_ratio:g} x thickness)", 16, 'start', f'#{layer}', 400))
    s.append(f'<text x="{x0-62}" y="70" font-family="Fraunces,Georgia,serif" font-style="italic" font-weight="600" font-size="34" fill="#A62639">{title}</text>')
    if sub: s.append(t(x0-62, 104, sub, 18, 'start', '#5C524E', 400))
    s.append('</svg>')
    return '\n'.join(s), (T/L, LAYER/T)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--length-mm", type=float, default=32)
    ap.add_argument("--depth-ratio", type=float, default=0.59)
    ap.add_argument("--layer-ratio", type=float, default=0.20)
    ap.add_argument("--ivory", default="FCF9F1"); ap.add_argument("--layer", default="7C1D2C")
    ap.add_argument("--title", default="Object — side elevation, dimension-true")
    ap.add_argument("--sub", default="dimension-true · geometry exact by construction")
    a = ap.parse_args()
    svg, (dr, lr) = build(a.length_mm, a.depth_ratio, a.layer_ratio, a.ivory, a.layer, a.title, a.sub)
    open(a.out, "w").write('<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@1,144,600&family=Atkinson+Hyperlegible:wght@400;700&display=block" rel="stylesheet">'
        '<style>html,body{margin:0;background:#FBE8DC}</style></head><body>' + svg + '</body></html>')
    print(f"drawn depth/length={dr:.4f} (target {a.depth_ratio})  layer/thickness={lr:.4f} (target {a.layer_ratio})")
