#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: >-
#   Renders a markdown document to a self-contained, branded HTML document for prez.example.com or any
#   standalone deliverable. Runs a humanizer copy gate before rendering, styles only from the composed
#   brand template, fails on off-brand colors or sub-AA contrast, and inlines mermaid diagrams as SVG.
# created: 2026-09-03
# last_updated: 2026-10-07
# maintainer: pvragon
# ---
#
# md_to_branded_html.py — render a markdown document to a self-contained, branded HTML DOCUMENT
# (the html-document template type), suitable for prez.example.com or any standalone deliverable.
#
# Usage:
#   python3 md_to_branded_html.py <input.md> <output.html> [--brand your-brand] [--type html-document]
#       [--diagrams-dir DIR]        # .mmd sources for `<!-- diagram: name -->` markers (else the fence body is rendered)
#       [--captions captions.json]  # {"name": ["Title", "subtitle", scale?]} per diagram; scale (default 1) multiplies the natural width cap
#       [--title TEXT]             # page title (default: the markdown H1)
#       [--eyebrow TEXT] [--lede TEXT] [--meta "item|item|item"] [--accent-words N] [--footer TEXT]
#       [--share-header]            # add <script src="/prez-header.js" defer> (prez.example.com pages only)
#       [--toc]                     # id every H2/H3 and open the article with a Contents card linking to them
#                                   # also opts the page into prez comment threads (document artifacts get comments)
#       [--no-comments]             # with --share-header: no comment threads on this page
#       [--drop-h1]                 # the page header carries the title; do not repeat it in the body (default on)
#       [--no-copy-pass]            # skip the copy gate entirely (non-prose artifacts only)
#       [--copy-ok]                 # build despite copy findings, after a human has read them
#       [--copy-model NAME]         # model for the copy gate (default sonnet)
#
# THE COPY GATE runs BEFORE rendering, on by default: the page's prose (markdown body + the
# --title/--eyebrow/--lede/--meta/--footer chrome) is judged by `claude -p` against the humanizer
# skill and the deliverable-copy stance rule, both loaded verbatim. Findings fail the build and are
# written to <output>.copy-report.json; no HTML is produced. A missing/failed `claude` FAILS the
# build too — a gate that silently passes measures nothing.
#
# Styling comes ONLY from the composed template context/indexed/companies/{brand}/brand/templates/{type}.json
# (compose-branded-template). The build fails on any colour that is not a brand token and on any text pair
# below the template's contrast minimum, so a rendered page cannot drift off-brand or off-AA.
#
# Markdown conventions: `# Title` (page title; frontmatter `version` / `last_updated` feed the meta line);
# `### 1. Step` renders the numeral as a badge; `#### Label` renders as a kicker; a paragraph opening with
# **bold** in the first section renders as a callout; ```mermaid fences (optionally preceded by
# `<!-- diagram: name -->`) become inline SVG figures with a click-to-open zoom/pan viewer.
#
# Requires: python-markdown, Pillow; node + the vendored Chromium/mermaid under
# team-lib/integrations/excalidraw-cli (used by mermaid_svg.mjs).
#
import argparse, base64, datetime, html as _html, io, json, pathlib, re, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = pathlib.Path.home() / 'ai-workspace'
COMPANIES = WORKSPACE / 'team-lib/context/indexed/companies'

# ----------------------------------------------------------------------------------------------------- template

def load_template(brand, ttype):
    p = COMPANIES / brand / 'brand/templates' / f'{ttype}.json'
    if not p.exists():
        sys.exit(f'composed template not found: {p}\n  run: node skills/compose-branded-template/scripts/compose-branded-template.js --brand {brand} --type {ttype}')
    t = json.loads(p.read_text())
    if '_unresolved' in json.dumps(t):
        sys.exit(f'template has unresolved tokenRefs: {p}')
    return t

def hexof(v):
    """composed values are bare 6-hex strings; accept #-prefixed too."""
    if isinstance(v, dict): v = v.get('$value') or v.get('value')
    return str(v).lstrip('#').upper()

def rgb(h):
    h = hexof(h); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def rgba(h, a):
    r, g, b = rgb(h); return f'rgba({r},{g},{b},{a})'

# ------------------------------------------------------------------------------------------------------- assets

def data_uri_png(path, width):
    from PIL import Image
    im = Image.open(path).convert('RGBA')
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

def font_data_uri(t):
    f = HERE / 'assets' / t['htmlSettings']['embeddedFont']['file']
    return 'data:font/woff2;base64,' + base64.b64encode(f.read_bytes()).decode()

# ----------------------------------------------------------------------------------------------------- markdown

def load_markdown(path, drop_h1=True):
    s = path.read_text()
    fm = re.match(r'^---\n(.*?)\n---\n', s, re.S)
    meta = dict(re.findall(r'^(\w+):\s*(.+)$', fm.group(1), re.M)) if fm else {}
    s = s[fm.end():] if fm else s
    diagrams = []   # (name, source_text or None)
    def repl(m):
        name = m.group(1) or f'diagram-{len(diagrams) + 1}'
        diagrams.append((name, m.group(2)))
        return f'\n\n@@DIAGRAM:{name}@@\n\n'
    s = re.sub(r'(?:<!-- diagram: ([\w.\-]+) -->\n)?```mermaid\n(.*?)```\n', repl, s, flags=re.S)
    s = re.sub(r'^<!-- strip(?: end=([^>]*?))? -->\n', lambda m: f'\n@@STRIP:{(m.group(1) or "").strip()}@@\n\n', s, flags=re.M)   # next ordered list -> winding stage strip
    s = re.sub(r'^<!--.*?-->\n?', '', s, flags=re.M | re.S)
    title = None
    m = re.search(r'^# (.*)$', s, re.M)
    if m:
        title = m.group(1).strip()
        if drop_h1: s = s[:m.start()] + s[m.end():]
    return meta, title, s, diagrams

