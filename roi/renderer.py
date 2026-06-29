"""HTML rendering using the Flowace dashboard template."""

import json
import os
import re

from .config import GA4_MEASUREMENT_ID
from .parser import _fh, _clock

# Template is one level up from this file (project root)
_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard_template.html",
)


def _load_template():
    """
    Extract CSS, body HTML, and JS from dashboard_template.html.
    Strips the benchmark section and all hardcoded client references.
    """
    if not os.path.exists(_TEMPLATE_PATH):
        raise FileNotFoundError(f"dashboard_template.html not found at {_TEMPLATE_PATH}")

    with open(_TEMPLATE_PATH, encoding="utf-8") as f:
        lines = f.readlines()

    style_open  = next(i for i,l in enumerate(lines) if "<style>" in l)
    style_close = next(i for i,l in enumerate(lines) if "</style>" in l)
    blob_line   = next(i for i,l in enumerate(lines) if "data-blob" in l)
    js_open     = next(i for i,l in enumerate(lines) if l.strip() == "<script>")

    css  = "".join(lines[style_open+1:style_close])
    body = "".join(lines[style_close+1:blob_line])
    js   = "".join(lines[js_open+1:])
    for s in ["</html>", "</body>", "</script>"]:
        js = js.rstrip().removesuffix(s).rstrip()

    # Remove benchmark section from body
    bench_start  = body.find("  <!-- ─── Benchmark widget")
    footer_start = body.find("  <!-- ─── Footer")
    if bench_start > 0 and footer_start > bench_start:
        body = body[:bench_start] + body[footer_start:]

    # Remove renderBenchmarks from JS (prevents crash on missing DATA.benchmarks)
    bench_fn_start = js.rfind("\n// =", 0, js.find("function renderBenchmarks"))
    if bench_fn_start == -1:
        bench_fn_start = js.find("function renderBenchmarks")
    bench_call_end = js.rfind("renderBenchmarks();") + len("renderBenchmarks();")
    if bench_fn_start > 0 and bench_call_end > bench_fn_start:
        js = js[:bench_fn_start].rstrip() + "\n" + js[bench_call_end:].strip()

    # Fix hardcoded KPI "across 151 days" → dynamic
    js = re.sub(r"sub: 'across \d+ days'",
                "sub: 'across ' + DATA.period_days + ' days'", js)

    # Replace hardcoded client name with placeholder for later substitution
    js = re.sub(r"Medibuddy['']s", "{COMPANY_NAME}'s", js)
    js = re.sub(r"Medibuddy-baseline", "{COMPANY_NAME}-baseline", js)
    js = re.sub(r"same Medibuddy", "same {COMPANY_NAME}", js)
    js = re.sub(r"Medibuddy", "{COMPANY_NAME}", js)

    return css, body, js


# ── JavaScript additions injected before the template JS ─────────────────────

