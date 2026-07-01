"""
Email-safe HTML digest renderer.

Produces a 600px-wide, table-based, fully inline-styled HTML email
compatible with Gmail, Outlook, and Apple Mail.

Rules strictly followed:
- No JavaScript
- No CSS variables — all colors hardcoded hex
- No flexbox/grid — <table> layout only
- No Google Fonts — system font stack
- All styles inline via style="" attributes
- Max-width 600px
"""

import os
import re
from urllib.parse import quote_plus


def _add_bgcolor(html: str) -> str:
    # Add bgcolor attribute for Gmail compatibility — CSS background is stripped on paste
    def _patch(m):
        tag, color = m.group(1), m.group(2)
        if 'bgcolor=' in tag:
            return m.group(0)
        return f'{tag} bgcolor="{color}">'
    return re.sub(
        r'(<(?:table|td|tr)[^>]*style="[^"]*background:(#[0-9A-Fa-f]{6})[^"]*")[^>]*>',
        _patch,
        html,
    )

from .config import TRACKING_PIXEL_URL
from .parser import _fh

# ── Colors (hardcoded — no CSS variables in email) ────────────────────────────
_BG       = "#0F1115"
_BG_CARD  = "#1A1D23"
_BG_RAISE = "#20242C"
_BORDER   = "#2A2F38"
_TEAL     = "#00D4AA"
_ORANGE   = "#F25425"
_BLUE     = "#4A90E2"
_RED      = "#EF4444"
_AMBER    = "#F59E0B"
_GREEN    = "#22C55E"
_TEXT     = "#FFFFFF"
_SOFT     = "#D4D8DD"
_MUTED    = "#8A929E"
_DIM      = "#5A6270"
_FONT     = "-apple-system, 'Segoe UI', Arial, sans-serif"
_MONO     = "'Courier New', Courier, monospace"


# ── Logo ──────────────────────────────────────────────────────────────────────