def render_svgs(diagrams, diagrams_dir, workdir):
    """render every diagram to SVG with the native mermaid renderer; returns {name: svg_text}"""
    mmds = []
    for name, body in diagrams:
        src = (diagrams_dir / f'{name}.mmd') if diagrams_dir else None
        if src and src.exists():
            mmds.append(str(src))
        else:
            tmp = workdir / f'{name}.mmd'; tmp.write_text(body); mmds.append(str(tmp))
    out = workdir / 'svg'; out.mkdir(exist_ok=True)
    subprocess.run(['node', str(HERE / 'mermaid_svg.mjs'), str(out), *mmds], check=True)
    return {pathlib.Path(m).stem: (out / f'{pathlib.Path(m).stem}.svg').read_text() for m in mmds}

def figure_html(name, svg, captions):
    # Cap each diagram at its natural width (times an optional per-diagram scale, the third caption
    # element), so a small diagram is never stretched to the full column; a large one still shrinks to fit.
    entry = (captions.get(name) if captions else None) or [name.replace('-', ' '), '']
    scale = float(entry[2]) if len(entry) > 2 else 1.0
    vb = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) [\d.]+"', svg)
    svg = re.sub(r'\sstyle="max-width:[^"]*"', '', svg, count=1)
    svg = re.sub(r'\swidth="[^"]*"', '', svg, count=1)
    svg = re.sub(r'\sheight="[^"]*"', '', svg, count=1)
    if vb:
        svg = svg.replace('<svg', f'<svg style="max-width:{float(vb.group(1)) * scale:.0f}px"', 1)
    title, sub = entry[:2]
    cap = f'<span class="nm">{_html.escape(title)}</span>' + (f'<span class="ds">{_html.escape(sub)}</span>' if sub else '')
    return (f'<figure class="dia" data-name="{name}" data-title="{_html.escape(title)}">'
            f'<figcaption>{cap}</figcaption><div class="canvas">{svg}</div></figure>')

def render_body(md_text, svgs, captions):
    import markdown
    html = markdown.markdown(md_text, extensions=['tables', 'sane_lists', 'smarty'])
    html = re.sub(r'<p>@@DIAGRAM:([\w.\-]+)@@</p>', lambda m: figure_html(m.group(1), svgs[m.group(1)], captions), html)
    html = re.sub(r'<h3>(\d+)\. (.*?)</h3>', r'<h3><span class="num">\1</span>\2</h3>', html)
    # a figure directly under an H4 of the same title keeps only its subtitle
    def _dd(m):
        same = _html.unescape(m.group(2)).replace('’', "'") == _html.unescape(m.group(4)).replace('’', "'")
        return m.group(1) + m.group(3) if same else m.group(0)
    html = re.sub(r'(<h4>(.*?)</h4>\n)(<figure class="dia" [^>]*><figcaption>)<span class="nm">(.*?)</span>', _dd, html)
    html = re.sub(r'<table>(.*?)</table>', r'<div class="table-scroll"><table>\1</table></div>', html, flags=re.S)
    # `<!-- strip [end=Label] -->` before an ordered list of **bold-led** items: a winding row of numbered
    # stage cards (3 per row, rows alternate direction, arrows turn at the row ends; the free cell in
    # the last row holds the end marker). Stacks to one column on narrow screens.
    def _strip(m):
        end = _html.escape(m.group(1) or 'Done')
        items = re.findall(r'<li>(.*?)</li>', m.group(2), re.S)
        n = len(items); cols = 3
        cards = []
        for i, it in enumerate(items):
            lm = re.match(r'\s*<strong>(.*?)</strong>\s*(.*)', it, re.S)
            lead, body = (lm.group(1), lm.group(2)) if lm else ('', it)
            row, k = divmod(i, cols)
            col = k + 1 if row % 2 == 0 else cols - k            # snake: even rows L->R, odd rows R->L
            last = (i == n - 1)
            if last: arrow = 'left' if row % 2 else 'right'
            elif k == cols - 1: arrow = 'down'
            else: arrow = 'right' if row % 2 == 0 else 'left'
            cards.append(f'<div class="stage arr-{arrow}" style="grid-row:{row + 1};grid-column:{col}">'
                         f'<span class="n">{i + 1}</span><div class="lead">{lead}</div><div class="body">{body.strip()}</div></div>')
        row, k = divmod(n - 1, cols)
        if k < cols - 1:   # free cell after the last card gets the end marker
            col = k + 2 if row % 2 == 0 else cols - k - 1
            cards.append(f'<div class="stage end" style="grid-row:{row + 1};grid-column:{col}"><span class="endpill">{end}</span></div>')
        return f'<div class="strip snake" data-count="{n}">' + ''.join(cards) + '</div>'
    html = re.sub(r'<p>@@STRIP:([^@]*)@@</p>\s*<ol>(.*?)</ol>', _strip, html, flags=re.S)
    # bold-led paragraphs in the opening section (up to the second H2) become callouts
    parts = html.split('<h2>')
    if len(parts) > 2:
        parts[1] = re.sub(r'<p>(<strong>)', r'<p class="callout">\1', parts[1])
    elif len(parts) == 2:
        parts[0] = re.sub(r'<p>(<strong>)', r'<p class="callout">\1', parts[0])
    return '<h2>'.join(parts)