_INJECTED_JS = """\
// ── RAG (Red / Amber / Green) helpers ────────────────────────────────────────
// Thresholds relative to org average — adapts automatically to any tenant
function ragProd(pct) {
  const diff = pct - DATA.organization.productivity_pct;
  if (diff >= -3)  return 'green';
  if (diff >= -10) return 'yellow';
  return 'red';
}
function ragAct(pct) {
  const diff = pct - DATA.organization.activity_pct;
  if (diff >= -3)  return 'green';
  if (diff >= -10) return 'yellow';
  return 'red';
}
function ragIdle(idlePct) {
  const orgIdle = DATA.organization.idle_pct || 1;
  const ratio = idlePct / orgIdle;
  if (ratio <= 1)    return 'green';
  if (ratio <= 1.5)  return 'yellow';
  return 'red';
}
function ragDot(rag, label) {
  const colors = { green: '#22C55E', yellow: '#F59E0B', red: '#EF4444' };
  const c = colors[rag] || colors.green;
  const tip = label ? ` title="${label}"` : '';
  return `<span${tip} style="display:inline-block;width:8px;height:8px;border-radius:50%;` +
    `background:${c};flex-shrink:0;box-shadow:0 0 0 2px ${c}33;margin-left:6px;vertical-align:middle"></span>`;
}
function ragBadge(severity) {
  if (severity >= 20) return `<span style="font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:3px;background:rgba(239,68,68,.15);color:#EF4444;border:1px solid rgba(239,68,68,.3)">High</span>`;
  if (severity >= 10) return `<span style="font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:3px;background:rgba(245,158,11,.15);color:#F59E0B;border:1px solid rgba(245,158,11,.3)">Medium</span>`;
  return `<span style="font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:3px;background:rgba(34,197,94,.12);color:#22C55E;border:1px solid rgba(34,197,94,.25)">Watch</span>`;
}

// ── Team insights + narratives ─────────────────────────────────────────────
function getTeamInsight(name) {
  return (DATA.team_insights && DATA.team_insights[name]) ? DATA.team_insights[name] : '';
}
function getTeamNarrative(name) {
  return (DATA.team_narratives && DATA.team_narratives[name]) ? DATA.team_narratives[name] : '';
}

// ── At-risk panel with pagination ─────────────────────────────────────────
const AT_RISK_PAGE_SIZE = 5;
let atRiskExpanded = false;

function renderAtRiskRow(u) {
  const detail   = (DATA.at_risk_detail && DATA.at_risk_detail[u.name]) ? DATA.at_risk_detail[u.name] : '';
  const severity = (DATA.organization.productivity_pct - u.productivity_pct) +
                   (DATA.organization.activity_pct - u.activity_pct);
  return `<div class="at-risk-row">
    <div>
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span style="font-size:13px;font-weight:600;color:#fff">${u.name}</span>
        ${ragBadge(severity)}
      </div>
      <div style="font-size:11px;color:#8A929E">${u.teams.join(', ')}</div>
    </div>
    <div class="at-risk-detail" style="font-size:12px;color:#D4D8DD;line-height:1.5">${detail || 'Below company average on both productivity and activity.'}</div>
    <div style="text-align:right">
      <div style="display:flex;align-items:center;justify-content:flex-end;gap:4px">
        <span style="font-size:16px;font-weight:700;font-family:'JetBrains Mono',monospace;color:#F25425">${u.productivity_pct.toFixed(1)}%</span>
        ${ragDot(ragProd(u.productivity_pct))}
      </div>
      <div style="font-size:11px;color:#8A929E;margin-top:2px">productivity</div>
      <div style="font-size:11px;color:#5A6270;margin-top:1px">−${severity.toFixed(1)} pts combined gap</div>
    </div>
  </div>`;
}

function renderAtRisk() {
  const section    = document.getElementById('at-risk-section');
  const rowsEl     = document.getElementById('at-risk-rows');
  const subEl      = document.getElementById('at-risk-sub');
  const toggleWrap = document.getElementById('at-risk-toggle');
  const toggleBtn  = document.getElementById('at-risk-toggle-btn');
  const list = DATA.at_risk || [];

  if (!list.length) { section.style.display = 'none'; return; }

  section.style.display = '';
  const total   = list.length;
  const showing = atRiskExpanded ? total : Math.min(AT_RISK_PAGE_SIZE, total);

  subEl.textContent = `${total} employee${total > 1 ? 's' : ''} below company average on both metrics`;
  rowsEl.innerHTML  = list.slice(0, showing).map(renderAtRiskRow).join('');

  const rows = rowsEl.querySelectorAll('[style*="border-bottom"]');
  if (rows.length) rows[rows.length - 1].style.borderBottom = 'none';

  if (total > AT_RISK_PAGE_SIZE) {
    toggleWrap.style.display = '';
    toggleBtn.textContent = atRiskExpanded
      ? 'Show less'
      : `Show all ${total} employees ↓`;
  } else {
    toggleWrap.style.display = 'none';
  }
}

window.toggleAtRisk = function() {
  atRiskExpanded = !atRiskExpanded;
  renderAtRisk();
};

"""