def _get_logo_src() -> str:
    import base64
    png = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logo.png")
    if not os.path.exists(png):
        return ""
    with open(png, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


_LOGO_SRC = _get_logo_src()


# ── RAG badge (text-only, no JS) ──────────────────────────────────────────────

def _rag_prod(pct, org_pct):
    diff = pct - org_pct
    if diff >= -3:  return ("●", _GREEN,  "On target")
    if diff >= -10: return ("●", _AMBER,  "Below avg")
    return                 ("●", _RED,    "At risk")

def _severity_badge(severity):
    if severity >= 20: return ("High",   _RED,   "rgba(239,68,68,.15)")
    if severity >= 10: return ("Medium", _AMBER, "rgba(245,158,11,.15)")
    return                    ("Watch",  _GREEN, "rgba(34,197,94,.12)")

def _team_status(prod_delta):
    if prod_delta >= 3:  return ("Leading",  _TEAL)
    if prod_delta >= -3: return ("On Track",  _BLUE)
    return                      ("Watch",    _ORANGE)


# ── Layout helpers ────────────────────────────────────────────────────────────

def _wrap(content, bg=_BG, max_width=600):
    """Outer email wrapper."""
    return (
        f'<table width="100%" border="0" cellpadding="0" cellspacing="0" '
        f'style="background:{bg};font-family:{_FONT}">'
        f'<tr><td align="center" style="padding:24px 16px;background:{bg}">'
        f'<table width="{max_width}" border="0" cellpadding="0" cellspacing="0" '
        f'style="max-width:{max_width}px;width:100%">'
        f'{content}'
        f'</table></td></tr></table>'
    )

def _row(content, bg=_BG_CARD, border_top=False):
    top_border = f'border-top:1px solid {_BORDER};' if border_top else ''
    return (
        f'<tr><td style="background:{bg};{top_border}padding:0">'
        f'{content}'
        f'</td></tr>'
    )

def _spacer(h=16):
    return f'<tr><td style="height:{h}px;font-size:0;line-height:0;background:{_BG}">&nbsp;</td></tr>'

def _section_label(text):
    return (
        f'<p style="margin:0 0 12px 0;font-size:9px;font-weight:600;'
        f'letter-spacing:.18em;text-transform:uppercase;color:{_MUTED};'
        f'font-family:{_FONT}">{text}</p>'
    )


# ── Sections ──────────────────────────────────────────────────────────────────

def _header(company, period, generated_at):
    logo_html = (
        f'<img src="{_LOGO_SRC}" width="123" height="28" alt="Flowace"'
        f' style="display:block;width:123px;height:28px;border:0">'
        if _LOGO_SRC else
        f'<span style="font-size:18px;font-weight:700;color:{_TEAL};font-family:{_FONT}'
        f';white-space:nowrap">Flowace</span>'
    )
    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:20px 28px;border-bottom:1px solid {_BORDER}">
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
      <tr>
        <td width="140" valign="top" style="vertical-align:top">{logo_html}</td>
        <td valign="top" style="text-align:right;vertical-align:top;padding-left:12px">
          <p style="margin:0;font-size:13px;font-weight:600;color:{_TEXT};font-family:{_FONT};text-align:right;word-break:break-word">{company}</p>
          <p style="margin:2px 0 0;font-size:11px;color:{_MUTED};font-family:{_FONT};text-align:right">{period}</p>
          <p style="margin:6px 0 0;font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
             color:{_ORANGE};border:1px solid {_ORANGE};border-radius:3px;padding:2px 7px;
             display:inline-block;font-family:{_FONT};text-align:right;white-space:nowrap">
            Confidential
          </p>
        </td>
      </tr>
    </table>
  </td>
</tr>"""


def _exec_summary(summary):
    if not summary:
        return ""
    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:24px 28px">
    {_section_label("Executive Summary")}
    <p style="margin:0;font-size:14px;color:{_SOFT};line-height:1.75;font-family:{_FONT}">{summary}</p>
  </td>
</tr>"""


def _kpis(org, enriched):
    def cell(label, value, color, sub=""):
        return (
            f'<td width="33%" style="padding:16px 12px;background:{_BG_RAISE};'
            f'border-radius:6px;text-align:center">'
            f'<p style="margin:0 0 6px;font-size:9px;font-weight:600;letter-spacing:.12em;'
            f'text-transform:uppercase;color:{_MUTED};font-family:{_FONT}">{label}</p>'
            f'<p style="margin:0;font-size:22px;font-weight:700;color:{color};'
            f'font-family:{_MONO}">{value}</p>'
            f'{"" if not sub else f"""<p style="margin:4px 0 0;font-size:10px;color:{_DIM};font-family:{_FONT}">{sub}</p>"""}'
            f'</td>'
        )

    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:20px 28px">
    {_section_label("Key Metrics")}
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
      <tr>
        {cell("Avg Productivity", f"{org['productivity_pct']}%", _TEAL, "of active time")}
        <td width="2%" style="padding:0">&nbsp;</td>
        {cell("Avg Activity", f"{org['activity_pct']}%", _BLUE, "of logged hours")}
        <td width="2%" style="padding:0">&nbsp;</td>
        {cell("Idle Hours", enriched['org_idle_fmt'], _ORANGE, f"{org['idle_pct']}% of logged")}
      </tr>
    </table>
  </td>
</tr>"""


def _takeaway(key_takeaway, financial_insight):
    if not key_takeaway:
        return ""
    fi_line = (
        f'<p style="margin:6px 0 0;font-size:11px;color:{_MUTED};font-family:{_FONT}">'
        f'{financial_insight}</p>' if financial_insight else ""
    )
    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:20px 28px">
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
      <tr>
        <td width="4" style="background:{_TEAL};border-radius:2px">&nbsp;</td>
        <td style="padding-left:14px">
          <p style="margin:0 0 4px;font-size:9px;font-weight:700;letter-spacing:.18em;
             text-transform:uppercase;color:{_TEAL};font-family:{_FONT}">Key Takeaway</p>
          <p style="margin:0;font-size:13px;color:{_SOFT};line-height:1.6;font-family:{_FONT}">{key_takeaway}</p>
          {fi_line}
        </td>
      </tr>
    </table>
  </td>
</tr>"""


def _teams(teams, org_prod):
    if not teams:
        return ""

    total = len(teams)
    visible = teams[:10]
    more_count = total - 10
    label = (
        f"Team Performance — top 10 of {total} teams"
        if more_count > 0 else
        f"Team Performance ({total} team{'s' if total != 1 else ''})"
    )

    rows = ""
    for t in visible:
        status_label, status_color = _team_status(t.get("_prod_delta", 0))
        dot, dot_color, _ = _rag_prod(t["productivity_pct"], org_prod)
        rows += (
            f'<tr style="border-bottom:1px solid {_BORDER}">'
            f'<td width="45%" style="padding:10px 0;font-family:{_FONT}">'
            f'<p style="margin:0;font-size:12px;font-weight:500;color:{_TEXT};word-break:break-word">{t["name"]}</p>'
            f'<p style="margin:3px 0 0;font-size:10px;font-weight:700;letter-spacing:.06em;'
            f'text-transform:uppercase;color:{status_color};white-space:nowrap">● {status_label}</p>'
            f'</td>'
            f'<td style="padding:10px 4px;font-size:11px;color:{_MUTED};text-align:center;white-space:nowrap;font-family:{_FONT}">{t["n"]}</td>'
            f'<td style="padding:10px 4px;font-size:12px;font-weight:600;color:{dot_color};'
            f'text-align:center;white-space:nowrap;font-family:{_MONO}">'
            f'<span style="color:{dot_color}">{dot}</span> {t["productivity_pct"]}%</td>'
            f'<td style="padding:10px 0;font-size:12px;color:{_SOFT};text-align:center;white-space:nowrap;font-family:{_MONO}">{t["activity_pct"]}%</td>'
            f'</tr>'
        )

    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:20px 28px">
    {_section_label(label)}
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
      <tr style="border-bottom:1px solid {_BORDER}">
        <th width="45%" style="text-align:left;font-size:9px;font-weight:600;letter-spacing:.1em;
            text-transform:uppercase;color:{_DIM};padding:0 0 8px;font-family:{_FONT}">Team</th>
        <th style="text-align:center;font-size:9px;font-weight:600;letter-spacing:.1em;
            text-transform:uppercase;color:{_DIM};padding:0 4px 8px;white-space:nowrap;font-family:{_FONT}">Members</th>
        <th style="text-align:center;font-size:9px;font-weight:600;letter-spacing:.1em;
            text-transform:uppercase;color:{_DIM};padding:0 4px 8px;white-space:nowrap;font-family:{_FONT}">Prod %</th>
        <th style="text-align:center;font-size:9px;font-weight:600;letter-spacing:.1em;
            text-transform:uppercase;color:{_DIM};padding:0 0 8px;white-space:nowrap;font-family:{_FONT}">Activity %</th>
      </tr>
      {rows}
    </table>
    {f'<p style="margin:10px 0 0;font-size:11px;color:{_MUTED};font-family:{_FONT}">+ {more_count} more teams — see full dashboard for complete breakdown.</p>' if more_count > 0 else ""}
  </td>
</tr>"""


def _recommendations(recs):
    if not recs:
        return ""
    items = "".join(
        f'<tr><td style="padding:8px 0;border-bottom:1px solid {_BORDER}">'
        f'<table border="0" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="width:24px;vertical-align:top;padding-top:1px">'
        f'<span style="font-size:11px;font-weight:700;color:{_TEAL};font-family:{_MONO}">0{i+1}</span>'
        f'</td>'
        f'<td style="font-size:12px;color:{_SOFT};line-height:1.55;font-family:{_FONT}">{rec}</td>'
        f'</tr></table></td></tr>'
        for i, rec in enumerate(recs[:3])
    )
    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:20px 28px">
    {_section_label("What To Do Next")}
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
      {items}
    </table>
  </td>
</tr>"""


def _at_risk(at_risk_list, at_risk_detail):
    if not at_risk_list:
        return ""

    rows = ""
    for u in at_risk_list[:8]:  # cap at 8 in email
        sev = u.get("_severity", 0)
        badge_label, badge_color, badge_bg = _severity_badge(sev)
        detail = at_risk_detail.get(u["name"], "")
        rows += (
            f'<tr style="border-bottom:1px solid {_BORDER}">'
            f'<td valign="top" style="padding:10px 0;vertical-align:top">'
            f'<p style="margin:0;font-size:12px;font-weight:600;color:{_TEXT};font-family:{_FONT};word-break:break-word">{u["name"]}</p>'
            f'<p style="margin:2px 0 0;font-size:10px;color:{_MUTED};font-family:{_FONT};word-break:break-word;overflow-wrap:break-word">{", ".join(u["teams"])}</p>'
            f'{"" if not detail else f"""<p style="margin:4px 0 0;font-size:11px;color:{_SOFT};line-height:1.4;font-family:{_FONT}">{detail}</p>"""}'
            f'</td>'
            f'<td width="80" valign="top" style="padding:10px 0 10px 10px;text-align:right;vertical-align:top;white-space:nowrap">'
            f'<span style="font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;'
            f'padding:2px 7px;border-radius:3px;color:{badge_color};background:{badge_bg};'
            f'border:1px solid {badge_color};font-family:{_FONT};white-space:nowrap;display:inline-block;text-align:center">{badge_label}</span>'
            f'<p style="margin:5px 0 0;font-size:13px;font-weight:700;color:{_ORANGE};'
            f'text-align:right;font-family:{_MONO};white-space:nowrap">{u["productivity_pct"]}%</p>'
            f'<p style="margin:2px 0 0;font-size:9px;color:{_DIM};text-align:right;font-family:{_FONT};white-space:nowrap">productivity</p>'
            f'</td>'
            f'</tr>'
        )

    total = len(at_risk_list)
    more  = (f'<p style="margin:12px 0 0;font-size:11px;color:{_MUTED};font-family:{_FONT}">'
             f'+ {total - 8} more employees — see full dashboard for complete list.</p>'
             if total > 8 else "")

    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:20px 28px;border-top:1px solid rgba(242,84,37,.3)">
    {_section_label(f"Employees Needing Attention ({total})")}
    <table width="100%" border="0" cellpadding="0" cellspacing="0">
      {rows}
    </table>
    {more}
  </td>
</tr>"""


def _cta_section(share_url: str) -> str:
    if not share_url:
        return ""
    return f"""
<tr>
  <td style="background:{_BG_CARD};padding:20px 28px;text-align:center;border-top:1px solid {_BORDER}">
    <p style="margin:0 0 14px;font-size:12px;color:{_MUTED};font-family:{_FONT}">
      Full interactive dashboard with team drill-down and quadrant analysis
    </p>
    <a href="{share_url}"
       style="display:inline-block;background:{_TEAL};color:#0F1115;font-size:13px;
              font-weight:700;letter-spacing:.04em;padding:10px 32px;border-radius:6px;
              text-decoration:none;font-family:{_FONT}">
      View Full Dashboard &rarr;
    </a>
    <p style="margin:10px 0 0;font-size:10px;color:{_DIM};font-family:{_FONT}">Link expires in 7 days</p>
  </td>
</tr>"""


def _footer(company, generated_at):
    return f"""
<tr>
  <td style="background:{_BG};padding:20px 28px;border-top:1px solid {_BORDER}">
    <p style="margin:0;font-size:11px;color:{_DIM};font-family:{_FONT}">
      Prepared for {company} leadership &nbsp;·&nbsp; Confidential &nbsp;·&nbsp; {generated_at}
    </p>
    <p style="margin:4px 0 0;font-size:10px;color:{_DIM};font-family:{_FONT}">
      Auto-generated by Flowace ROI Engine &nbsp;·&nbsp; Open the attached .html for the full interactive dashboard
    </p>
  </td>
</tr>"""


# ── Public API ────────────────────────────────────────────────────────────────

def _tracking_pixel(company: str, report_date: str, pixel_url: str, nonce: str = "") -> str:
    if not pixel_url:
        return ""
    url = (
        f"{pixel_url.rstrip('?&')}"
        f"?company={quote_plus(company)}"
        f"&date={quote_plus(report_date)}"
        + (f"&nonce={nonce}" if nonce else "")
    )
    return (
        f'<img src="{url}" width="1" height="1" alt="" border="0" '
        f'style="display:block;width:1px;height:1px;max-width:1px;max-height:1px;'
        f'overflow:hidden;visibility:hidden;mso-hide:all" />'
    )


def append_cta(email_html: str, share_url: str) -> str:
    """Append CTA button after the email body, inside a properly centered 600px wrapper."""
    if not share_url:
        return email_html
    wrapper = (
        f'<table width="100%" border="0" cellpadding="0" cellspacing="0"'
        f' style="background:{_BG}">'
        f'<tr><td align="center" style="padding:0 16px 24px">'
        f'<table width="600" border="0" cellpadding="0" cellspacing="0"'
        f' style="max-width:600px;width:100%">'
        + _cta_section(share_url)
        + '</table></td></tr></table>'
    )
    return _add_bgcolor(email_html.replace("</body>", wrapper + "\n</body>"))


def render_email_html(company: str, data: dict, insights: dict, pixel_url: str = "", share_url: str = "") -> str:
    """
    Generate an email-safe static HTML digest.
    Table-based layout, inline styles, no JS, no CSS variables, no external fonts.
    Compatible with Gmail, Outlook, Apple Mail.
    """
    import secrets

    org      = data["organization"]
    enriched = data["enriched"]
    teams    = data["teams"]
    at_risk  = data.get("at_risk", [])

    at_risk_detail = insights.get("at_risk_detail", {})

    # Add severity to at_risk items if not already enriched
    for u in at_risk:
        if "_severity" not in u:
            u["_severity"] = round(
                (org["productivity_pct"] - u["productivity_pct"]) +
                (org["activity_pct"]     - u["activity_pct"]), 1
            )

    period = f"{data['period_start']} – {data['period_end']}"
    nonce  = secrets.token_hex(8)

    body = (
        _header(company, period, data["generated_at"])
        + _spacer(2)
        + _exec_summary(insights.get("executive_summary", ""))
        + _spacer(2)
        + _kpis(org, enriched)
        + _spacer(2)
        + _takeaway(insights.get("key_takeaway", ""), insights.get("financial_insight", ""))
        + _spacer(2)
        + _teams(teams, org["productivity_pct"])
        + _spacer(2)
        + _recommendations(insights.get("recommendations", []))
        + (_spacer(2) + _at_risk(at_risk, at_risk_detail) if at_risk else "")
        + _spacer(2)
        + _cta_section(share_url)
        + _spacer(2)
        + _footer(company, data["generated_at"])
    )

    pixel_html = _tracking_pixel(company, data["generated_at"], pixel_url or TRACKING_PIXEL_URL, nonce)

    return _add_bgcolor(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>{company} · Flowace ROI Digest</title>
</head>
<body bgcolor="{_BG}" style="margin:0;padding:0;background:{_BG};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%">
{_wrap(body)}
{pixel_html}
</body>
</html>""")
