"""deals — command-line entrypoint.

  deals init                          scaffold central user config (~/.config/deals)
  deals refresh-auth --site offerup   (re)provision the site's device token
  deals scrape --query "gaming pc"    feed sweep -> detail -> filters -> CSV catalog
  deals export [--format csv]         re-emit the latest catalog
  deals ls [--under N] [--since 2mo]  quick filtered view of a catalog

No defaults live in this code — operational defaults come from the user config
(deals init). Build order steps 2-4 (SPEC).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from . import (__version__, config, auth as auth_mod, catalog, filters,
               diff as diffmod, cache as cache_mod, packs as packs_mod,
               watchstate, notify as notify_mod)
from .adapters import get_adapter_cls, available_sites
from .geo import geocode_zip


def _err(msg: str) -> int:
    print(f"deals: {msg}", file=sys.stderr)
    return 1


# --- argparse type validators (fail cleanly at parse time, before any I/O) ---
def _pos_int(s: str) -> int:
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s!r} is not an integer")
    if v < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return v


def _nonneg_int(s: str) -> int:
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s!r} is not an integer")
    if v < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return v


def _pos_float(s: str) -> float:
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s!r} is not a number")
    if v <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return v


def _age_spec(s: str) -> str:
    """Validate an age spec (e.g. 2mo, 30d) at parse time; return it unchanged."""
    try:
        filters.parse_age(s)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    return s


def _validate_out_path(path: str) -> None:
    p = Path(path)
    if p.is_dir():
        raise ValueError(f"output path is a directory: {path}")
    parent = p.parent
    if parent and not parent.exists():
        raise ValueError(f"output directory does not exist: {parent}")


# --------------------------------------------------------------------------- init
def cmd_init(args) -> int:
    path = config.config_path()
    if path.exists() and not args.force:
        return _err(f"config already exists at {path} (use --force to overwrite)")

    def ask(prompt, default):
        if args.yes:
            return default
        try:
            v = input(f"{prompt} [{default}]: ").strip()
        except EOFError:           # non-interactive / piped stdin -> take default
            return default
        return v or default

    zipcode = (args.zip or ask("Default ZIP code", "")).strip()
    if not zipcode:
        return _err("a ZIP code is required (pass --zip or answer the prompt)")

    radius = args.radius if args.radius is not None else ask("Default radius (mi)", "40")
    try:
        radius = float(radius)
        if radius <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _err(f"radius must be a positive number (got {radius!r})")

    max_age = (args.max_age or ask("Default max listing age", "2mo")).strip()
    try:
        filters.parse_age(max_age)
    except ValueError as e:
        return _err(str(e))

    site = args.site or ask("Default marketplace", "offerup")

    lat, lon, name = args.lat, args.lon, ""
    if lat is None or lon is None:
        print(f"resolving {zipcode} -> lat/lon ...", file=sys.stderr)
        geo = geocode_zip(zipcode)
        if geo:
            lat, lon, name = geo
            print(f"  {name}: {lat}, {lon}", file=sys.stderr)
        else:
            return _err(f"could not geocode {zipcode}; pass --lat/--lon manually")

    text = config.CONFIG_TEMPLATE.format(
        created=datetime.now().date().isoformat(),   # local date
        zip=zipcode, lat=lat, lon=lon, name=name,
        radius_mi=int(float(radius)), max_age=max_age, site=site,
        catalogs_dir=str(config.catalogs_dir()),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    auth_mod.ensure(site)  # mint token now so the first scrape needs no extra step
    print(f"wrote {path}")
    print(f"minted {site} auth at {auth_mod.auth_path()}")
    print('ready — try:  deals scrape --query "<your search>"')
    return 0


# -------------------------------------------------------------------- refresh-auth
def cmd_refresh_auth(args) -> int:
    site = args.site or _cfg_site_or(None)
    if not site:
        return _err("specify --site")
    rec = auth_mod.refresh(site)
    tok = rec.get("x-ou-d-token", "")
    print(f"refreshed {site} auth -> {auth_mod.auth_path()}")
    print(f"  device token: {tok[:12]}…{tok[-4:]} ({len(tok)} chars)")
    return 0


def _cfg_site_or(default):
    try:
        return config.load().site
    except config.ConfigError:
        return default


# ------------------------------------------------------------------------- scrape
def _progress(kind, q, n, m):
    if kind == "feed":
        print(f"  [feed] {q!r}: page {n}, {m} unique so far", file=sys.stderr)
    elif kind == "cache":
        print(f"  [cache] {n} served from cache, {m} to fetch", file=sys.stderr)
    else:
        print(f"  [detail] {n} fetched, {m} ok", file=sys.stderr)


def cmd_scrape(args) -> int:
    try:
        cfg = config.load()
    except config.ConfigError as e:
        return _err(str(e))

    site = args.site or cfg.site
    radius = float(args.radius) if args.radius is not None else cfg.radius_mi
    max_age = args.max_age or cfg.max_age
    zipcode = args.location or cfg.zip
    lat, lon = cfg.lat, cfg.lon
    # if the user overrode location, re-resolve lat/lon for distance localization
    if args.location and args.location != cfg.zip:
        geo = geocode_zip(args.location)
        if geo:
            lat, lon, _ = geo
        else:
            return _err(f"could not geocode override location {args.location}")

    queries = _collect_queries(args)
    if not queries:
        return _err("provide --query or --queries-file")

    detail = not args.fast

    # --- validate everything CHEAP before paying for the network scrape ---
    if detail:
        try:
            filters.parse_age(max_age)
        except ValueError as e:
            return _err(f"{e} (config defaults.max_age or --max-age)")
    if args.out:
        _validate_out_path(args.out)               # raises ValueError -> caught upstream
    else:
        cd = cfg.catalogs_dir
        if cd.exists() and not cd.is_dir():
            return _err(f"configured catalogs_dir is not a directory: {cd} (fix config.toml)")
        cd.mkdir(parents=True, exist_ok=True)
    if (args.max_price is not None and args.min_price is not None
            and args.min_price > args.max_price):
        print(f"  warning: price band is empty "
              f"(--min-price {args.min_price} > --max-price {args.max_price}) "
              f"— nothing will match", file=sys.stderr)

    auth = auth_mod.ensure(site)
    adapter = get_adapter_cls(site)(auth, lat, lon, zipcode,
                                    rps=args.rps, cache=not args.no_cache,
                                    refresh=args.refresh)

    print(f"scraping {site}: queries={queries} radius={radius}mi "
          f"max_age={max_age} detail={detail} enrich={args.enrich}", file=sys.stderr)

    # cheap pre-filter on price band before paying for details
    pre = None
    if args.max_price is not None or args.min_price is not None:
        lo = args.min_price if args.min_price is not None else float("-inf")
        hi = args.max_price if args.max_price is not None else float("inf")
        pre = lambda L: (L.price is not None and lo <= L.price <= hi)  # noqa: E731

    listings = adapter.scrape(queries, radius, enrich=args.enrich, detail=detail,
                              max_pages=args.max_pages, concurrency=args.concurrency,
                              pre_filter=pre, progress=_progress)
    n_raw = len(listings)
    if getattr(adapter, "last_throttled", False):
        print("  WARNING: detail endpoint throttled — partial results written "
              "(fetched details are cached; re-run to resume from cache).",
              file=sys.stderr)

    # post-filters (radius always; age only when we have posted_at i.e. detail ran)
    kept, dropped = filters.apply(
        listings,
        radius_mi=radius if detail else None,   # distance is detail-only
        max_age=max_age if detail else None,
    )
    print(f"  scraped {n_raw} -> kept {len(kept)} "
          f"(dropped radius={dropped['radius']} age={dropped['age']})", file=sys.stderr)
    if not detail:
        print("  (--fast: no detail fetch -> no radius/age/price-drop filtering)", file=sys.stderr)

    out = Path(args.out) if args.out else catalog.default_path(
        cfg.catalogs_dir, site, queries[0])
    catalog.write(kept, out)
    n_drops = sum(1 for L in kept if L.price_dropped)
    print(f"wrote {len(kept)} listings -> {out}")
    if detail:
        print(f"  {n_drops} have a price drop")
    return 0


def _collect_queries(args) -> list:
    qs = []
    if args.query:
        qs.extend(args.query)
    if args.queries_file:
        qf = Path(args.queries_file)
        if not qf.exists():
            raise ValueError(f"queries file not found: {args.queries_file}")
        for line in qf.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                qs.append(line)
    # dedup, preserve order
    seen, out = set(), []
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


# ------------------------------------------------------------------------- export
def cmd_export(args) -> int:
    if args.format != "csv":
        return _err(f"format {args.format!r} not supported yet (csv only)")
    src = _resolve_catalog(args)
    if isinstance(src, int):
        return src
    if args.out:
        _validate_out_path(args.out)
    rows = catalog.read(src)
    out = Path(args.out) if args.out else None
    if out:
        catalog.write(rows, out)
        print(f"exported {len(rows)} rows -> {out}")
    else:
        # passthrough to stdout
        sys.stdout.write(src.read_text())
    return 0


# ----------------------------------------------------------------------------- ls
def cmd_ls(args) -> int:
    src = _resolve_catalog(args)
    if isinstance(src, int):
        return src
    rows = catalog.read(src)

    if args.under is not None:
        rows = [L for L in rows if L.price is not None and L.price <= args.under]
    if args.over is not None:
        rows = [L for L in rows if L.price is not None and L.price >= args.over]
    if args.site:
        rows = [L for L in rows if L.site == args.site]
    if args.drops:
        rows = [L for L in rows if L.price_dropped]
    if args.since:
        undated = sum(1 for L in rows if filters._parse_dt(L.posted_at) is None)
        if undated:
            print(f"deals: warning: {undated}/{len(rows)} listings have no posted_at "
                  f"(e.g. a --fast catalog); --since keeps them", file=sys.stderr)
        cutoff = datetime.now(tz=timezone.utc) - filters.parse_age(args.since)
        def fresh(L):
            dt = filters._parse_dt(L.posted_at)
            return dt is None or dt >= cutoff
        rows = [L for L in rows if fresh(L)]

    sort_key = {"price": lambda L: (L.price is None, L.price or 0),
                "drop": lambda L: -(L.price_drop_pct or 0),
                "distance": lambda L: (L.distance_mi is None, L.distance_mi or 0)}[args.sort]
    rows.sort(key=sort_key)
    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        print("(no listings match)")
        return 0
    print(f"{'PRICE':>7} {'DROP':>6} {'MI':>5}  {'POSTED':<10} TITLE")
    for L in rows:
        price = f"${L.price:.0f}" if L.price is not None else "—"
        drop = f"-{L.price_drop_pct:.0f}%" if L.price_dropped and L.price_drop_pct else ""
        mi = f"{L.distance_mi:.0f}" if L.distance_mi is not None else ""
        posted = (L.posted_at or "")[:10]
        print(f"{price:>7} {drop:>6} {mi:>5}  {posted:<10} {L.title[:60]}")
    print(f"\n{len(rows)} listings  ({src})")
    return 0


def _latest_or_err():
    try:
        cfg = config.load()
    except config.ConfigError as e:
        return _err(str(e))
    p = catalog.latest(cfg.catalogs_dir)
    if not p:
        return _err(f"no catalog found in {cfg.catalogs_dir} — run `deals scrape` first")
    return p


# ------------------------------------------------------------------------- value
def cmd_value(args) -> int:
    src = _resolve_catalog(args)
    if isinstance(src, int):
        return src
    try:
        pack = packs_mod.load_pack(args.pack)
    except packs_mod.PackError as e:
        return _err(str(e))
    if args.out:
        _validate_out_path(args.out)

    rows = catalog.read(src)
    packs_mod.apply_pack(pack, rows)

    # perishability nudge: value tables drift
    cal = pack.meta.get("calibrated_on")
    pa = pack.meta.get("perishable_after")
    if cal and pa:
        try:
            age = datetime.now(tz=timezone.utc) - datetime.fromisoformat(cal).replace(tzinfo=timezone.utc)
            if age > filters.parse_age(pa):
                print(f"  warning: pack '{pack.name}' calibrated {cal} (> {pa} ago) — "
                      f"value estimates may be stale; recalibrate.", file=sys.stderr)
        except (ValueError, TypeError):
            pass

    out = Path(args.out) if args.out else src
    catalog.write(rows, out)

    scored = [L for L in rows if L.deal_score is not None]
    scored.sort(key=lambda L: -(L.deal_score or 0))
    shown = scored[: args.limit] if args.limit else scored
    print(f"valued {len(rows)} listings with pack '{pack.name}' -> {out}")
    n_verify = sum(1 for L in rows if (L.flags or {}).get("verify_tier"))
    print(f"  {len(scored)} scored; {n_verify} in verify-tier (high-reward/high-verify)\n")
    print(f"{'SCORE':>6} {'PRICE':>7} {'EST.AVG':>8}  SPECS / TITLE")
    for L in shown:
        tag = "  ⚑VERIFY" if (L.flags or {}).get("verify_tier") else ""
        specs = " ".join(f"{k}={v}" for k, v in (L.attributes or {}).items()) or "—"
        price = f"${L.price:.0f}" if L.price is not None else "—"
        est = f"${L.est_value_avg:.0f}" if L.est_value_avg else "—"
        print(f"{L.deal_score:>6.2f} {price:>7} {est:>8}  {specs[:40]} | {L.title[:34]}{tag}")
    return 0


# ------------------------------------------------------------------------- cache
def cmd_cache(args) -> int:
    site = args.site or _cfg_site_or("offerup")
    if args.clear:
        n = cache_mod.clear(site)
        print(f"cleared {n} cached detail entries for {site}")
        return 0
    s = cache_mod.stats(site)
    print(f"{site}: {s['entries']} cached detail entries  ({s['dir']})")
    return 0


# ------------------------------------------------------------------------- diff
CHANGE_EXIT_CODE = 10   # `--exit-on-change`: distinct from error(1) so cron can branch


def cmd_diff(args) -> int:
    # resolve the (old, new) pair: explicit, or auto-pick the two most recent
    if args.old and args.new:
        old_p, new_p = Path(args.old), Path(args.new)
        for p in (old_p, new_p):
            if not p.exists():
                return _err(f"catalog not found: {p}")
    elif not args.old and not args.new:
        cfg = config.load()
        recents = catalog.recent(cfg.catalogs_dir, 2)
        if len(recents) < 2:
            return _err(f"need >= 2 catalogs in {cfg.catalogs_dir} to auto-diff "
                        f"(or pass OLD NEW explicitly)")
        old_p, new_p = recents[0], recents[1]      # oldest, newest
    else:
        return _err("pass both OLD and NEW catalogs, or neither (auto-picks latest two)")

    if args.out:
        _validate_out_path(args.out)

    result = diffmod.diff_catalogs(catalog.read(old_p), catalog.read(new_p))

    # price-drop view filters (display + change-detection)
    drops = result.price_drop
    if args.min_drop is not None:
        drops = [pc for pc in drops if pc.pct is not None and -pc.pct >= args.min_drop]
    if args.min_drop_amt is not None:
        drops = [pc for pc in drops if -pc.delta >= args.min_drop_amt]

    _print_diff(old_p, new_p, result, drops, args)

    if args.out:
        diffmod.write_diff(result, Path(args.out))
        print(f"wrote delta -> {args.out}")

    if args.exit_on_change and (result.new or drops):
        return CHANGE_EXIT_CODE
    return 0


def _print_diff(old_p, new_p, result, drops, args) -> None:
    c = result.counts
    print(f"diff  {Path(old_p).name}  ->  {Path(new_p).name}", file=sys.stderr)
    sold_bit = (f"   x{c['sold']} sold   u{c['unlisted']} unlisted"
                if (c['sold'] or c['unlisted']) else "")
    print(f"  +{c['new']} new   -{c['gone']} gone   "
          f"v{len(drops)} drops   ^{c['price_rise']} rises   "
          f"={c['unchanged']} unchanged{sold_bit}", file=sys.stderr)

    show_new = not (args.drops or args.gone)
    show_drops = not (args.new_only or args.gone)
    show_gone = args.gone

    if show_new and result.new:
        rows = sorted(result.new, key=lambda L: (L.price is None, L.price or 0))
        print("\nNEW:")
        for L in rows:
            _print_listing_line(L)
    if show_drops and drops:
        rows = sorted(drops, key=lambda pc: (pc.pct if pc.pct is not None else 0))
        print("\nPRICE DROPS:")
        for pc in rows:
            L = pc.listing
            tag = f"${pc.prev_price:.0f}->${pc.new_price:.0f} ({pc.pct:+.0f}%)"
            print(f"  {tag:>22}  {(L.distance_mi or 0):>4.0f}mi  {L.title[:50]}")
            print(f"     {L.url}")
    if show_gone:
        if result.sold:
            print("\nSOLD (listing marked sold):")
            for L in sorted(result.sold, key=lambda L: (L.price is None, L.price or 0)):
                _print_listing_line(L)
        if result.unlisted:
            print("\nUNLISTED (seller pulled it — not marked sold):")
            for L in sorted(result.unlisted, key=lambda L: (L.price is None, L.price or 0)):
                _print_listing_line(L)
        if result.gone:
            print("\nGONE (no longer resolves — delisted/expired/removed; not confirmed sold):")
            for L in sorted(result.gone, key=lambda L: (L.price is None, L.price or 0)):
                _print_listing_line(L)


def _print_listing_line(L) -> None:
    price = f"${L.price:.0f}" if L.price is not None else "—"
    mi = f"{L.distance_mi:.0f}mi" if L.distance_mi is not None else ""
    print(f"  {price:>7}  {mi:>5}  {L.title[:55]}")
    print(f"     {L.url}")


# ------------------------------------------------------------------------- watch
def _upsert(prev_listings, head_listings) -> list:
    """Merge the incremental feed head into the prior catalog: replace by id, add
    new. A listing absent from the head is KEPT — it's below the newest-first fold,
    not gone (the head can't prove a departure)."""
    by_id = {L.listing_id: L for L in prev_listings}
    for L in head_listings:
        by_id[L.listing_id] = L
    return list(by_id.values())


def cmd_watch(args) -> int:
    """One poll of a saved query: detect changes vs the query's own last run and
    alert. The recurring cadence is external (/loop or /schedule re-invokes this).

    Two modes over the one diff primitive:
      default (incremental): newest-first feed, bounded to --pages, reports NEW +
        price drops on the head (cheap; can't see departures).
      --full: full re-scan; also splits departed listings into sold / unlisted /
        gone by re-querying their state. Read-only — never contacts sellers."""
    try:
        cfg = config.load()
    except config.ConfigError as e:
        return _err(str(e))

    site = args.site or cfg.site
    radius = float(args.radius) if args.radius is not None else cfg.radius_mi
    max_age = args.max_age or cfg.max_age
    zipcode = args.location or cfg.zip
    lat, lon = cfg.lat, cfg.lon
    if args.location and args.location != cfg.zip:
        geo = geocode_zip(args.location)
        if geo:
            lat, lon, _ = geo
        else:
            return _err(f"could not geocode override location {args.location}")

    queries = _collect_queries(args)
    if not queries:
        return _err("provide --query or --queries-file")
    if args.notify == "email" and not args.email_to:
        return _err("--notify email requires --email-to ADDR")
    try:
        filters.parse_age(max_age)
    except ValueError as e:
        return _err(f"{e} (config defaults.max_age or --max-age)")

    pack = None
    if args.pack:
        try:
            pack = packs_mod.load_pack(args.pack)
        except packs_mod.PackError as e:
            return _err(str(e))

    auth = auth_mod.ensure(site)
    adapter = get_adapter_cls(site)(auth, lat, lon, zipcode,
                                    rps=args.rps, cache=not args.no_cache)

    q0 = queries[0]
    wkey = watchstate.key(site, q0, zipcode)
    prev_path = watchstate.last_catalog(wkey)

    mode = "full re-scan" if args.full else "incremental (newest-first)"
    print(f"watch {site}: “{q0}” {mode} radius={radius}mi", file=sys.stderr)

    sort = None if args.full else "newest"
    max_pages = 0 if args.full else args.pages     # full exhausts; incremental bounded
    listings = adapter.scrape(queries, radius, enrich=False, detail=True,
                              max_pages=max_pages, concurrency=args.concurrency,
                              sort=sort, progress=_progress)
    if getattr(adapter, "last_throttled", False):
        print("  WARNING: detail endpoint throttled — partial results "
              "(cached; re-run resumes).", file=sys.stderr)
    kept, _ = filters.apply(listings, radius_mi=radius, max_age=max_age)
    cfg.catalogs_dir.mkdir(parents=True, exist_ok=True)

    # first run for this query: establish a baseline, no diff/alert
    if prev_path is None:
        out = catalog.default_path(cfg.catalogs_dir, site, q0)
        catalog.write(kept, out)
        watchstate.save(wkey, out, len(kept))
        print(f"baseline established: {len(kept)} listings -> {out}\n"
              f"  (re-run to detect changes)")
        return 0

    prev = catalog.read(prev_path)
    result = diffmod.diff_catalogs(prev, kept)

    if args.full:
        gone_ids = [L.listing_id for L in result.gone]
        if gone_ids:
            states = adapter.lookup_states(gone_ids)
            if states:
                diffmod.reclassify_gone(result, lambda lid: states.get(lid))
        new_catalog = kept
    else:
        result.gone = []                       # head can't prove departures
        new_catalog = _upsert(prev, kept)

    if pack and result.new:
        packs_mod.apply_pack(pack, result.new)

    drops = result.price_drop
    if args.min_drop is not None:
        drops = [pc for pc in drops if pc.pct is not None and -pc.pct >= args.min_drop]

    c = result.counts
    print(f"  +{len(result.new)} new  v{len(drops)} drops  "
          f"x{c['sold']} sold  u{c['unlisted']} unlisted  -{c['gone']} gone",
          file=sys.stderr)

    notify_mod.dispatch(result, q0, sink=args.notify, email_to=args.email_to,
                        drops=drops, location=zipcode, incremental=not args.full)

    out = catalog.default_path(cfg.catalogs_dir, site, q0)
    catalog.write(new_catalog, out)
    watchstate.save(wkey, out, len(new_catalog))

    if args.exit_on_change and (result.new or drops):
        return CHANGE_EXIT_CODE
    return 0


def _resolve_catalog(args):
    """Resolve a catalog path from --in (validated) or the latest. Returns a Path
    or an int error code."""
    if args.inp:
        p = Path(args.inp)
        if not p.exists():
            return _err(f"catalog not found: {args.inp}")
        return p
    return _latest_or_err()


# ---------------------------------------------------------------------- arg parse
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deals", description="Marketplace deal-mining CLI.")
    p.add_argument("--version", action="version", version=f"deals {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="scaffold central user config")
    pi.add_argument("--zip"); pi.add_argument("--radius", type=_pos_float)
    pi.add_argument("--max-age", dest="max_age", type=_age_spec); pi.add_argument("--site")
    pi.add_argument("--lat", type=float); pi.add_argument("--lon", type=float)
    pi.add_argument("--yes", "-y", action="store_true", help="accept defaults, no prompts")
    pi.add_argument("--force", action="store_true", help="overwrite existing config")
    pi.set_defaults(func=cmd_init)

    pr = sub.add_parser("refresh-auth", help="(re)provision a site's device token")
    pr.add_argument("--site", choices=available_sites())
    pr.set_defaults(func=cmd_refresh_auth)

    ps = sub.add_parser("scrape", help="scrape listings into a catalog")
    ps.add_argument("--site", choices=available_sites())
    ps.add_argument("--query", "-q", action="append", help="search query (repeatable)")
    ps.add_argument("--queries-file", dest="queries_file", help="file of queries, one per line")
    ps.add_argument("--location", help="override ZIP for this run")
    ps.add_argument("--radius", type=_pos_float, help="override radius (mi)")
    ps.add_argument("--max-age", dest="max_age", type=_age_spec, help="override max age (e.g. 2mo)")
    ps.add_argument("--max-price", dest="max_price", type=float, help="cheap pre-filter ceiling")
    ps.add_argument("--min-price", dest="min_price", type=float, help="cheap pre-filter floor")
    ps.add_argument("--enrich", action="store_true", help="retain full description text")
    ps.add_argument("--fast", action="store_true",
                    help="feed-only (no detail; no radius/age/price-drop)")
    ps.add_argument("--max-pages", dest="max_pages", type=_nonneg_int, default=0,
                    help="cap feed pages per query (0 = all pages / full census; default 0)")
    ps.add_argument("--concurrency", type=_pos_int, default=3,
                    help="parallel detail fetches (default: 3 — polite)")
    ps.add_argument("--rps", type=float, default=3.0,
                    help="max detail requests/sec (default: 3)")
    ps.add_argument("--no-cache", dest="no_cache", action="store_true",
                    help="ignore the detail cache (always fetch, don't store)")
    ps.add_argument("--refresh", action="store_true",
                    help="re-fetch details even if cached (refresh the cache)")
    ps.add_argument("--out", help="output CSV path (default: catalogs dir)")
    ps.set_defaults(func=cmd_scrape)

    pe = sub.add_parser("export", help="re-emit the latest (or given) catalog")
    pe.add_argument("--format", default="csv")
    pe.add_argument("--in", dest="inp", help="catalog CSV to read (default: latest)")
    pe.add_argument("--out", help="output path (default: stdout)")
    pe.set_defaults(func=cmd_export)

    pl = sub.add_parser("ls", help="quick filtered view of a catalog")
    pl.add_argument("--in", dest="inp", help="catalog CSV to read (default: latest)")
    pl.add_argument("--under", type=float, help="price <= N")
    pl.add_argument("--over", type=float, help="price >= N")
    pl.add_argument("--since", type=_age_spec, help="posted within (e.g. 2mo)")
    pl.add_argument("--site", choices=available_sites())
    pl.add_argument("--drops", action="store_true", help="only price-dropped listings")
    pl.add_argument("--sort", choices=["price", "drop", "distance"], default="price")
    pl.add_argument("--limit", type=_nonneg_int, default=0, help="max rows (0 = no limit)")
    pl.set_defaults(func=cmd_ls)

    pd = sub.add_parser("diff", help="compare two catalogs: new / gone / price changes")
    pd.add_argument("old", nargs="?", help="old catalog CSV (omit both to auto-pick latest two)")
    pd.add_argument("new", nargs="?", help="new catalog CSV")
    pd.add_argument("--new-only", dest="new_only", action="store_true",
                    help="show only newly-appeared listings")
    pd.add_argument("--drops", action="store_true", help="show only price drops")
    pd.add_argument("--gone", action="store_true", help="show only gone listings")
    pd.add_argument("--min-drop", dest="min_drop", type=float,
                    help="only price drops >= N percent")
    pd.add_argument("--min-drop-amt", dest="min_drop_amt", type=float,
                    help="only price drops >= $N")
    pd.add_argument("--out", help="write machine-readable delta CSV")
    pd.add_argument("--exit-on-change", dest="exit_on_change", action="store_true",
                    help=f"exit {CHANGE_EXIT_CODE} if there are new/dropped listings (for cron)")
    pd.set_defaults(func=cmd_diff)

    pw = sub.add_parser("watch", help="one poll of a saved query: detect changes "
                        "vs its own last run + alert (drive on a cadence with /loop)")
    pw.add_argument("--site", choices=available_sites())
    pw.add_argument("--query", "-q", action="append", help="search query (first is primary)")
    pw.add_argument("--queries-file", dest="queries_file", help="file of queries, one per line")
    pw.add_argument("--location", help="override ZIP for this run")
    pw.add_argument("--radius", type=_pos_float, help="override radius (mi)")
    pw.add_argument("--max-age", dest="max_age", type=_age_spec, help="override max age (e.g. 2mo)")
    pw.add_argument("--full", action="store_true",
                    help="full re-scan (catches price drops + sold/unlisted on existing "
                         "listings); default is the cheap newest-first incremental poll")
    pw.add_argument("--pages", type=_pos_int, default=2,
                    help="incremental poll: feed pages of newest-first to pull (default 2)")
    pw.add_argument("--pack", help="optional domain pack to value the NEW listings (e.g. gaming-pc)")
    pw.add_argument("--notify", choices=["none", "email"], default="none",
                    help="alert sink for changes (default: none -> stdout only)")
    pw.add_argument("--email-to", dest="email_to", help="recipient for --notify email")
    pw.add_argument("--min-drop", dest="min_drop", type=float,
                    help="only alert price drops >= N percent")
    pw.add_argument("--concurrency", type=_pos_int, default=3,
                    help="parallel detail fetches (default: 3 — polite)")
    pw.add_argument("--rps", type=float, default=3.0, help="max detail requests/sec (default: 3)")
    pw.add_argument("--no-cache", dest="no_cache", action="store_true",
                    help="ignore the detail cache (always fetch, don't store)")
    pw.add_argument("--exit-on-change", dest="exit_on_change", action="store_true",
                    help=f"exit {CHANGE_EXIT_CODE} if there are new/dropped listings (for cron)")
    pw.set_defaults(func=cmd_watch)

    pc = sub.add_parser("cache", help="inspect or clear the detail cache")
    pc.add_argument("--site", choices=available_sites())
    pc.add_argument("--clear", action="store_true", help="delete all cached details for the site")
    pc.set_defaults(func=cmd_cache)

    pv = sub.add_parser("value", help="extract attributes + estimate value + score a catalog with a domain pack")
    pv.add_argument("--pack", required=True, help="domain pack name (e.g. gaming-pc)")
    pv.add_argument("--in", dest="inp", help="catalog CSV to value (default: latest)")
    pv.add_argument("--out", help="output CSV (default: enrich the input in place)")
    pv.add_argument("--limit", type=_nonneg_int, default=20, help="rows to print (0 = all)")
    pv.set_defaults(func=cmd_value)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
    except config.ConfigError as e:
        return _err(str(e))
    except (ValueError, OSError) as e:
        # safety net: never dump a raw traceback at the user for an expected
        # failure mode (bad input, unreadable/unwritable path, malformed data).
        return _err(str(e))


if __name__ == "__main__":
    sys.exit(main())