_RESPONSIVE_CSS = """\
/* Flowace logo */
.logo { display:flex;align-items:center;gap:12px; }

/* ── Responsive overrides ──────────────────────────────────────────────── */
.rec-grid { display:grid;grid-template-columns:repeat(3,1fr);gap:12px; }
@media(max-width:900px) { .rec-grid { grid-template-columns:repeat(2,1fr); } }
@media(max-width:560px) { .rec-grid { grid-template-columns:1fr; } }

.quadrant-grid { grid-template-columns:1fr 340px; }
@media(max-width:960px) { .quadrant-grid { grid-template-columns:1fr; } }

.at-risk-row { display:grid;grid-template-columns:200px 1fr 130px;align-items:center;gap:16px;padding:13px 0;border-bottom:1px solid #1F2329; }
@media(max-width:700px) { .at-risk-row { grid-template-columns:1fr auto;gap:10px; } .at-risk-detail { display:none; } }
@media(max-width:420px) { .at-risk-row { grid-template-columns:1fr; } }

@media(max-width:600px) { .app { padding:20px 16px 56px; } }
@media(max-width:700px) { .topbar { flex-direction:column;align-items:flex-start;gap:12px; } .topbar-right { flex-wrap:wrap;gap:8px; } }
@media(max-width:960px) { h1 { font-size:48px; } }
@media(max-width:700px) { h1 { font-size:36px; } }
@media(max-width:480px) { h1 { font-size:28px; } }
@media(max-width:700px) { .hero { grid-template-columns:1fr; } .hero-meta { text-align:left; } }
@media(max-width:1100px) { .kpi-row { grid-template-columns:repeat(3,1fr); } }
@media(max-width:640px)  { .kpi-row { grid-template-columns:repeat(2,1fr); } .kpi-value { font-size:22px; } }
@media(max-width:380px)  { .kpi-row { grid-template-columns:1fr; } }
@media(max-width:700px) { .timeline-bar { grid-template-columns:90px 1fr;gap:8px; } .tb-meta { display:none; } }
@media(max-width:420px) { .timeline-bar { grid-template-columns:1fr; } .tb-track { display:none; } }
@media(max-width:900px) { .teams-grid { grid-template-columns:repeat(2,1fr); } }
@media(max-width:560px) { .teams-grid { grid-template-columns:1fr; } }
@media(max-width:700px) { .td-summary { flex-wrap:wrap;gap:12px 20px; } .td-title { font-size:20px; } }
@media(max-width:800px) { .team-detail { overflow-x:auto; } .individuals-table { min-width:560px; } }
.footer { flex-wrap:wrap;gap:12px; }
@media(max-width:720px) { .footer-compliance { flex-wrap:wrap;gap:6px; } .footer-compliance span:first-child { width:100%; } }
@media(max-width:600px) { .footer { flex-direction:column;align-items:flex-start;gap:10px;margin-top:48px; } }
@media(max-width:600px) { .exec-summary-inner { padding:18px !important; } }
"""