def add_toc(html):
    """Give every H2/H3 a stable id and return (html, contents-card html). Ids are slugs of the heading
    text (the H3 number badge dropped), de-duplicated with a numeric suffix, so `[text](#slug)` links in
    the markdown resolve. The card is generated after the copy gate ran and carries no prose of its own."""
    seen = {}
    def slug(text):
        t = re.sub(r'<[^>]+>', '', text); t = _html.unescape(t).lower()
        t = re.sub(r'[^a-z0-9]+', '-', t).strip('-') or 'section'
        n = seen.get(t, 0); seen[t] = n + 1
        return t if n == 0 else f'{t}-{n + 1}'
    entries = []
    def _h(m):
        level, inner = m.group(1), m.group(2)
        sid = slug(re.sub(r'<span class="num">\d+</span>', '', inner))
        label = re.sub(r'<span class="num">(\d+)</span>', r'\1. ', inner)
        entries.append((int(level), sid, label))
        return f'<h{level} id="{sid}">{inner}</h{level}>'
    html = re.sub(r'<h([23])>(.*?)</h\1>', _h, html, flags=re.S)
    if not entries:
        return html, ''
    out = ['<nav class="toc" aria-label="Contents"><div class="toc-h">Contents</div><ol>']
    open_sub = False
    for level, sid, label in entries:
        if level == 2:
            if open_sub: out.append('</ol></li>'); open_sub = False
            elif out[-1].endswith('</a>'): out.append('</li>')
            out.append(f'<li><a href="#{sid}">{label}</a>')
        else:
            if not open_sub:
                if out[-1] == out[0]: out.append('<li>')
                out.append('<ol>'); open_sub = True
            out.append(f'<li><a href="#{sid}">{label}</a></li>')
    if open_sub: out.append('</ol>')
    out.append('</li></ol></nav>')
    return html, ''.join(out)

# ---------------------------------------------------------------------------------------------------------- css

