"""API-based data parser — produces the same dict schema as parse_csv()."""

import json
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime

from .parser import _build_metrics, _safe_pct

_MS = 3_600_000  # ms per hour


def _ms_h(ms: int) -> float:
    return ms / _MS


def _entry_minutes(iso_ts: str) -> float | None:
    # Flowace stores firstEntry/lastEntry in local time despite the Z suffix
    if not iso_ts:
        return None
    try:
        clean = iso_ts.split("+")[0].replace("Z", "").strip()
        dt = datetime.fromisoformat(clean)
        minutes = dt.hour * 60 + dt.minute + dt.second / 60.0
        return round(minutes, 1) if 0 < minutes <= 1440 else None
    except Exception:
        return None


def _user_avg_times(day_wise_data: list) -> tuple:
    # Returns (avg_start_min, avg_end_min); end may be >1440 for past-midnight workers
    starts, ends = [], []
    for d in day_wise_data:
        if (d.get("unclassified_duration", 0)
                + d.get("classified_duration", 0)
                + d.get("idle_duration", 0)) == 0:
            continue
        s = _entry_minutes(d.get("firstEntry"))
        e = _entry_minutes(d.get("lastEntry"))
        if s is not None:
            starts.append(s)
        if s is not None and e is not None:
            if e < s:
                e += 1440  # normalize past-midnight end (e.g. 00:33 → 24:33)
            ends.append(e)
        elif e is not None:
            ends.append(e)

    avg_start = round(sum(starts) / len(starts), 1) if starts else None
    avg_end   = round(sum(ends) / len(ends), 1) if ends else None
    return avg_start, avg_end


def fetch_timesheets(
    token: str,
    start_date: str,
    end_date: str,
    base_url: str,
    origin: str,
) -> list:
    # origin: tenant URL e.g. "https://acme.flowace.in" (no trailing slash)
    origin  = origin.rstrip("/")
    url     = f"{base_url.rstrip('/')}/v1/Timesheets/getDailywiseTimesheet"
    payload = json.dumps({
        "userId":          [],
        "startDate":       start_date,
        "endDate":         end_date,
        "activeUsersOnly": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Authorization":   token,
            "Content-Type":    "application/json",
            "Origin":          origin,
            "Referer":         origin + "/",
            "User-Agent":      (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/149.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Timesheet API returned invalid JSON: {e}") from e
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Timesheet API returned HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Timesheet API unreachable: {e.reason}") from e


def parse_api(
    token: str,
    start_date: str,
    end_date: str,
    base_url: str = "https://api.flowace.in/prod",
    origin: str = "https://gozo.flowace.in",
) -> dict:
    raw = fetch_timesheets(token, start_date, end_date, base_url, origin)

    users: list   = []
    inactive: int = 0
    team_enabled: dict = defaultdict(int)  # provisioned seats per team (active + dormant)

    for u in raw:
        active_ms = (u.get("totalClassifiedDuration",   0)
                   + u.get("totalUnClassifiedDuration", 0))
        idle_ms   =  u.get("totalIdleDuration",          0)
        logged_h  = _ms_h(active_ms + idle_ms)

        teams_raw = u.get("teamNames", "").strip()
        teams = [t.strip() for t in teams_raw.split(";") if t.strip()] or ["No Team"]
        for t in teams:
            team_enabled[t] += 1

        if logged_h < 0.05:  # same inactivity threshold as parse_csv
            inactive += 1
            continue

        active_h  = _ms_h(active_ms)
        idle_h    = _ms_h(idle_ms)
        prod_h    = _ms_h(u.get("totalProductiveDuration",   0))
        unprod_h  = _ms_h(u.get("totalUnproductiveDuration", 0))
        neutral_h = _ms_h(u.get("totalNeutralDuration",      0))

        activity_pct     = round(active_h / logged_h * 100, 2) if logged_h > 0 else 0.0
        productivity_pct = round(prod_h   / active_h * 100, 2) if active_h > 0 else 0.0

        dw             = u.get("dayWiseData", [])
        avg_start, avg_end = _user_avg_times(dw)

        days = sum(
            1 for d in dw
            if (d.get("unclassified_duration", 0)
                + d.get("classified_duration",   0)
                + d.get("idle_duration",          0)) > 0
        )

        users.append({
            "name":             u["fullName"],
            "teams":            teams,
            "days":             float(days),
            "logged":           round(logged_h,  2),
            "active":           round(active_h,  2),
            "idle":             round(idle_h,    2),
            "productive":       round(prod_h,    2),
            "unproductive":     round(unprod_h,  2),
            "neutral":          round(neutral_h, 2),
            "activity_pct":     activity_pct,
            "productivity_pct": productivity_pct,
            "avg_start_min":    avg_start,
            "avg_end_min":      avg_end,
        })

    if not users:
        raise ValueError("No active users found in API response")

    meta = {
        "Start Date":   start_date,
        "End Date":     end_date,
        "Generated At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    result = _build_metrics(meta, users, inactive)

    # Wrap avg_end_min to 0–1439 after all averaging is done
    def _norm(m):
        return round(m % 1440, 1) if m is not None else None

    result["organization"]["avg_end_min"] = _norm(result["organization"]["avg_end_min"])
    for team in result["teams"]:
        team["avg_end_min"] = _norm(team["avg_end_min"])
        for ind in team.get("individuals", []):
            ind["avg_end_min"] = _norm(ind["avg_end_min"])

    # Platform coverage — active vs provisioned (active + dormant) seats
    active_by_team = {t["name"]: t["n"] for t in result["teams"]}
    team_cov = {}
    for name, enabled in team_enabled.items():
        active_n = active_by_team.get(name, 0)
        team_cov[name] = {
            "enabled":      enabled,
            "active":       active_n,
            "coverage_pct": _safe_pct(active_n, enabled),
        }
    total_enabled = len(users) + inactive
    result["coverage"] = {
        "enabled":      total_enabled,
        "active":       len(users),
        "dormant":      inactive,
        "coverage_pct": _safe_pct(len(users), total_enabled),
        "teams":        team_cov,
    }

    return result
