# football-api-verify

Recount [5DollarFootballAPI](https://5dollarfootballapi.com)'s published data-quality figures with your own key.

The [data quality page](https://5dollarfootballapi.com/docs/data-quality) says, per competition, what share of finished matches in the last 12 months carry corner counts, a corner line, pre-match odds, an event timeline, live statistics and card counts. Those numbers are counted on our side. This script lets you count them on yours: it pulls the same fixtures through the public API with your key, applies the same published definitions, and prints both columns side by side.

No dependencies beyond Python 3.8+.

```bash
export FIVEDOLLARFOOTBALL_API_KEY=fb_live_your_key   # a free key works: https://5dollarfootballapi.com/register
python verify.py 4160026622                          # league id, as shown on the data quality page
python verify.py --search "Brazil Serie A"           # or find it by name
python verify.py 4160026622 --json                   # machine-readable output
```

Example output:

```
England Premier League (England), league id 4160026622
  recounted with your key: 365 finished fixtures, 2025-10-18 → 2026-10-10
  published on the site:   365 finished fixtures, last 365 days, recounted 2026-10-11T04:28 UTC

                   you counted     published
  corners                 100%          100%
  ht corners              100%          100%
  corner line             100%          100%
  odds                    100%          100%
  events                 99.7%         99.7%
  live stats              100%          100%
  cards                   100%          100%

  same window, same definitions: differences over 1 point (≠) mean something changed since the nightly count, or a bug worth reporting
```

## What it counts

Every share is a percentage of **finished** fixtures (`status = "finished"`) with kickoff in the window. The definitions are the ones published at [/docs/data-quality#definitions](https://5dollarfootballapi.com/docs/data-quality#definitions) and returned by every `/docs/data-quality/{id}.json`:

| column | counted when |
|---|---|
| corners | `corners.home` and `corners.away` are both present and at least one corner was taken — a 0–0 corner count is treated as *not tracked* |
| ht corners | `corners.half_home` and `corners.half_away` are both present |
| corner line | `odds.corner_line` has an opening or closing line |
| odds | `odds.asian_handicap` has an opening or closing line (1X2, handicap and goal-line markets arrive together) |
| events | `events` is non-empty |
| live stats | `statistics` is present |
| cards | `cards.home.yellow` and `cards.away.yellow` are both present |

The calls behind it: `GET /v1/leagues/{id}/fixtures?status=finished&include=odds,events,stats` paged at 50, and `GET /docs/data-quality/{id}.json` for the published column.

## Windows and plans

The published column covers the last 365 days. A Free key reaches the last 3 months of the Pro competitions; when the API refuses the 12-month window, the script recounts the last 90 days and says so — the two columns then cover different windows and are not expected to match. Pro keys reach 12 months of the Pro competitions, Ultra keys everything.

A 365-fixture league is about eight requests. The script waits out rate limits on its own.

## If the columns disagree

A difference of a point or less is the nightly count lagging a day. More than that is either a change in the feed since the count or a bug in one of the two counters — [tell us](https://5dollarfootballapi.com/contact) which league and we will look.

## License

MIT.