def build_css(t):
    v = t['cssVariables']; ty = t['typography']; bg = t['background']; c = t['components']
    near = hexof(bg['nearBlack']); card = hexof(v['bgCard']); prim = hexof(v['accentPrimary'])
    fam = t['htmlSettings']['embeddedFont']['family']; fb = t['htmlSettings']['embeddedFont'].get('fallbackFamily', 'Arial')
    fam = fam if isinstance(fam, str) else fam.get('$value', 'Noto Sans')
    fb = fb if isinstance(fb, str) else fb.get('$value', 'Arial')
    h2, h3, h4, h1 = ty['h2'], ty['h3'], ty['h4'], ty['h1']
    return f"""
  :root{{
    --accent-primary:#{prim}; --accent-secondary:#{hexof(v['accentSecondary'])}; --heading:#{hexof(v['headingText'])};
    --text-main:#{hexof(v['textMain'])}; --text-muted:#{hexof(v['textMuted'])}; --text-subtle:#{hexof(v['textSubtle'])};
    --bg-body:#{hexof(v['bgBody'])}; --bg-card:#{card}; --near-black:#{near}; --white:#{hexof(v['white'])};
    --line:{rgba(v['textMain'], .08)}; --line-strong:{rgba(v['textMain'], .16)};
    --card:{rgba(card, bg.get('cardAlpha', .97))}; --card-2:{rgba(prim, bg.get('cardTintAlpha', .18))}; --band-soft:{rgba(prim, .45)};
    --sans:"{fam}",system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,{fb},sans-serif;
    --mono:{ty['monospace']};
  }}
  *{{box-sizing:border-box;}}
  html{{scroll-behavior:smooth;color-scheme:dark;}}
  body{{margin:0;background:var(--near-black);color:var(--text-muted);font-family:var(--sans);
    line-height:{ty['body']['lineHeight']};-webkit-font-smoothing:antialiased;font-size:{ty['body']['fontSize']}px;}}
  #wave-bg{{position:fixed;top:0;left:0;width:100%;height:100%;z-index:0;pointer-events:none;}}
  .wrap{{position:relative;z-index:1;max-width:{t['htmlSettings']['contentMaxWidth']}px;margin:0 auto;padding:0 24px 96px;}}
  a{{color:var(--heading);text-decoration-color:var(--accent-secondary);}}
  a:hover{{color:var(--text-main);}}
  h1,h2,h3,h4{{line-height:1.2;letter-spacing:-.015em;text-wrap:balance;}}
  .logo{{display:block;height:{t['logoPlacement']['header']['height']}px;width:auto;}}

  header{{padding:44px 0 30px;border-bottom:{c['rules']['header']['width']}px solid var(--accent-secondary);}}
  header .top{{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;}}
  .eyebrow{{font-family:var(--mono);font-size:{ty['eyebrow']['fontSize']}px;letter-spacing:{ty['eyebrow']['letterSpacing']};text-transform:uppercase;
    color:var(--heading);font-weight:{ty['eyebrow']['fontWeight']};}}
  header h1{{font-size:{h1['fontSize']};font-weight:{h1['fontWeight']};margin:{h1['marginAbove']}px 0 {h1['marginBelow']}px;color:var(--text-main);}}
  header h1 .accent{{color:var(--heading);}}
  header p.lede{{font-size:{ty['lede']['fontSize']}px;color:var(--text-subtle);margin:0;max-width:{ty['lede']['maxWidth']};}}
  header .meta{{margin-top:20px;font-family:var(--mono);font-size:12.5px;color:var(--text-subtle);display:flex;flex-wrap:wrap;gap:8px 18px;}}

  /* heading rhythm: space ABOVE a heading is {ty['headingRhythm']['aboveToBelowRatio']}x the space BELOW it at every level */
  article h2{{font-size:{h2['fontSize']}px;font-weight:{h2['fontWeight']};margin:{h2['marginAbove']}px 0 {h2['marginBelow']}px;color:var(--heading);}}
  article h2:first-child{{margin-top:{h2['firstMarginAbove']}px;}}
  article h3{{font-size:{h3['fontSize']}px;font-weight:{h3['fontWeight']};margin:{h3['marginAbove']}px 0 {h3['marginBelow']}px;color:var(--heading);}}
  article h3 .num{{display:inline-flex;align-items:center;justify-content:center;
    width:{h3['numberBadge']['size']}px;height:{h3['numberBadge']['size']}px;border-radius:{h3['numberBadge']['borderRadius']}px;
    background:var(--card-2);border:1px solid {rgba(v['headingText'], .35)};color:var(--heading);
    font-family:var(--mono);font-size:15px;font-weight:700;margin-right:12px;vertical-align:4px;}}
  article h4{{font-size:{h4['fontSize']}px;font-weight:{h4['fontWeight']};letter-spacing:{h4['letterSpacing']};text-transform:uppercase;
    margin:{h4['marginAbove']}px 0 {h4['marginBelow']}px;color:var(--heading);display:flex;align-items:center;gap:10px;}}
  article h4::before{{content:"";display:inline-block;width:{h4['kickerDash']['width']}px;height:{h4['kickerDash']['height']}px;border-radius:2px;background:var(--accent-secondary);}}
  article h2,article h3{{scroll-margin-top:84px;}}
  nav.toc{{background:var(--card-2);border:1px solid var(--line);border-radius:10px;padding:18px 22px 14px;margin:30px 0 6px;}}
  nav.toc .toc-h{{font-family:var(--mono);font-size:12.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--heading);font-weight:700;margin:0 0 10px;}}
  nav.toc ol{{margin:0;padding-left:0;list-style:none;}}
  nav.toc li{{margin:0 0 6px;}}
  nav.toc ol ol{{margin:5px 0 2px;padding-left:22px;}}
  nav.toc li{{padding-left:0;}}
  nav.toc ol ol li{{margin:0 0 3px;font-size:.94em;}}
  nav.toc a{{color:var(--text-main);text-decoration:none;border-bottom:1px solid var(--line);}}
  nav.toc a:hover{{color:var(--heading);border-bottom-color:var(--heading);}}
  article p{{margin:0 0 14px;}}
  article strong{{color:var(--text-main);font-weight:700;}}
  article ul,article ol{{margin:0 0 16px;padding-left:26px;}}
  article li{{margin:0 0 7px;}}
  article li::marker{{color:var(--heading);font-weight:700;}}
  article code{{font-family:var(--mono);font-size:.9em;background:var(--card-2);border:1px solid var(--line);border-radius:5px;padding:1px 6px;color:var(--text-main);}}
  article > p.callout{{background:var(--card-2);border:1px solid {rgba(v['headingText'], .25)};
    border-left:{c['callout']['borderLeft']['width']}px solid var(--accent-secondary);border-radius:{c['callout']['borderRadius']}px;padding:14px 18px;}}

  /* stage strip (winding): 3 columns, rows alternate direction, orange arrows turn at the row ends */
  .strip{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:1fr;gap:18px 22px;margin:18px 0 26px;}}
  .stage{{position:relative;background:var(--card);border:1px solid var(--line);border-top:3px solid var(--accent-secondary);
    border-radius:10px;padding:14px 16px 16px;}}
  .stage::after{{content:"";position:absolute;border:7px solid transparent;}}
  .stage.arr-right::after{{right:-15px;top:50%;transform:translateY(-50%);border-left:8px solid var(--accent-secondary);}}
  .stage.arr-left::after{{left:-15px;top:50%;transform:translateY(-50%);border-right:8px solid var(--accent-secondary);}}
  .stage.arr-down::after{{left:50%;bottom:-15px;transform:translateX(-50%);border-top:8px solid var(--accent-secondary);}}
  .stage .n{{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:7px;
    background:var(--card-2);border:1px solid {rgba(v['headingText'], .35)};color:var(--heading);font-family:var(--mono);font-size:13px;font-weight:700;}}
  .stage .lead{{color:var(--heading);font-weight:700;font-size:15.5px;line-height:1.3;margin:10px 0 6px;}}
  .stage .body{{font-size:14px;line-height:1.5;color:var(--text-muted);}}
  .stage.end{{display:flex;align-items:center;justify-content:center;background:none;border:0;padding:0;}}
  .stage.end::after{{display:none;}}
  .endpill{{display:flex;align-items:center;justify-content:center;width:100%;height:56px;font-family:var(--mono);font-size:15px;font-weight:700;
    letter-spacing:.14em;text-transform:uppercase;color:var(--heading);background:var(--card-2);
    border:1px solid {rgba(v['headingText'], .35)};border-radius:999px;}}
  @media (max-width:760px){{
    .strip{{grid-template-columns:1fr;gap:18px;}}
    .stage{{grid-row:auto !important;grid-column:auto !important;}}
    .stage::after{{left:50% !important;right:auto !important;top:auto !important;bottom:-15px !important;transform:translateX(-50%) !important;
      border:7px solid transparent !important;border-top:8px solid var(--accent-secondary) !important;}}
    .stage.end{{order:99;}}
  }}
  table{{border-collapse:collapse;width:100%;margin:0 0 22px;font-size:15.5px;background:var(--card);border:1px solid var(--line);}}
  .table-scroll{{overflow-x:auto;margin:0 0 22px;border-radius:10px;border:1px solid var(--line);}}
  .table-scroll table{{margin:0;min-width:{c['table']['scrollsHorizontallyBelow']}px;border:0;}}
  thead th{{background:var(--accent-primary);color:var(--text-main);text-align:left;padding:11px 14px;font-weight:700;}}
  tbody td{{padding:11px 14px;border-top:1px solid var(--line);vertical-align:top;color:var(--text-muted);}}
  tbody td:first-child{{color:var(--text-main);white-space:nowrap;font-weight:600;}}
  tbody tr:nth-child(even) td{{background:var(--card-2);}}

  figure.dia{{margin:0 0 26px;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:0 25px 60px -12px rgba(0,0,0,.7);}}
  p + figure.dia, ul + figure.dia, ol + figure.dia{{margin-top:20px;}}
  figure.dia figcaption{{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;padding:12px 18px;background:var(--band-soft);border-bottom:1px solid {rgba(v['headingText'], .25)};}}
  figure.dia .nm{{font-size:15.5px;font-weight:700;color:var(--heading);}}
  figure.dia .ds{{font-size:14px;color:var(--text-muted);opacity:.75;}}
  .canvas{{background:var(--white);padding:14px;cursor:zoom-in;position:relative;}}
  .canvas svg{{display:block;height:auto;margin:0 auto;width:100%;max-width:none;}}
  .canvas .tap{{position:absolute;right:12px;bottom:12px;font:600 11.5px/1 var(--sans);color:var(--text-subtle);background:var(--white);
    border:1px solid {rgba(prim, .25)};border-radius:999px;padding:6px 12px;pointer-events:none;opacity:.94;}}
  .canvas:hover .tap{{color:var(--accent-primary);border-color:var(--accent-secondary);}}
  /* Mermaid HTML labels live in foreignObject and were measured under browser defaults; reset there so page styles cannot clip them */
  svg foreignObject, svg foreignObject *{{line-height:normal;box-sizing:content-box;}}

  .viewer{{position:fixed;inset:0;z-index:9999;background:var(--bg-body);display:flex;flex-direction:column;}}
  .viewer[hidden]{{display:none;}}
  .viewer-bar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:11px 16px;background:var(--bg-body);border-bottom:2px solid var(--accent-secondary);}}
  .viewer-bar .vtitle{{font-weight:700;font-size:15px;margin-right:6px;color:var(--heading);}}
  .zbtn{{font:600 12.5px/1 var(--sans);color:var(--text-muted);background:var(--card-2);border:1px solid var(--line-strong);border-radius:8px;padding:8px 12px;cursor:pointer;}}
  .zbtn:hover{{color:var(--text-main);border-color:var(--accent-secondary);}}
  .zbtn:focus-visible{{outline:2px solid var(--accent-secondary);outline-offset:1px;}}
  .zbtn.close{{margin-left:auto;}}
  .zlevel{{font-family:var(--mono);font-size:12px;color:var(--text-subtle);min-width:48px;text-align:center;font-variant-numeric:tabular-nums;}}
  .viewer-stage{{flex:1;overflow:hidden;background:var(--white);position:relative;cursor:grab;touch-action:none;}}
  .viewer-stage.grabbing{{cursor:grabbing;}}
  .viewer-stage .pan{{position:absolute;top:0;left:0;transform-origin:0 0;}}
  .viewer-stage .pan svg{{display:block;width:100%;height:auto;max-width:none;}}
  .viewer-hint{{padding:8px 16px;background:var(--bg-body);border-top:1px solid var(--line);font-size:12px;color:var(--text-subtle);}}
  body.viewing{{overflow:hidden;}}

  footer{{margin-top:64px;padding-top:22px;border-top:{c['rules']['footer']['width']}px solid var(--accent-secondary);font-size:13.5px;color:var(--text-subtle);}}
  footer p{{margin:0 0 7px;}}
  footer .mono{{font-family:var(--mono);font-size:12px;overflow-wrap:anywhere;}}
  @media (max-width:{ty['bodyMobile']['breakpoint']}px){{ body{{font-size:{ty['bodyMobile']['fontSize']}px;}} header{{padding-top:28px;}} article h2{{font-size:{h2['fontSize'] - 4}px;}} }}
  @media (prefers-reduced-motion:reduce){{ #wave-bg{{display:none;}} }}
"""