def _build_tracking_html(company: str, report_date: str, measurement_id: str) -> str:
    if not measurement_id:
        return ""
    safe_company = company.replace("\\", "\\\\").replace("'", "\\'")
    safe_date    = report_date.replace("\\", "\\\\").replace("'", "\\'")
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={measurement_id}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{ dataLayer.push(arguments); }}
  gtag('js', new Date());
  gtag('config', '{measurement_id}');
  gtag('event', 'page_view', {{
    'company_name': '{safe_company}',
    'report_date':  '{safe_date}'
  }});
  (function() {{
    var fired = new Set();
    var obs = new IntersectionObserver(function(entries) {{
      entries.forEach(function(e) {{
        if (e.isIntersecting && !fired.has(e.target)) {{
          fired.add(e.target);
          var t = (e.target.querySelector('.section-title') || {{}}).textContent || 'unknown';
          gtag('event', 'scroll_section', {{
            'company_name': '{safe_company}',
            'report_date':  '{safe_date}',
            'section_title': t.trim()
          }});
        }}
      }});
    }}, {{threshold: 0.3}});
    document.querySelectorAll('.section').forEach(function(el) {{ obs.observe(el); }});
  }})();
  (function() {{
    var elapsed = 0, ticks = 0;
    var timer = setInterval(function() {{
      elapsed += 30; ticks += 1;
      gtag('event', 'time_on_page', {{
        'company_name': '{safe_company}',
        'report_date':  '{safe_date}',
        'seconds': elapsed
      }});
      if (ticks >= 10) {{ clearInterval(timer); }}
    }}, 30000);
  }})();
  document.addEventListener('click', function(e) {{
    var el = e.target.closest('a[href], button');
    if (!el) return;
    gtag('event', 'cta_click', {{
      'company_name':  '{safe_company}',
      'report_date':   '{safe_date}',
      'element_text':  (el.textContent || '').trim().slice(0, 100),
      'element_href':  el.getAttribute('href') || ''
    }});
  }});
  (function() {{
    var _map = {{
      '.team-card':         'team_drill_down',
      '.qdot':              'quadrant_open',
      '.breadcrumb .crumb': 'breadcrumb_nav',
      '.quadrant-back':     'quadrant_back',
      '.td-back':           'individual_back'
    }};
    document.addEventListener('click', function(e) {{
      Object.keys(_map).forEach(function(sel) {{
        if (e.target.closest(sel)) {{
          var label = '';
          var el = e.target.closest(sel);
          if (sel === '.team-card') {{
            var nameEl = el.querySelector('.tc-name');
            label = nameEl ? nameEl.textContent.trim() : '';
          }} else if (sel === '.qdot') {{
            label = el.getAttribute('data-team') || el.getAttribute('title') || '';
          }} else if (sel === '.breadcrumb .crumb') {{
            label = el.textContent.trim();
          }}
          gtag('event', 'dashboard_interaction', {{
            'company_name':     '{safe_company}',
            'report_date':      '{safe_date}',
            'interaction_type': _map[sel],
            'element_label':    label
          }});
        }}
      }});
    }});
  }})();
