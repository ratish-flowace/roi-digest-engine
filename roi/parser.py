"""CSV parsing and metric computation."""

import csv
import re
from datetime import datetime


# ── Formatting utilities (used by enricher, agent, renderer too) ──────────────

def _strip_excel(v):
    v = v.strip()
    m = re.match(r'^="?(.*?)"?$', v)
    return m.group(1) if m else v

def _to_hours(s):
    s = _strip_excel(s)
    if not s or s == "00:00:00":
        return 0.0
    p = s.split(":")
    if len(p) != 3:
        return 0.0
    try:
        return int(p[0]) + int(p[1]) / 60.0 + int(p[2]) / 3600.0
    except ValueError:
        return 0.0

def _to_pct(s):
    try:
        return float(s.strip().rstrip("%"))
    except ValueError:
        return 0.0

def _to_minutes(s):
    s = _strip_excel(s)
    if not s or s == "00:00:00":
        return None
    p = s.split(":")
    if len(p) != 3:
        return None
    try:
        h, m, sec = int(p[0]), int(p[1]), int(p[2])
        result = h * 60 + m + sec / 60.0
        return round(result, 1) if result <= 1440 else None
    except ValueError:
        return None

def _avg(lst):
    lst = [v for v in lst if v is not None]
    return round(sum(lst) / len(lst), 1) if lst else 0.0

def _fh(h):
    """196.9 → '196h 54m'"""
    m = int(round(h * 60))
    hh, mm = divmod(m, 60)
    if hh == 0: return f"{mm}m"
    if mm == 0: return f"{hh}h"
    return f"{hh}h {mm}m"

def _clock(mins):
    if mins is None: return "--:--"
    h, m = divmod(int(mins), 60)
    return f"{h:02d}:{m:02d}"

def _safe_pct(num, den):
    return round(num / den * 100, 1) if den else 0.0

def _num_in(x):
    """Indian-grouped integer, matching the UI's toLocaleString('en-IN'). 134493 → '1,34,493'"""
    s = str(int(round(x)))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    head = re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", head)
    return f"{head},{tail}"


# ── CSV → metrics ─────────────────────────────────────────────────────────────

def parse_csv(path: str) -> dict:
    """
    Parse a Flowace Workforce Efficiency CSV export.
    Returns a fully computed metrics dict ready for enrichment and rendering.
    Data source agnostic — swap this function for an API fetcher when the
    platform API is available; the rest of the pipeline stays unchanged.
    """
    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()

    meta = {}
    for line in lines[:10]:
        kv = line.strip().split(",", 1)
        if len(kv) == 2:
            k = kv[0].strip().rstrip(" :")
            v = _strip_excel(kv[1].strip())
            if k: meta[k] = v

    hi = next((i for i, l in enumerate(lines) if l.startswith("User Name,")), None)
    if hi is None:
        raise ValueError("Cannot find 'User Name' header row in CSV")

    reader = csv.DictReader(lines[hi:])
    users, inactive = [], 0
    for row in reader:
        name = row.get("User Name", "").strip()
        if not name: continue
        try:
            days = float(row.get("Timesheet Logged Days", "0") or "0")
        except ValueError:
            days = 0.0
        logged = _to_hours(row.get("Logged Hours", "00:00:00"))
        if days == 0 or logged < 0.05:
            inactive += 1
            continue
        teams_raw = row.get("Teams", "-").strip()
        teams = ([t.strip() for t in teams_raw.split(";") if t.strip()]
                 if teams_raw and teams_raw != "-" else ["No Team"])
        users.append({
            "name":             name,
            "teams":            teams,
            "days":             days,
            "logged":           logged,
            "active":           _to_hours(row.get("Active Hours", "00:00:00")),
            "idle":             _to_hours(row.get("Idle Hours", "00:00:00")),
            "productive":       _to_hours(row.get("Productive Hours", "00:00:00")),
            "unproductive":     _to_hours(row.get("Unproductive Hours", "00:00:00")),
            "neutral":          _to_hours(row.get("Neutral Hours", "00:00:00")),
            "activity_pct":     _to_pct(row.get("Activity %", "0")),
            "productivity_pct": _to_pct(row.get("Productivity %", "0")),
            "avg_start_min":    _to_minutes(row.get("Avg Work Start Time", "")),
            "avg_end_min":      _to_minutes(row.get("Avg Work End Time", "")),
        })

    if not users:
        raise ValueError("No active users found in CSV")

    return _build_metrics(meta, users, inactive)


