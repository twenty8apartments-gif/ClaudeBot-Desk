"""Research bot (free): builds the event map from the public Forex Factory
calendar feed (this week + next week), converted to the desk time zone and
tagged with the watchlist instruments each event touches.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta

from common import add_blocked, iso, load, log_run, now_utc, save, settings, today_local, tz

FEEDS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]
SOURCE_TITLE = "Forex Factory calendar"
SOURCE_URL = "https://www.forexfactory.com/calendar"
IMPACT = {"High": "high", "Medium": "medium", "Low": "low", "Holiday": "low"}


def fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "claudebot-desk/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_events(raw: list, watchlist: list, zone) -> list:
    by_ccy: dict[str, list[str]] = {}
    for w in watchlist:
        for c in w.get("currencies", []):
            by_ccy.setdefault(c, []).append(w["name"])
    events = []
    for r in raw:
        ccy = r.get("country")
        if ccy not in by_ccy:
            continue
        try:
            dt = datetime.fromisoformat(r["date"]).astimezone(zone)
        except (KeyError, ValueError):
            continue
        all_day = r.get("impact") == "Holiday" or dt.strftime("%H:%M") == "00:00" and "holiday" in r.get("title", "").lower()
        slug = "".join(ch if ch.isalnum() else "-" for ch in r.get("title", "event").lower()).strip("-")[:40]
        note = []
        if r.get("forecast"):
            note.append(f"Forecast {r['forecast']}")
        if r.get("previous"):
            note.append(f"previous {r['previous']}")
        if r.get("actual"):
            note.append(f"actual {r['actual']}")
        events.append({
            "id": f"{dt.date().isoformat()}-{dt.strftime('%H%M')}-{ccy.lower()}-{slug}",
            "date": dt.date().isoformat(),
            "time": "" if all_day else dt.strftime("%H:%M"),
            "title": f"{ccy} {r.get('title', '')}".strip(),
            "instrument": ", ".join(by_ccy[ccy]),
            "impact": IMPACT.get(r.get("impact"), "low"),
            "source_title": SOURCE_TITLE,
            "source_url": SOURCE_URL,
            "verified": True,
            "note": ", ".join(note),
            "bot": "research",
        })
    return events


def main() -> None:
    cfg = settings()
    raw, errors = [], []
    for url in FEEDS:
        try:
            raw.extend(fetch(url))
        except Exception as exc:
            errors.append(f"{url.rsplit('/', 1)[-1]}: {exc.__class__.__name__}")
    if not raw:
        add_blocked("research", f"Event map for {today_local()}", "Calendar feed unreachable: " + "; ".join(errors))
        log_run("research", "blocked", "Calendar feed unreachable")
        return

    fresh = {e["id"]: e for e in to_events(raw, cfg.get("watchlist", []), tz())}
    stamp = iso(now_utc())
    for e in fresh.values():
        e["createdAt"] = stamp
    cutoff = (now_utc().astimezone(tz()) - timedelta(days=21)).date().isoformat()
    kept = {e["id"]: e for e in load("research") if e.get("date", "") >= cutoff}
    kept.update(fresh)  # newer feed values (e.g. actuals) replace older copies
    events = sorted(kept.values(), key=lambda e: (e["date"], e.get("time") or "00:00"))
    save("research", events)
    high = sum(1 for e in fresh.values() if e["impact"] == "high")
    log_run("research", "ok", f"{len(fresh)} events in feed ({high} high impact)" + (f"; partial: {'; '.join(errors)}" if errors else ""))


if __name__ == "__main__":
    main()