</script>"""


def render_html(company: str, data: dict, insights: dict, ga4_id: str = "") -> str:
    css, body, js = _load_template()

    org = data["organization"]

    # ── Company name substitutions ────────────────────────────────────────────
    js = js.replace("{COMPANY_NAME}", company)
    body = re.sub(r'<span class="client">[^<]+</span>',
                  f'<span class="client">{company}</span>', body)
    body = body.replace("When Medibuddy Works", "Working Hours")
    body = body.replace("Where Medibuddy stands vs the market", "Performance Overview")
    body = body.replace(
        "Prepared for Medibuddy leadership · Confidential · June 2026",
        f"Prepared for {company} leadership · Confidential · {data['generated_at']}"
    )
    body = re.sub(r'\bMedibuddy\b', company, body)

    # ── Hero section ──────────────────────────────────────────────────────────
    hero_narrative = insights.get("hero_narrative", "")
    h1_stat = f"{org['productivity_pct']}% productivity."
    h1_sub  = f'<span class="accent">{org["n"]} people. {data["period_days"]} days.</span>'
    body = re.sub(
        r'<h1>89% productivity\.<br><span class="accent">The strength is the work\.</span></h1>',
        f'<h1>{h1_stat}<br>{h1_sub}</h1>', body
    )
    body = re.sub(
        r'<p>Across <span class="strong" id="hero-hours"></span> hours logged.*?</p>',
        f'<p>{hero_narrative}</p><span id="hero-hours" style="display:none"></span>',
        body, flags=re.DOTALL
    )

    # ── Fix hardcoded dates/numbers ───────────────────────────────────────────
    body = re.sub(r'<span class="meta-value">151 days · 5 months</span>',
                  f'<span class="meta-value">{data["period_days"]} days</span>', body)
    body = re.sub(r'<span class="meta-value">June 2026</span>',
                  f'<span class="meta-value">{data["generated_at"]}</span>', body)
    body = re.sub(
        r'Aggregated across \d+ members, \d+ teams · [^<]+',
        f'Aggregated across {org["n"]} employees, {len(data["teams"])} teams · '
        f'{data["period_start"]} – {data["period_end"]}',
        body
    )
    js = re.sub(r'period 1 Jan – 31 May 2026',
                f'period {data["period_start"]} – {data["period_end"]}', js)

    # ── Inject new sections ───────────────────────────────────────────────────
    key_takeaway      = insights.get("key_takeaway", "")
    recommendations   = insights.get("recommendations", [])
    financial_insight = insights.get("financial_insight", "")
    executive_summary = insights.get("executive_summary", "")

    rec_cards_html = "".join(
        f'<div style="background:#1A1D23;border:1px solid #2A2F38;border-radius:10px;'
        f'padding:18px;position:relative;overflow:hidden">'
        f'<div style="position:absolute;top:0;left:0;right:0;height:2px;background:#00D4AA;opacity:.6"></div>'
        f'<div style="font-size:28px;font-weight:700;color:rgba(0,212,170,.2);'
        f'font-family:\'JetBrains Mono\',monospace;line-height:1;margin-bottom:10px">0{i+1}</div>'
        f'<div style="font-size:13px;color:#D4D8DD;line-height:1.6">{rec}</div></div>'
        for i, rec in enumerate(recommendations[:3])
    )

    new_sections = (
        (f'<div class="section" style="margin-bottom:40px">'
         f'<div class="section-head">'
         f'<div class="section-title">Executive Summary</div>'
         f'<div class="section-sub">What leadership needs to know</div></div>'
         f'<div class="exec-summary-inner" style="background:#1A1D23;border:1px solid #2A2F38;'
         f'border-radius:10px;padding:28px 32px">'
         f'<div style="font-size:15px;color:#D4D8DD;line-height:1.8;max-width:900px">'
         f'{executive_summary}</div></div></div>' if executive_summary else "")
        + f'<div style="margin-bottom:40px;padding:18px 24px;background:rgba(0,212,170,.07);'
          f'border:1px solid rgba(0,212,170,.3);border-radius:10px">'
          f'<div style="font-size:9px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;'
          f'color:#00D4AA;margin-bottom:8px">KEY TAKEAWAY</div>'
          f'<div style="font-size:14px;color:#D4D8DD;line-height:1.6">{key_takeaway}</div>'
          + (f'<div style="font-size:12px;color:#8A929E;margin-top:6px">{financial_insight}</div>'
             if financial_insight else "")
          + "</div>"
        + (f'<div class="section"><div class="section-head">'
           f'<div class="section-title">What To Do Next</div>'
           f'<div class="section-sub">Three specific actions, ordered by impact</div></div>'
           f'<div class="rec-grid">{rec_cards_html}</div></div>'
           if rec_cards_html else "")
    )

    first_section = body.find('  <div class="section">')
    if first_section > 0:
        body = body[:first_section] + new_sections + body[first_section:]

    # At-risk panel (JS-driven)
    at_risk_panel = (
        '<div class="section" id="at-risk-section" style="display:none">'
        '<div class="section-head">'
        '<div class="section-title">Employees Needing Attention</div>'
        '<div class="section-sub" id="at-risk-sub"></div></div>'
        '<div style="background:#1A1D23;border:1px solid rgba(242,84,37,.3);'
        'border-radius:10px;padding:0 24px">'
        '<div id="at-risk-rows"></div>'
        '<div id="at-risk-toggle" style="display:none;padding:14px 0;'
        'border-top:1px solid #1F2329;text-align:center">'
        '<button onclick="toggleAtRisk()" style="background:none;border:1px solid #2A2F38;'
        'color:#8A929E;font-size:12px;padding:6px 20px;border-radius:6px;cursor:pointer;'
        'font-family:inherit" id="at-risk-toggle-btn"></button>'
        '</div></div></div>'
    )
    quadrant_section = body.find('  <!-- ─── Quadrant analysis')
    if quadrant_section > 0:
        body = body[:quadrant_section] + at_risk_panel + "\n" + body[quadrant_section:]

    # ── Store insights in data blob ───────────────────────────────────────────
    data["benchmarks"]     = []
    data["team_insights"]  = insights.get("team_insights",  {})
    data["team_narratives"]= insights.get("team_narratives", data.get("team_narratives", {}))
    data["at_risk_detail"] = insights.get("at_risk_detail", {})

    # ── Patch JS ──────────────────────────────────────────────────────────────
    # RAG on KPI cards
    js = js.replace(
        "{ label: 'Activity Rate',  value: org.activity_pct + '%',",
        "{ label: 'Activity Rate',  value: org.activity_pct + '%' + ragDot(ragAct(org.activity_pct), 'vs org baseline'),",
    )
    js = js.replace(
        "{ label: 'Productivity',   value: org.productivity_pct + '%',",
        "{ label: 'Productivity',   value: org.productivity_pct + '%' + ragDot(ragProd(org.productivity_pct), 'vs org baseline'),",
    )
    js = js.replace(
        "{ label: 'Idle Exposure',  value: org.idle_pct + '%',",
        "{ label: 'Idle Exposure',  value: org.idle_pct + '%' + ragDot(ragIdle(org.idle_pct), 'idle vs org avg'),",
    )
    # RAG on individual table
    js = js.replace(
        '<span class="metric-bar"><span class="metric-bar-fill" style="width:${activityBar}%"></span></span>${m.activity_pct.toFixed(1)}%',
        '<span class="metric-bar"><span class="metric-bar-fill" style="width:${activityBar}%"></span></span>${m.activity_pct.toFixed(1)}%${ragDot(ragAct(m.activity_pct))}',
    )
    js = js.replace(
        '<td class="num-col">${m.productivity_pct.toFixed(1)}%</td>',
        '<td class="num-col">${m.productivity_pct.toFixed(1)}%${ragDot(ragProd(m.productivity_pct))}</td>',
    )
    # Team narrative in drill-down
    js = js.replace(
        "const indRows = inds.map((m, i) => {",
        "const narrativeHtml = getTeamNarrative(t.name)"
        " ? `<div style=\"margin:0;padding:16px 28px 0\">"
        "<div style=\"padding:14px 18px;background:rgba(0,212,170,.06);"
        "border-left:3px solid rgba(0,212,170,.35);border-radius:0 6px 6px 0\">"
        "<div style=\"font-size:13px;color:#D4D8DD;line-height:1.7\">"
        "${getTeamNarrative(t.name)}</div></div></div>` : '';\n"
        "  const indRows = inds.map((m, i) => {",
    )
    js = js.replace(
        '</div>\n      <div style="overflow-x:auto">\n        <table class="individuals-table">',
        '</div>\n      ${narrativeHtml}\n      <div style="overflow-x:auto;-webkit-overflow-scrolling:touch">\n        <table class="individuals-table" style="min-width:560px">',
    )
    # Team card status labels + RAG dot + insight chip
    js = js.replace(
        "const statusLabel = status === 'strong' ? 'Strong' : status === 'ok' ? 'Steady' : 'Watch';",
        "const statusLabel = status === 'strong' ? 'Leading' : status === 'ok' ? 'On Track' : 'Watch';",
    )
    js = js.replace(
        '<div class="tc-name">${t.name}</div>',
        '<div class="tc-name" style="display:flex;align-items:center;gap:4px">'
        '${t.name}${ragDot(ragProd(t.productivity_pct), "Productivity vs org avg")}</div>',
    )
    js = js.replace(
        '</div>\n        <div class="tc-metrics">',
        '</div>\n        ${getTeamInsight(t.name) ? `<div style="font-size:11px;color:#8A929E;font-style:italic;margin:6px 0 2px;line-height:1.4">${getTeamInsight(t.name)}</div>` : ""}\n        <div class="tc-metrics">',
    )

    # Prepend RAG/insight helpers; append at-risk init call
    js = _INJECTED_JS + js + "\n\n// Render at-risk panel on load\nrenderAtRisk();"

    blob = json.dumps(data, separators=(",", ":"))
    tracking_html = _build_tracking_html(company, data["generated_at"], ga4_id or GA4_MEASUREMENT_ID)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{company} · Flowace ROI Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
{css}
{_RESPONSIVE_CSS}
</style>
</head>
<body>
<div class="app">
{body.strip()}
</div>
<script id="data-blob" type="application/json">{blob}</script>
<script>
{js}
</script>
{tracking_html}
</body>
</html>"""
