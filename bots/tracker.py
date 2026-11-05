"""Tracker bot (free): stamps entry prices on new paper ideas and re-prices open
ones every hour from Yahoo Finance hourly bars (via yfinance).

Because it reads each hour's HIGH and LOW, a stop or target touched between
runs is still caught. If one bar touched both, the stop is assumed to have
hit first (the cautious reading).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from common import add_blocked, iso, load, log_run, now_utc, parse_iso, save, symbol_for

STALE_AFTER = timedelta(minutes=90)
MAX_MARKS = 200


def trading_days_between(a: datetime, b: datetime) -> int:
    """Whole Mon–Fri days elapsed from a to b."""
    days, d = 0, a
    while True:
        d = d + timedelta(days=1)
        if d > b:
            return days
        if d.weekday() < 5:
            days += 1


def thin_marks(marks: list) -> list:
    if len(marks) <= MAX_MARKS:
        return marks
    half = len(marks) // 2
    return marks[:half:2] + marks[half:]


def evaluate(idea: dict, bars: list[dict], now: datetime) -> dict:
    """Apply new hourly bars to one idea. bars: [{t, o, h, l, c}] oldest first, t = datetime UTC.

    Returns the updated idea (a new dict). Pure function: easy to test.
    """
    idea = dict(idea)
    idea["marks"] = list(idea.get("marks") or [])
    if not bars:
        idea["stale"] = True
        return idea
    last = bars[-1]
    fresh = now - last["t"] <= STALE_AFTER
    source = idea.get("_source", "Yahoo Finance hourly bar")

    if idea.get("status") == "pending":
        if not fresh:
            idea["stale"] = True
            return idea
        idea.update({
            "status": "open", "entryPrice": round(last["c"], 6), "entryAt": iso(last["t"]),
            "entrySource": source, "lastPrice": round(last["c"], 6), "lastAt": iso(last["t"]),
            "lastSource": source, "stale": False,
        })
        idea["marks"] = [{"at": iso(last["t"]), "price": round(last["c"], 6)}]
        return idea

    if idea.get("status") != "open":
        return idea

    entry_at = parse_iso(idea.get("entryAt"))
    seen = parse_iso(idea.get("lastAt")) or entry_at
    new_bars = [b for b in bars if b["t"] > seen]
    long = idea.get("direction") != "short"
    stop, target = float(idea["stop"]), float(idea["target"])

    for b in new_bars:
        idea["marks"].append({"at": iso(b["t"]), "price": round(b["c"], 6)})
        hit_stop = b["l"] <= stop if long else b["h"] >= stop
        hit_target = b["h"] >= target if long else b["l"] <= target
        if hit_stop or hit_target:
            outcome = "stopped" if hit_stop else "target"   # both in one bar → assume stop first
            idea.update({
                "status": outcome, "exitPrice": stop if hit_stop else target,
                "closedAt": iso(b["t"]), "lastPrice": round(b["c"], 6), "lastAt": iso(b["t"]),
                "lastSource": source, "stale": False,
                "exitNote": "Assumed fill at the level. Checked with hourly highs and lows"
                            + ("; stop and target both touched in one hour, stop assumed first" if hit_stop and hit_target else ""),
            })
            idea["marks"] = thin_marks(idea["marks"])
            return idea

    idea.update({"lastPrice": round(last["c"], 6), "lastAt": iso(last["t"]), "lastSource": source, "stale": not fresh})
    horizon = int(idea.get("horizonDays") or 5)
    if entry_at and trading_days_between(entry_at, last["t"]) >= horizon:
        idea.update({"status": "expired", "exitPrice": round(last["c"], 6), "closedAt": iso(last["t"]),
                     "exitNote": f"Time exit after {horizon} trading days"})
    idea["marks"] = thin_marks(idea["marks"])
    return idea


def fetch_bars(symbol: str) -> list[dict]:
    import yfinance as yf  # imported here so tests don't need it

    df = yf.Ticker(symbol).history(period="7d", interval="60m", auto_adjust=False)
    bars = []
    for ts, row in df.iterrows():
        t = ts.to_pydatetime().astimezone(timezone.utc)
        bars.append({"t": t, "o": float(row["Open"]), "h": float(row["High"]),
                     "l": float(row["Low"]), "c": float(row["Close"])})
    # The newest bar is still forming; its close is the latest price, which is what we want.
    return bars


def main() -> None:
    ideas = load("ideas")
    live = [i for i in ideas if i.get("status") in ("pending", "open")]
    if not live:
        log_run("tracker", "ok", "Nothing to track")
        return

    now = now_utc()
    cache, failed = {}, []
    for i in live:
        sym = i.get("symbol") or symbol_for(i.get("instrument", ""))
        if not sym:
            failed.append(f"{i.get('instrument')}: no symbol in settings.json watchlist")
            continue
        if sym not in cache:
            try:
                cache[sym] = fetch_bars(sym)
            except Exception as exc:  # network / rate limit
                cache[sym] = []
                failed.append(f"{sym}: {exc.__class__.__name__}")

    closed, out = [], []
    for i in ideas:
        if i.get("status") in ("pending", "open"):
            sym = i.get("symbol") or symbol_for(i.get("instrument", ""))
            updated = evaluate({**i, "symbol": sym}, cache.get(sym, []), now)
            if updated.get("status") not in ("pending", "open"):
                closed.append(f"{updated['instrument']} {updated['status']}")
            out.append(updated)
        else:
            out.append(i)
    save("ideas", out)

    all_stale = all(not cache.get(s) or now - cache[s][-1]["t"] > STALE_AFTER for s in cache) if cache else True
    if failed and all_stale and now.weekday() < 5:
        add_blocked("tracker", "Hourly pricing", "Could not get prices: " + "; ".join(failed))
    open_n = sum(1 for i in out if i.get("status") == "open")
    status = "stale" if all_stale else "ok"
    log_run("tracker", status, f"{open_n} open" + (f"; closed: {', '.join(closed)}" if closed else ""))


if __name__ == "__main__":
    main()
