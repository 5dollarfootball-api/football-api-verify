#!/usr/bin/env python3
"""Recount 5DollarFootballAPI's published data-quality figures with your own key.

The data quality page (https://5dollarfootballapi.com/docs/data-quality) says,
per competition, what share of finished matches carry corner counts, a corner
line, pre-match odds, an event timeline, live statistics and card counts. This
script pulls the same fixtures through the public API with your key, counts
them by the same published definitions, and prints both columns side by side.

    export FIVEDOLLARFOOTBALL_API_KEY=fb_live_...
    python verify.py 4160026622            # league id from the data quality page
    python verify.py --search "Serie A"    # or find the id by name
    python verify.py 4160026622 --json     # machine-readable output

Standard library only. Free keys reach the last 3 months of the Pro
competitions; the published column covers 12 months, and the script says so
when the two windows differ.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.5dollarfootballapi.com/v1"
SITE = "https://5dollarfootballapi.com"
METRICS = ["with_corners", "with_corner_line", "with_odds", "with_events", "with_live_stats", "with_cards"]
LABELS = {
    "with_corners": "corners",
    "with_corner_line": "corner line",
    "with_odds": "odds",
    "with_events": "events",
    "with_live_stats": "live stats",
    "with_cards": "cards",
}


def get(url, key=None, tries=6):
    """GET JSON; waits out 429s using Retry-After, returns (status, body)."""
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "football-api-verify/1.0"})
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = {"raw": body}
            if e.code == 429 and attempt < tries - 1:
                wait = int(e.headers.get("Retry-After") or 15)
                print(f"  rate limited, waiting {wait}s …", file=sys.stderr)
                time.sleep(wait)
                continue
            return e.code, payload
    return 0, {}


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def has_line(market):
    """A pre-match line exists when opening or closing is a number."""
    if not isinstance(market, dict):
        return False
    return market.get("opening") is not None or market.get("closing") is not None


def classify(fx):
    """The published definitions, applied to one finished fixture row."""
    corners = fx.get("corners") or {}
    h, a = corners.get("home"), corners.get("away")
    cards = fx.get("cards") or {}
    odds = fx.get("odds") or {}
    return {
        # Both corner counts recorded and at least one corner taken: 0-0 counts as not tracked.
        "with_corners": h is not None and a is not None and (h + a) > 0,
        "with_corner_line": has_line(odds.get("corner_line")),
        # A pre-match Asian handicap line stands for the 1X2 / handicap / goal-line markets.
        "with_odds": has_line(odds.get("asian_handicap")),
        "with_events": bool(fx.get("events")),
        "with_live_stats": fx.get("statistics") is not None,
        "with_cards": (cards.get("home") or {}).get("yellow") is not None and (cards.get("away") or {}).get("yellow") is not None,
    }


def fetch_fixtures(base, key, league_id, start, end, include="odds,events,stats"):
    """Every finished fixture in [start, end), expanded with the includes asked for."""
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "status": "finished", "include": include, "per_page": 50, "page": page,
            "order": "asc", "start_time": int(start.timestamp()), "end_time": int(end.timestamp()),
        })
        status, body = get(f"{base}/leagues/{league_id}/fixtures?{q}", key)
        if status != 200:
            return status, body, rows
        rows.extend(body.get("data") or [])
        print(f"  page {page}: {len(rows)} finished fixtures so far", file=sys.stderr)
        if not (body.get("pagination") or {}).get("has_more"):
            return 200, body, rows
        page += 1


def search_league(base, key, text):
    status, body = get(f"{base}/leagues?{urllib.parse.urlencode({'search': text, 'per_page': 20})}", key)
    if status != 200:
        fail(f"league search failed ({status}): {(body.get('error') or {}).get('message', body)}")
    hits = body.get("data") or []
    if not hits:
        fail(f"no league matches '{text}'")
    if len(hits) > 1:
        print("Several leagues match — pass the id you mean:", file=sys.stderr)
        for l in hits:
            print(f"  {l['id']:>12}  {l.get('name')}  ({(l.get('country') or {}).get('name') or 'international'})", file=sys.stderr)
        sys.exit(2)
    return hits[0]["id"]


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def fmt(p):
    return "—" if p is None else ("100%" if p >= 99.95 else f"{p:.1f}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("league", nargs="?", help="league id as shown on /docs/data-quality")
    ap.add_argument("--search", help="find the league by name instead")
    ap.add_argument("--key", default=os.environ.get("FIVEDOLLARFOOTBALL_API_KEY"), help="API key (or FIVEDOLLARFOOTBALL_API_KEY)")
    ap.add_argument("--months", type=int, default=12, help="window to recount, in months back from now (default 12, the published window)")
    ap.add_argument("--base", default=API, help=argparse.SUPPRESS)
    ap.add_argument("--site", default=SITE, help=argparse.SUPPRESS)
    ap.add_argument("--json", action="store_true", help="print a JSON object instead of the table")
    args = ap.parse_args()

    if not args.key:
        fail("no API key: set FIVEDOLLARFOOTBALL_API_KEY or pass --key (a free key works: https://5dollarfootballapi.com/register)")
    if not args.league and not args.search:
        ap.error("give a league id or --search")

    league_id = args.league or search_league(args.base, args.key, args.search)

    # The published figures: the site's JSON twin for this league.
    status, published = get(f"{args.site}/docs/data-quality/{league_id}.json")
    if status == 404:
        fail(f"league {league_id} is not on the data quality page (ids there are the ones /v1 returns)")
    if status != 200:
        fail(f"could not read the published figures ({status})")
    pub = published["league"]
    pub_days = published.get("window_days", 365)

    now = datetime.now(timezone.utc)
    end = now - timedelta(hours=4)  # the published count also leaves the live window alone
    # 12 months means the published window exactly (365 days); other values are 30-day months.
    start = now - timedelta(days=pub_days if args.months == 12 else 30 * args.months)
    print(f"{pub['name']}: recounting finished fixtures since {start.date()} …", file=sys.stderr)

    include = "odds,events,stats"
    status, body, rows = fetch_fixtures(args.base, args.key, league_id, start, end, include)
    note = None
    odds_note = None
    if status == 403 and "odds" in ((body.get("error") or {}).get("message") or "").lower():
        # Expanding odds on a fixture list starts with Pro; recount the other columns with a Free key.
        include = "events,stats"
        odds_note = "odds and corner line are not counted: expanding odds on fixture lists starts with Pro, and a Free key would need one call per fixture"
        print(f"  {odds_note}", file=sys.stderr)
        status, body, rows = fetch_fixtures(args.base, args.key, league_id, start, end, include)
    if status == 403:
        err = body.get("error") or {}
        if "history" in (err.get("code") or ""):
            # The key's plan reaches less history than asked: recount what it can reach.
            start = now - timedelta(days=90)
            note = f"your key reaches {err.get('message', 'less history than 12 months')} — recounted the last 90 days instead; the published column covers {pub_days} days"
            print(f"  {note}", file=sys.stderr)
            status, body, rows = fetch_fixtures(args.base, args.key, league_id, start, end, include)
        else:
            fail(f"{err.get('code')}: {err.get('message')} ({err.get('doc_url', '')})")
    if status != 200:
        err = body.get("error") or {}
        fail(f"{status} {err.get('code', '')}: {err.get('message', body)}")

    finished = [fx for fx in rows if fx.get("status") == "finished"]
    counts = {m: 0 for m in METRICS}
    for fx in finished:
        for m, ok in classify(fx).items():
            counts[m] += 1 if ok else 0
    n = len(finished)
    mine = {m: pct(counts[m], n) for m in METRICS}
    if odds_note:
        mine["with_odds"] = mine["with_corner_line"] = None
    theirs = {m: pub["pct"].get(m) for m in METRICS}
    first = min((fx.get("kickoff_utc") or "" for fx in finished), default=None)
    last = max((fx.get("kickoff_utc") or "" for fx in finished), default=None)
    # Plans with a shorter history window are clipped silently by the API: say so
    # rather than compare a season's worth against a year's worth as if equal.
    if note is None and first and datetime.fromisoformat(first) > start + timedelta(days=14) and n < 0.9 * (pub["finished"] or 0):
        note = f"your key reaches back to {first[:10]} (its plan's history window); the published column covers {pub_days} days, so the counts differ and the shares are compared over different windows"

    if args.json:
        print(json.dumps({
            "league": {"id": league_id, "name": pub["name"], "country": pub.get("country")},
            "recounted": {"finished": n, "first_kickoff": first, "last_kickoff": last, "counts": counts, "pct": mine},
            "published": {"finished": pub["finished"], "pct": theirs, "generated_at": published.get("generated_at"), "window_days": pub_days},
            "note": note,
            "odds_note": odds_note,
            "definitions": published.get("definitions"),
        }, indent=2))
        return

    same_window = note is None and args.months == 12
    print()
    print(f"{pub['name']} ({pub.get('country') or 'international'}), league id {league_id}")
    print(f"  recounted with your key: {n} finished fixtures, {first[:10] if first else '—'} → {last[:10] if last else '—'}")
    print(f"  published on the site:   {pub['finished']} finished fixtures, last {pub_days} days, recounted {published.get('generated_at', '')[:16]} UTC")
    print()
    print(f"  {'':<14}{'you counted':>14}{'published':>14}{'':>4}")
    for m in METRICS:
        a, b = mine[m], theirs[m]
        flag = "" if a is None or b is None else ("" if abs(a - b) <= 1.0 else "  ≠")
        print(f"  {LABELS[m]:<14}{fmt(a):>14}{fmt(b):>14}{flag}")
    print()
    if odds_note:
        print(f"  note: {odds_note}")
    if note:
        print(f"  note: {note}")
    elif not same_window:
        print(f"  note: you recounted {args.months} months; the published column covers {pub_days} days")
    else:
        print("  same window, same definitions: differences over 1 point (≠) mean something changed since the nightly count, or a bug worth reporting")
    print(f"  definitions: {args.site}/docs/data-quality#definitions")


if __name__ == "__main__":
    main()
