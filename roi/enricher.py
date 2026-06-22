"""Pre-compute derived intelligence from raw metrics (no LLM needed)."""

from .parser import _fh, _clock


def enrich(data: dict) -> dict:
    """
    Adds derived fields to the metrics dict that the analyst agent
    can reason over — team deltas, at-risk severity, idle recovery potential.
    All deterministic Python — no LLM calls.
    """
    org   = data["organization"]
    teams = data["teams"]

    for t in teams:
        t["_prod_delta"]     = round(t["productivity_pct"] - org["productivity_pct"], 1)
        t["_activity_delta"] = round(t["activity_pct"]     - org["activity_pct"],     1)

    for u in data["at_risk"]:
        u["_severity"] = round(
            (org["activity_pct"]     - u["activity_pct"]) +
            (org["productivity_pct"] - u["productivity_pct"]), 1
        )

    idle_recovery_h = round(org["idle"] * (org["activity_pct"] / 100), 1)

    return {
        **data,
        "enriched": {
            "idle_recovery_h":    idle_recovery_h,
            "idle_recovery_fmt":  _fh(idle_recovery_h),
            "top_team":           teams[0]["name"]  if teams else "",
            "bottom_team":        teams[-1]["name"] if len(teams) > 1 else "",
            "top_team_prod":      teams[0]["productivity_pct"]  if teams else 0,
            "bottom_team_prod":   teams[-1]["productivity_pct"] if len(teams) > 1 else 0,
            "at_risk_names":      [u["name"] for u in data["at_risk"][:3]],
            "org_idle_fmt":       _fh(org["idle"]),
            "org_productive_fmt": _fh(org["productive"]),
            "org_logged_fmt":     _fh(org["logged"]),
        },
    }