# ----------------------------------------------------------------------------------------------------------- js

def build_wave_js(t):
    w = t['background']['waveCanvas']
    if not w.get('enabled', True): return ''
    layers = '\n'.join(f"    drawWave(h * {L['yPosition']}, {L['amplitude']}, {L['wavelength']}, {L['speed']}, '{rgba(L['color'], L['alpha'])}');" for L in w['layers'])
    sky = w['topSky']
    return f"""
(function () {{
  var canvas = document.getElementById('wave-bg'); if (!canvas) return;
  if ({'true' if w.get('respectsReducedMotion', True) else 'false'} && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var ctx = canvas.getContext('2d'), w, h, time = 0;
  function resize() {{ w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight; }}
  window.addEventListener('resize', resize); window.addEventListener('orientationchange', resize); resize();
  function drawWave(yBase, amplitude, wavelength, speed, color) {{
    ctx.beginPath(); ctx.moveTo(0, h);
    for (var x = 0; x <= w; x += 2) {{
      var y = yBase + Math.sin((x / wavelength) + (time * speed)) * amplitude
        + Math.sin((x / (wavelength * 0.6)) + (time * speed * 0.7)) * (amplitude * 0.4)
        + Math.cos((x / (wavelength * 1.8)) + (time * speed * 0.3)) * (amplitude * 0.25);
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }}
    ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath(); ctx.fillStyle = color; ctx.fill();
  }}
  function draw() {{
    time += {w.get('timeStep', 0.008)}; ctx.clearRect(0, 0, w, h);
{layers}
    ctx.beginPath();
    for (var x = 0; x <= w; x += 2) {{
      var y = h * {sky['yPosition']} + Math.sin((x / {sky['wavelength']}) + (time * {sky['speed']})) * {sky['amplitude']} + Math.cos((x / 350) + (time * 0.15)) * 12;
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }}
    ctx.lineTo(w, 0); ctx.lineTo(0, 0); ctx.closePath(); ctx.fillStyle = '{rgba(sky['color'], sky['alpha'])}'; ctx.fill();
    requestAnimationFrame(draw);
  }}
  draw();
}})();
"""

