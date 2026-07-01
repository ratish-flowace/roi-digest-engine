"""Pre-compute derived intelligence from raw metrics (no LLM needed)."""

from .parser import _fh, _clock, _num_in


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

    # Unlockable capacity — the recoverable slice of idle if idle dropped to the
    # org activity ratio. A strict SUBSET of total idle, never the full idle figure.
    unlockable_capacity_h = round(org["idle"] * (org["activity_pct"] / 100), 1)

    # Platform coverage / dormant seats (present in API mode; absent in CSV mode)
    coverage = data.get("coverage")
    coverage_pct = coverage["coverage_pct"] if coverage else None
    under_covered_teams = []
    if coverage:
        for name, c in coverage["teams"].items():
            if name == "No Team":  # junk bucket, not a real team
                continue
            if c["enabled"] >= 3 and c["coverage_pct"] < 60:
                under_covered_teams.append({"name": name, **c})
        under_covered_teams.sort(key=lambda x: x["coverage_pct"])
        under_covered_teams = under_covered_teams[:5]

    return {
        **data,
        "enriched": {
            "unlockable_capacity_h":   unlockable_capacity_h,
            "unlockable_capacity_fmt": f"{_num_in(unlockable_capacity_h)} hours",
            "capacity_value":          None,  # seam: set when a loaded-cost rate exists
            "idle_recovery_h":         unlockable_capacity_h,   # legacy alias
            "idle_recovery_fmt":       f"{_num_in(unlockable_capacity_h)} hours",
            "dormant_count":           data.get("inactive_count", 0),
            "coverage_pct":            coverage_pct,
            "under_covered_teams":     under_covered_teams,
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
