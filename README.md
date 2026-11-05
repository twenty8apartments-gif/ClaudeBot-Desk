# ClaudeBot Desk

A trading desk of small bots, modeled on Grok Bot's desk roles. Most bots are free Python scripts on GitHub Actions; only the two seats where judgment matters use Claude.

**Paper trades only. Nothing here connects to a broker or places orders.**

| Seat | Runs on | Schedule (Mauritius time) | Writes |
|---|---|---|---|
| Research | GitHub Actions (free) | Mon–Fri 07:13 | `data/research.json` |
| Chief of Staff | GitHub Actions (free) | Mon–Fri 07:15, after Research | `data/briefs.json` |
| Tracker | GitHub Actions (free) | Hourly at :55, Mon–Sat | `data/ideas.json` |
| Journal (daily) | GitHub Actions (free) | Mon–Fri 23:37 | `data/reviews.json` |
| Tax & Ops | GitHub Actions (free) | Sun 11:17 | `data/ops.json` |
| Ideas (paper) | Claude scheduled task | Mon–Fri 08:13 | `data/ideas.json` |
| Journal (weekly) | Claude scheduled task | Sat 10:23 | `data/reviews.json` |

The dashboard is `index.html`, served by GitHub Pages. It reads the JSON files in `data/` straight from the repo.

## Logging trades

The dashboard's forms open a pre-filled GitHub issue. The `commands` workflow reads it, updates `data/`, and closes the issue. Only issues opened by the repo owner are accepted.

## Settings

Edit `data/settings.json`: watchlist (name + Yahoo Finance symbol + currencies the calendar should match), risk limits and playbook rules.

## Data sources

- Prices: Yahoo Finance hourly bars via `yfinance` (unofficial, can be delayed or rate-limited).
- Calendar: the public Forex Factory weekly calendar feed.