VIEWER_JS = (HERE / 'viewer.js').read_text() if (HERE / 'viewer.js').exists() else ''

# --------------------------------------------------------------------------------------------------- copy gate

HUMANIZER_SKILL = WORKSPACE / 'team-lib/skills/_external/blader-humanizer/SKILL.md'
STANCE_CONTEXT = WORKSPACE / 'team-lib/skills/humanizer-supplement/SKILL.md'
COPY_MODEL_DEFAULT = 'sonnet'
COPY_TIMEOUT = 240          # seconds; the judge is one turn over ~30-60 KB of prompt

COPY_SYSTEM = ('You are a copy reviewer for a branded deliverable. You read reference material and a body of '
               'copy, and you answer with STRICT JSON only — no prose, no markdown fences, no commentary.')

COPY_INSTRUCTION = """
=== YOUR TASK ===

Above you have two references and one body of COPY.

Work through the COPY sentence by sentence — every sentence, including headings, table cells and
the Title/Eyebrow/Lede/Meta/Footer lines at the end. For each one, run both checks before moving on:

  (a) the humanizer skill — the vocabulary and construction tells of machine writing;
  (b) the stance rule — ask its test question, "is this sentence about the subject, or about the
      document?", and check it against all three patterns: explaining the document's own conventions,
      structure or navigation (S1); narrating the method, the sourcing or how the document was
      built (S2); flourish where a plain label was the job (S3). The knowing aside that closes a
      paragraph now lives in the humanizer skill as pattern 2.

Flag only REAL instances you can point at with a verbatim quote from the COPY. Do not flag style
preferences, do not flag things you would merely have written differently, and do not invent a
quote. A short factual label, a plain heading, a caveat that changes what the reader DOES, and a
dry aside about the SUBJECT are all fine and must not be flagged.

Return STRICT JSON and nothing else, in exactly this shape:

{"findings":[{"quote":"<verbatim sentence or fragment from the COPY>","rule":"humanizer:<pattern name>|stance:<shape 1-4>","why":"<one line>","rewrite":"<proposed replacement, or empty string to cut it>"}]}

- "rule" is either "humanizer:<pattern name>" (e.g. "humanizer:em dash overuse") or
  "stance:<shape N>" (e.g. "stance:shape 3") — one rule per finding, the primary one.
- "rewrite" is "" when the right fix is to delete the sentence outright.
- If the copy is clean, return exactly {"findings":[]}.
"""


def copy_prose(md_text, chrome):
    """The prose a reader actually reads: the markdown body with markup, code, diagrams and raw HTML
    tags removed (tag TEXT is kept, table cells become sentences), plus the page-chrome strings."""
    s = md_text
    s = re.sub(r'@@DIAGRAM:[\w.\-]+@@|@@STRIP:[^@]*@@', '', s)
    s = re.sub(r'^```.*?^```', '', s, flags=re.S | re.M)          # fenced code
    s = re.sub(r'^(?: {4}|\t)\S.*$', '', s, flags=re.M)           # indented code
    s = re.sub(r'<!--.*?-->', '', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)                                # raw HTML tags, text kept
    s = re.sub(r'`([^`]*)`', r'\1', s)
    s = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', s)                    # images
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)                # links -> text
    lines = []
    for ln in s.splitlines():
        ln = ln.strip()
        if not ln: continue
        if re.match(r'^\|?[\s:|-]+\|[\s:|-]*$', ln): continue     # table rule row
        if ln.startswith('|'):                                    # table row -> cells as sentences
            cells = [c.strip() for c in ln.strip('|').split('|') if c.strip()]
            ln = '. '.join(cells)
        ln = re.sub(r'^\s*#{1,6}\s*', '', ln)                     # heading marks (the text is copy too)
        ln = re.sub(r'^\s*(?:[-*+]|\d+\.)\s+', '', ln)            # list markers
        ln = re.sub(r'^\s*>\s?', '', ln)                          # blockquote
        ln = re.sub(r'\*\*|__|(?<!\w)[*_](?!\s)', '', ln)         # emphasis marks
        ln = _html.unescape(ln).strip()
        if ln: lines.append(ln)
    for label, value in chrome:
        v = _html.unescape(re.sub(r'<[^>]+>', ' ', value or '')).strip()
        if v: lines.append(f'{label}: {v}')
    return '\n'.join(lines)