def _build_metrics(meta: dict, users: list, inactive: int) -> dict:
    n  = len(users)
    ol = round(sum(u["logged"]       for u in users), 2)
    oa = round(sum(u["active"]       for u in users), 2)
    oi = round(sum(u["idle"]         for u in users), 2)
    op = round(sum(u["productive"]   for u in users), 2)
    ou = round(sum(u["unproductive"] for u in users), 2)
    on = round(sum(u["neutral"]      for u in users), 2)

    org = {
        "n": n, "logged": ol, "active": oa, "idle": oi,
        "productive": op, "unproductive": ou, "neutral": on,
        "activity_pct":     _safe_pct(oa, ol),
        "productivity_pct": _safe_pct(op, oa),
        "idle_pct":         _safe_pct(oi, ol),
        "unproductive_pct": _safe_pct(ou, oa),
        "avg_start_min":    _avg([u["avg_start_min"] for u in users]),
        "avg_end_min":      _avg([u["avg_end_min"]   for u in users]),
    }

    team_map = {}
    for u in users:
        for t in u["teams"]:
            team_map.setdefault(t, []).append(u)

    teams = []
    for tname, members in sorted(team_map.items()):
        tn   = len(members)
        tl   = round(sum(m["logged"]       for m in members), 2)
        ta   = round(sum(m["active"]       for m in members), 2)
        ti   = round(sum(m["idle"]         for m in members), 2)
        tp   = round(sum(m["productive"]   for m in members), 2)
        tu   = round(sum(m["unproductive"] for m in members), 2)
        tneu = round(sum(m["neutral"]      for m in members), 2)
        teams.append({
            "name": tname, "n": tn,
            "logged": tl, "active": ta, "idle": ti,
            "productive": tp, "unproductive": tu, "neutral": tneu,
            "activity_pct":     _safe_pct(ta, tl),
            "productivity_pct": _safe_pct(tp, ta),
            "idle_pct":         _safe_pct(ti, tl),
            "unproductive_pct": _safe_pct(tu, ta),
            "avg_start_min":    _avg([m["avg_start_min"] for m in members]),
            "avg_end_min":      _avg([m["avg_end_min"]   for m in members]),
            "individuals": sorted([{
                "name": m["name"],
                "logged": round(m["logged"], 2), "active": round(m["active"], 2),
                "idle": round(m["idle"], 2), "productive": round(m["productive"], 2),
                "unproductive": round(m["unproductive"], 2), "neutral": round(m["neutral"], 2),
                "activity_pct": m["activity_pct"], "productivity_pct": m["productivity_pct"],
                "avg_start_min": m["avg_start_min"], "avg_end_min": m["avg_end_min"],
                "days": m["days"],
            } for m in members], key=lambda x: -x["productivity_pct"]),
        })

    teams.sort(key=lambda t: -t["productivity_pct"])

    sr, er = meta.get("Start Date", ""), meta.get("End Date", "")
    try:
        sd = datetime.strptime(sr, "%Y-%m-%d")
        ed = datetime.strptime(er, "%Y-%m-%d")
        period_start = sd.strftime("%-d %B %Y")
        period_end   = ed.strftime("%-d %B %Y")
        period_days  = (ed - sd).days + 1
    except Exception:
        period_start, period_end, period_days = sr, er, 0

    gr = meta.get("Generated At", "")
    try:
        generated_at = datetime.strptime(gr, "%Y-%m-%d %H:%M:%S").strftime("%-d %b %Y")
    except Exception:
        generated_at = datetime.now().strftime("%-d %b %Y")

    at_risk = sorted(
        [u for u in users
         if u["activity_pct"] < org["activity_pct"]
         and u["productivity_pct"] < org["productivity_pct"]],
        key=lambda u: u["productivity_pct"]
    )

    return {
        "org_name":       "",
        "period_start":   period_start,
        "period_end":     period_end,
        "period_days":    period_days,
        "generated_at":   generated_at,
        "inactive_count": inactive,
        "organization":   org,
        "teams":          teams,
        "at_risk": [{
            "name": u["name"], "teams": u["teams"],
            "activity_pct": u["activity_pct"],
            "productivity_pct": u["productivity_pct"],
            "idle": round(u["idle"], 2),
        } for u in at_risk],
    }
