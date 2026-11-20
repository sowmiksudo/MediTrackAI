import base64
from datetime import datetime
from io import BytesIO
import os
from typing import Any, Dict, List, Optional

import qrcode
import weasyprint


def _qr_data_uri(url: str) -> str:
    img = qrcode.make(url, box_size=5, border=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _esc(val: Any) -> str:
    s = str(val if val is not None else "")
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def generate_doctor_brief_pdf(
    output_pdf: str,
    profile_info: Dict[str, Any],
    brief_data: Dict[str, Any],
    deterministic_scores: Dict[str, Any],
    normalized_labs: List[Dict[str, Any]],
    ddi_alerts: List[Dict[str, Any]],
    share_url: str,
) -> str:
    os.makedirs(os.path.dirname(output_pdf) or ".", exist_ok=True)
    qr_uri = _qr_data_uri(share_url)
    generated_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    meds = brief_data.get("active_medications", [])
    med_rows = "".join(
        f"<tr><td><strong>{_esc(m.get('brand_name'))}</strong></td>"
        f"<td>{_esc(m.get('generic_name') or 'Unverified')}</td>"
        f"<td>{_esc(m.get('dosage') or '-')}</td>"
        f"<td>{_esc(m.get('frequency_bd') or '-')}</td>"
        f"<td>{_esc(m.get('flag') or 'Active')}</td></tr>"
        for m in meds[:8]
    ) or "<tr><td colspan='5'>No active medications recorded.</td></tr>"

    lab_rows = "".join(
        f"<tr><td>{_esc(l.get('canonical_name'))}</td>"
        f"<td><strong>{_esc(l.get('canonical_value'))} {_esc(l.get('canonical_unit'))}</strong></td>"
        f"<td>{_esc(l.get('reference_range') or '-')}</td>"
        f"<td class='flag-{_esc(l.get('flag', 'normal'))}'>{_esc(str(l.get('flag', 'normal')).upper())}</td>"
        f"<td>{_esc(l.get('observed_date') or '')}</td></tr>"
        for l in normalized_labs[:8]
    ) or "<tr><td colspan='5'>No normalized lab observations recorded.</td></tr>"

    alerts_html = ""
    red_flags = brief_data.get("red_flag_summary", [])
    if red_flags or ddi_alerts:
        items = "".join(f"<li>{_esc(x)}</li>" for x in red_flags)
        items += "".join(
            f"<li><strong>[{_esc(a.get('severity','warning').upper())}]</strong> {_esc(a.get('clinical_note'))}</li>"
            for a in ddi_alerts
        )
        alerts_html = f"<div class='alert-box'><div class='box-title'>Safety, Duplicate-Generic &amp; Red-Flag Alerts</div><ul>{items}</ul></div>"

    egfr = deterministic_scores.get("egfr_ckd_epi", {})
    gly = deterministic_scores.get("glycemic_band", {})
    egfr_str = (
        f"{egfr.get('egfr_ml_min')} mL/min ({egfr.get('kdigo_stage')})"
        if egfr.get("status") == "computed"
        else f"Insufficient data ({', '.join(egfr.get('missing_inputs', []))})"
    )
    gly_str = (
        f"{gly.get('band')} — {gly.get('summary')}"
        if gly.get("status") == "computed"
        else "Insufficient glycemic labs"
    )

    obs_html = "".join(f"<li>{_esc(o)}</li>" for o in brief_data.get("clinical_observations", [])[:5])
    q_html = "".join(f"<li>{_esc(q)}</li>" for q in brief_data.get("questions_for_doctor", [])[:4])
    tl_html = "".join(
        f"<li><span class='muted'>{_esc(t.get('date'))}</span> — {_esc(t.get('summary'))} <span class='cite'>{_esc(t.get('citation'))}</span></li>"
        for t in brief_data.get("timeline_events", [])[:5]
    )

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  @page {{ size: A4; margin: 12mm 13mm; }}
  body {{ font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 9.2pt; color: #1e293b; line-height: 1.35; margin: 0; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #0f4c81; padding-bottom: 8px; margin-bottom: 8px; }}
  .brand {{ font-size: 15pt; font-weight: 700; color: #0f4c81; }}
  .sub {{ font-size: 8.5pt; color: #475569; }}
  .patient-bar {{ background: #f1f5f9; border-left: 4px solid #0f4c81; padding: 6px 10px; margin-bottom: 8px; display: flex; justify-content: space-between; }}
  .grid {{ display: flex; gap: 10px; margin-bottom: 8px; }}
  .col {{ flex: 1; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 7px 9px; }}
  h2 {{ font-size: 9.5pt; text-transform: uppercase; letter-spacing: 0.4px; color: #0f4c81; margin: 7px 0 4px 0; border-bottom: 1px solid #cbd5e1; padding-bottom: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 8.4pt; margin-bottom: 6px; }}
  th {{ background: #0f4c81; color: #ffffff; text-align: left; padding: 4px 6px; }}
  td {{ border-bottom: 1px solid #e2e8f0; padding: 3.5px 6px; vertical-align: top; }}
  .flag-high, .flag-critical {{ color: #b91c1c; font-weight: 700; }}
  .flag-low {{ color: #b45309; font-weight: 700; }}
  .flag-normal {{ color: #15803d; font-weight: 600; }}
  .alert-box {{ background: #fef2f2; border: 1px solid #ef4444; border-left: 4px solid #b91c1c; padding: 6px 9px; margin-bottom: 8px; border-radius: 3px; }}
  .box-title {{ font-weight: 700; color: #991b1b; margin-bottom: 2px; font-size: 9pt; }}
  ul {{ margin: 2px 0 4px 16px; padding: 0; }}
  li {{ margin-bottom: 2px; }}
  .muted {{ color: #64748b; font-size: 8.2pt; }}
  .cite {{ color: #0369a1; font-size: 7.8pt; font-weight: 600; }}
  .footer {{ border-top: 1px solid #cbd5e1; margin-top: 8px; padding-top: 5px; font-size: 7.6pt; color: #64748b; display: flex; justify-content: space-between; align-items: center; }}
  .qr-box {{ text-align: right; }}
  .qr-box img {{ width: 64px; height: 64px; }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="brand">MediTrackAI — 1-Page Clinical Brief</div>
      <div class="sub">Prepared for Physician Consultation (Bangladesh Clinical Standard) · Generated {_esc(generated_at)}</div>
    </div>
    <div class="qr-box">
      <img src="{qr_uri}" alt="QR"/>
      <div style="font-size:7pt;color:#475569;">Scan for live timeline</div>
    </div>
  </div>

  <div class="patient-bar">
    <div>
      <strong>Patient:</strong> {_esc(profile_info.get('display_name'))}
      ({ _esc(profile_info.get('age_label') or 'Age N/A') }, { _esc(profile_info.get('sex') or 'Sex N/A') })<br/>
      <span class="muted"><strong>Chronic Conditions:</strong> {_esc(', '.join(profile_info.get('chronic_conditions') or []) or 'None recorded')} · <strong>Allergies:</strong> {_esc(', '.join(profile_info.get('allergies') or []) or 'None recorded')}</span>
    </div>
  </div>

  {alerts_html}

  <div class="grid">
    <div class="col">
      <strong>Patient Snapshot &amp; Check-In Concerns</strong><br/>
      {_esc(brief_data.get('patient_snapshot'))}<br/>
      <span class="muted"><strong>Recent Voice Summary:</strong> {_esc(brief_data.get('chief_concerns_summary'))}</span>
    </div>
    <div class="col">
      <strong>Deterministic Clinical Calculators</strong><br/>
      <strong>CKD-EPI 2021 eGFR:</strong> {_esc(egfr_str)}<br/>
      <strong>ADA Glycemic Band:</strong> {_esc(gly_str)}
    </div>
  </div>

  <h2>Active Medications (DGDA Brand → Generic Reconciliation)</h2>
  <table>
    <thead><tr><th>BD Brand</th><th>Generic Molecule</th><th>Dose</th><th>BD Regimen</th><th>Status / Flag</th></tr></thead>
    <tbody>{med_rows}</tbody>
  </table>

  <h2>Normalized Lab Observations &amp; Trends</h2>
  <table>
    <thead><tr><th>Test (LOINC)</th><th>Normalized Value</th><th>Ref Range</th><th>Flag</th><th>Date</th></tr></thead>
    <tbody>{lab_rows}</tbody>
  </table>
  <div style="font-size:8.6pt;margin-bottom:4px;"><strong>Trend Narrative:</strong> {_esc(brief_data.get('lab_trends_narrative'))}</div>

  <div class="grid">
    <div class="col">
      <strong>Chronological Highlights</strong>
      <ul>{tl_html}</ul>
    </div>
    <div class="col">
      <strong>Clinical Observations &amp; Questions for Doctor</strong>
      <ul>{obs_html}{q_html}</ul>
    </div>
  </div>

  <div class="footer">
    <div>{_esc(brief_data.get('disclaimer'))}</div>
    <div style="white-space:nowrap;margin-left:10px;">QR Exp: 72h</div>
  </div>
</body>
</html>"""

    weasyprint.HTML(string=html).write_pdf(output_pdf)
    return output_pdf