def sentence_count(prose):
    return len([x for x in re.split(r'(?<=[.!?])\s+|\n', prose) if x.strip()])


def run_copy_pass(prose, model, timeout=COPY_TIMEOUT):
    """Judge the prose with `claude -p` against the humanizer skill + the stance rule.
    Returns (findings, seconds). Exits the build on any failure to actually run the judge."""
    for p in (HUMANIZER_SKILL, STANCE_CONTEXT):
        if not p.exists():
            sys.exit(f'COPY PASS CANNOT RUN: missing reference {p}\n  (pass --no-copy-pass only for non-prose artifacts)')
    prompt = (f'=== REFERENCE 1 — HUMANIZER SKILL (verbatim) ===\n{HUMANIZER_SKILL.read_text()}\n\n'
              f'=== REFERENCE 2 — DELIVERABLE COPY STANCE RULE (verbatim) ===\n{STANCE_CONTEXT.read_text()}\n\n'
              f'=== COPY UNDER REVIEW ===\n{prose}\n\n{COPY_INSTRUCTION}')
    cmd = ['claude', '-p', '--output-format', 'json', '--model', model,
           '--tools', '', '--setting-sources', '', '--system-prompt', COPY_SYSTEM]
    t0 = datetime.datetime.now()
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        sys.exit('COPY PASS CANNOT RUN: `claude` is not on PATH. Fix it, or pass --no-copy-pass for a non-prose artifact.')
    except subprocess.TimeoutExpired:
        sys.exit(f'COPY PASS TIMED OUT after {timeout}s (model {model}). A gate that silently passes measures nothing — '
                 'rerun, or pass --no-copy-pass deliberately.')
    secs = (datetime.datetime.now() - t0).total_seconds()
    if r.returncode != 0:
        sys.exit(f'COPY PASS FAILED: claude exited {r.returncode}\n{(r.stderr or r.stdout)[:800]}')
    try:
        text = json.loads(r.stdout)['result']
    except Exception:
        sys.exit(f'COPY PASS FAILED: could not parse the claude envelope\n{r.stdout[:800]}')
    m = re.search(r'\{.*\}', text, re.S)                          # tolerate a fence or a stray sentence around it
    if not m:
        sys.exit(f'COPY PASS FAILED: the judge returned no JSON\n{text[:800]}')
    try:
        findings = json.loads(m.group(0)).get('findings', [])
    except Exception:
        sys.exit(f'COPY PASS FAILED: the judge returned malformed JSON\n{m.group(0)[:800]}')
    return findings, secs


def copy_gate(md_text, chrome, out_path, a):
    """Run the copy gate and act on it. Returns when the build may continue; exits otherwise."""
    prose = copy_prose(md_text, chrome)
    n = sentence_count(prose)
    findings, secs = run_copy_pass(prose, a.copy_model)
    if not findings:
        print(f'copy pass: clean ({n} sentences checked, {a.copy_model}, {secs:.0f}s)')
        return
    for f in findings:
        print(f'COPY {f.get("rule", "?")} | "{f.get("quote", "")}" -> "{f.get("rewrite", "")}" ({f.get("why", "")})')
    rep = pathlib.Path(str(out_path) + '.copy-report.json')
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({'input': str(a.input), 'output': str(out_path), 'model': a.copy_model,
                               'seconds': round(secs, 1), 'sentences_checked': n,
                               'acknowledged': bool(a.copy_ok), 'checked': datetime.datetime.now().isoformat(timespec='seconds'),
                               'findings': findings}, indent=2) + '\n')
    if a.copy_ok:
        print(f'copy pass: {len(findings)} finding(s) ACKNOWLEDGED via --copy-ok; report {rep}')
        return
    sys.exit(f'COPY PASS FAILED: {len(findings)} finding(s); report written to {rep}\n'
             '  Fix the copy, or pass --copy-ok once a human has read the report.')

# ------------------------------------------------------------------------------------------------------- gates

def validate(html, t, brand):
    tokens = json.loads((COMPANIES / brand / 'brand/brand-tokens.json').read_text())
    allowed = set(m.upper() for m in re.findall(r'#([0-9A-Fa-f]{6})\b', json.dumps(tokens))) | {hexof(t['background']['nearBlack'])}
    css = html[html.index('<style>'):html.index('</style>')]
    js = html[html.index('</article>'):]
    bad = sorted(set(m.upper() for m in re.findall(r'#([0-9A-Fa-f]{6})\b', css)) - allowed)
    triples = set(re.findall(r'rgba?\((\d+),\s*(\d+),\s*(\d+)', css + js))
    badrgb = sorted(x for x in triples if '%02X%02X%02X' % tuple(map(int, x)) not in allowed and x != ('0', '0', '0'))
    if bad or badrgb:
        sys.exit(f'OFF-TOKEN COLOURS: hex={bad} rgb={badrgb}')
    def lum(h):
        r, g, b = [c / 255 for c in rgb(h)]
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    def ratio(fg, bg):
        a, b = sorted([lum(fg), lum(bg)], reverse=True); return (a + 0.05) / (b + 0.05)
    v = dict(t['cssVariables']); v['nearBlack'] = t['background']['nearBlack']
    fails = []
    for pair in t['accessibility']['contrastGate']:
        r = ratio(v[pair['fg']], v[pair['bg']])
        print(f"  contrast {pair['name']:26s} #{hexof(v[pair['fg']])} on #{hexof(v[pair['bg']])}: {r:5.2f}:1  (min {pair['min']})")
        if r < pair['min']: fails.append((pair['name'], round(r, 2), pair['min']))
    if fails: sys.exit(f'CONTRAST FAIL: {fails}')
    return len(allowed)

