"""Turns a GitHub issue opened from the dashboard into a data change.

Titles it understands:
  [trade] ...           body: key: value lines (date, time, instrument, direction, setup, size,
                        riskPct, entry, stop, target, exit, pnl, followedPlan, notes)
  [close] <trade id>    body: exit, pnl (optional), notes (optional)
  [delete] <trade id>
  [decision] <date>     body: call: trade|none, note
  [resolve] <blocked id>

Reads the issue from the GITHUB_EVENT_PATH file. Prints a one-line result,
which the workflow posts back as the issue comment.
"""
from __future__ import annotations

import json
import os
import re
import sys

from common import iso, load, now_utc, save, today_local, trade_r

NUM = {"size", "riskPct", "entry", "stop", "target", "exit", "pnl"}
FIELDS = NUM | {"date", "time", "instrument", "direction", "setup", "followedPlan", "notes", "call", "note"}


def parse_body(body: str) -> dict:
    out, key = {}, None
    for line in (body or "").splitlines():
        m = re.match(r"^\s*([A-Za-z]+)\s*:\s*(.*)$", line)
        if m and m.group(1) in FIELDS:
            key = m.group(1)
            out[key] = m.group(2).strip()
        elif key == "notes" and line.strip():
            out["notes"] += "\n" + line.strip()   # multi-line notes
    for k in NUM & out.keys():
        v = out[k].replace(",", "")
        out[k] = float(v) if v not in ("", "-") else None
    return out


def handle(title: str, body: str) -> str:
    title = title.strip()
    tag = (re.match(r"^\[(\w+)\]", title) or [None, ""])[1].lower()
    arg = re.sub(r"^\[\w+\]\s*", "", title).strip()
    f = parse_body(body)

    if tag == "trade":
        missing = [k for k in ("instrument", "entry", "stop") if f.get(k) in (None, "")]
        if missing:
            return "Not saved: missing " + ", ".join(missing) + "."
        t = {k: f.get(k) for k in FIELDS - {"call", "note"}}
        t["date"] = t.get("date") or today_local()
        t["instrument"] = str(t["instrument"]).upper()
        t["direction"] = "short" if str(t.get("direction", "")).lower().startswith("s") else "long"
        t["status"] = "open" if t.get("exit") is None else "closed"
        t["r"] = trade_r(t)
        t["createdAt"] = iso(now_utc())
        t["id"] = f"t{now_utc().strftime('%Y%m%d%H%M%S')}"
        trades = load("trades")
        trades.insert(0, t)
        save("trades", trades)
        r = "open" if t["r"] is None else f"{t['r']:+.2f}R"
        return f"Saved {t['instrument']} {t['direction']} ({r}) as {t['id']}."

    if tag in ("close", "delete"):
        trades = load("trades")
        hit = next((t for t in trades if t.get("id") == arg), None)
        if not hit:
            return f"No trade with id {arg}."
        if tag == "delete":
            save("trades", [t for t in trades if t.get("id") != arg])
            return f"Deleted {arg}."
        if f.get("exit") is None:
            return "Not saved: exit price missing."
        hit["exit"], hit["status"] = f["exit"], "closed"
        if f.get("pnl") is not None:
            hit["pnl"] = f["pnl"]
        if f.get("notes"):
            hit["notes"] = ((hit.get("notes") or "") + "\n" + f["notes"]).strip()
        hit["r"] = trade_r(hit)
        save("trades", trades)
        return f"Closed {arg} at {hit['exit']} ({hit['r']:+.2f}R)." if hit["r"] is not None else f"Closed {arg}."

    if tag == "decision":
        day = arg or today_local()
        call = "none" if str(f.get("call", "")).lower().startswith("n") else "trade"
        ds = [d for d in load("decisions") if d.get("date") != day]
        ds.insert(0, {"date": day, "call": call, "note": f.get("note", ""), "at": iso(now_utc())})
        save("decisions", ds[:60])
        return f"Recorded {day}: {'trading' if call == 'trade' else 'no-trade day'}."

    if tag == "resolve":
        blocked = load("blocked")
        for b in blocked:
            if b.get("id") == arg:
                b["status"], b["resolvedAt"] = "resolved", iso(now_utc())
                save("blocked", blocked)
                return f"Marked {arg} resolved."
        return f"No blocked item with id {arg}."

    return "Title not recognised. Use [trade], [close], [delete], [decision] or [resolve]."


def main() -> None:
    event = json.load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8"))
    issue = event["issue"]
    print(handle(issue.get("title", ""), issue.get("body") or ""))


if __name__ == "__main__":
    sys.exit(main())