# -------------------------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input'); ap.add_argument('output')
    ap.add_argument('--brand', default='your-brand'); ap.add_argument('--type', default='html-document')
    ap.add_argument('--diagrams-dir'); ap.add_argument('--captions')
    ap.add_argument('--title'); ap.add_argument('--eyebrow', default=''); ap.add_argument('--lede', default=''); ap.add_argument('--meta', default='')
    ap.add_argument('--accent-words', type=int, default=0); ap.add_argument('--footer', default='')
    ap.add_argument('--share-header', action='store_true'); ap.add_argument('--keep-h1', action='store_true')
    ap.add_argument('--toc', action='store_true', help='id every H2/H3 and open the article with a Contents card')
    ap.add_argument('--no-comments', action='store_true',
                    help='suppress the prez comment-threads opt-in meta tag (emitted by default with --share-header)')
    ap.add_argument('--no-copy-pass', action='store_true',
                    help='skip the copy gate entirely (non-prose artifacts only)')
    ap.add_argument('--copy-ok', action='store_true',
                    help='build despite copy findings, after a human has read the report')
    ap.add_argument('--copy-model', default=COPY_MODEL_DEFAULT,
                    help=f'model for the copy gate (default {COPY_MODEL_DEFAULT})')
    a = ap.parse_args()

    t = load_template(a.brand, a.type)
    brand_dir = COMPANIES / a.brand / 'brand'
    meta, title, md_text, diagrams = load_markdown(pathlib.Path(a.input), drop_h1=not a.keep_h1)
    title = a.title or title or meta.get('title') or pathlib.Path(a.input).stem

    if not a.no_copy_pass:      # BEFORE rendering: a failing gate must not leave an HTML behind
        copy_gate(md_text, [('Title', title), ('Eyebrow', a.eyebrow), ('Lede', a.lede),
                            ('Meta', a.meta), ('Footer', a.footer)], pathlib.Path(a.output), a)

    captions = json.loads(pathlib.Path(a.captions).read_text()) if a.captions else {}
    with tempfile.TemporaryDirectory(prefix='branded-html-') as td:
        svgs = render_svgs(diagrams, pathlib.Path(a.diagrams_dir) if a.diagrams_dir else None, pathlib.Path(td)) if diagrams else {}
    body = render_body(md_text, svgs, captions)
    if a.toc:
        body, toc = add_toc(body)
        body = toc + body

    words = title.split()
    if a.accent_words and len(words) > a.accent_words:
        title_html = _html.escape(' '.join(words[:-a.accent_words])) + ' <span class="accent">' + _html.escape(' '.join(words[-a.accent_words:])) + '</span>'
    else:
        title_html = _html.escape(title)
    meta_items = [m.strip() for m in a.meta.split('|') if m.strip()] if a.meta else [x for x in [
        f"Version {meta['version']}" if meta.get('version') else '', f"Updated {meta['last_updated']}" if meta.get('last_updated') else ''] if x]
    logo = brand_dir / t['logoPlacement']['header']['asset']
    fav = brand_dir / t['logoPlacement']['favicon']['asset']
    font = t['htmlSettings']['embeddedFont']
    fam = font['family'] if isinstance(font['family'], str) else font['family'].get('$value', 'Noto Sans')

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{'<meta name="prez-comments" content="on">' if (a.share_header and not a.no_comments) else ''}
<title>{_html.escape(title)}</title>
<link rel="icon" href="{data_uri_png(fav, 64)}">
<style>
@font-face{{font-family:'{fam}';src:url({font_data_uri(t)}) format('woff2');font-weight:{font['weightRange'][0]} {font['weightRange'][1]};font-style:normal;font-display:swap;}}
{build_css(t)}</style>
</head>
<body>
<canvas id="wave-bg" aria-hidden="true"></canvas>
<div class="wrap">

<header>
  <div class="top">
    <div class="eyebrow">{a.eyebrow}</div>
    <img class="logo" alt="{_html.escape(a.brand.title())}" src="{data_uri_png(logo, 420)}">
  </div>
  <h1>{title_html}</h1>
  {f'<p class="lede">{a.lede}</p>' if a.lede else ''}
  <div class="meta">{''.join(f'<span>{_html.escape(m)}</span>' for m in meta_items)}</div>
</header>

<article>
{body}
</article>

<footer>
  {f'<p>{a.footer}</p>' if a.footer else ''}
  <p class="mono">Internal &middot; {_html.escape(a.brand.title())} &middot; built {datetime.date.today().isoformat()}</p>
</footer>

</div>
<script>{build_wave_js(t)}</script>
<script>{VIEWER_JS}</script>
{'<script src="/prez-header.js" defer></script>' if a.share_header else ''}
</body>
</html>
"""
    n = validate(html, t, a.brand)
    out = pathlib.Path(a.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(html)
    print(f'token check passed ({n} allowed colours); wrote {out} ({len(html) / 1024:.0f} KB), diagrams: {len(svgs)}')

if __name__ == '__main__':
    main()
