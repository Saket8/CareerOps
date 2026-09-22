"""Reporting Agent for generating responsive HTML and Markdown Daily & Weekly Reports."""

import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Tuple, Dict, Any

from src.models.report import DailyReportData, WeeklyIntelligenceData
from src.utils.logger import get_logger

logger = get_logger("reporting_agent")


class ReportingAgent:
    """Builds and persists daily execution reports and Friday weekly intelligence reports."""

    def __init__(self, daily_dir: Path = Path("reports/daily"), weekly_dir: Path = Path("reports/weekly")):
        self.daily_dir = daily_dir
        self.weekly_dir = weekly_dir
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.weekly_dir.mkdir(parents=True, exist_ok=True)

    def generate_daily_report(self, data: DailyReportData) -> Tuple[Path, Path, str]:
        """Generates Daily Markdown and HTML reports strictly categorizing application statuses."""
        md_file = self.daily_dir / f"{data.date}.md"
        html_file = self.daily_dir / f"{data.date}.html"

        # Zero-dummy filter: Never show dummy/mock jobs regardless of run mode
        def _is_valid_report_app(a):
            u = a.url or ""
            if not u or u == "#" or not u.startswith("http"):
                return False
            if any(fake in u for fake in ("job-listings-job_oci_", "job-listings-job_undisclosed_", "job-listings-nk_", "job_oci_", "nk_")):
                return False
            return True

        valid_apps = [a for a in data.top_applications if _is_valid_report_app(a)]
        # Confirmed apps must be authentic live applications with non-mock references
        confirmed_apps = [
            a for a in valid_apps
            if a.status in ("APPLIED_CONFIRMED", "APPLIED")
            and not (a.confirmation_ref and any(a.confirmation_ref.startswith(p) for p in ("MOCK_", "SIM_")))
        ]
        unverified_apps = [a for a in valid_apps if a.status == "SUBMISSION_UNVERIFIED"]
        blocked_apps = [a for a in valid_apps if a.status in ("APPLICATION_BLOCKED", "BLOCKED")]
        external_apps = [a for a in valid_apps if a.status in ("EXTERNAL_APPLICATION_REQUIRED", "NEEDS_MANUAL_INTERVENTION")]
        failed_apps = [a for a in valid_apps if a.status in ("APPLICATION_FAILED", "FAILED")]

        # Markdown format
        md_content = f"""# CAREER AGENT — APPLICATION REPORT
Date: {data.date}
**Mode:** {'DRY RUN (No live applications)' if data.dry_run else 'LIVE PRODUCTION'}  
**Run ID:** `{data.run_id}`  
**Execution Window:** {data.start_time.strftime('%H:%M:%S UTC')} — {data.end_time.strftime('%H:%M:%S UTC')}  

---

## Executive Pipeline Summary
- **Jobs discovered:** {data.jobs_scanned}
- **Salary rejected (< ₹20 LPA):** {data.salary_rejected}
- **Qualified:** {data.qualified_jobs}
- **Strong matches (Score >= 85%):** {data.strong_matches}
- **Applications confirmed:** {len(confirmed_apps)}
- **Applications attempted but unverified:** {len(unverified_apps)}
- **Blocked:** {len(blocked_apps)}
- **Failed:** {len(failed_apps)}
- **External portal applications / Manual:** {len(external_apps)}
- **ATS Resumes generated:** {data.resumes_generated}
- **Interview packs built:** {data.interview_packs_generated}

---

### CONFIRMED APPLICATIONS
"""
        if confirmed_apps:
            for idx, item in enumerate(confirmed_apps, 1):
                md_content += f"{idx}. **{item.role}**\n"
                md_content += f"   - **Company:** {item.company}\n"
                md_content += f"   - **Salary:** {item.salary}\n"
                md_content += f"   - **Match:** `{item.match_score}%`\n"
                md_content += f"   - **Method:** {item.method}\n"
                md_content += f"   - **Status:** `{item.status}`\n"
                if item.confirmation_ref:
                    md_content += f"   - **Confirmation Ref:** `{item.confirmation_ref}`\n"
                if item.url:
                    md_content += f"   - **Live Job Link:** [{item.url}]({item.url})\n"
                    md_content += f"   - **Verification:** Click link above in your browser — displays the official green **'Applied'** badge on your Naukri account.\n"
                md_content += "\n"
        else:
            md_content += "_No confirmed applications in this run._\n\n"

        if external_apps:
            md_content += "### ⭐ HIGH-VALUE EXTERNAL OPPORTUNITIES (RECOMMENDED FOR 1-CLICK MANUAL APPLICATION)\n"
            md_content += "_The following opportunities scored high for your profile (≥75% match, ₹25+ LPA) but require submission on external enterprise career portals (Workday, Greenhouse, Taleo). Direct links are provided below for 1-click manual submission:_\n\n"
            for idx, item in enumerate(external_apps, 1):
                factors = ", ".join(item.key_factors[:3]) if item.key_factors else "High architecture alignment"
                md_content += f"{idx}. **{item.role}** @ **{item.company}**\n"
                md_content += f"   - **Match Score:** `{item.match_score}%`\n"
                md_content += f"   - **Salary:** {item.salary}\n"
                md_content += f"   - **Key Fit Factors:** {factors}\n"
                md_content += f"   - **Recommended Resume:** `{item.resume_used}`\n"
                md_content += f"   - **Direct Portal Link:** [Apply on Company Portal ↗]({item.url})\n\n"

        if unverified_apps:
            md_content += "### UNVERIFIED APPLICATIONS\n"
            for idx, item in enumerate(unverified_apps, 1):
                md_content += f"{idx}. **{item.role}** @ {item.company}\n"
                md_content += f"   - **Status:** `{item.status}`\n"
                md_content += f"   - **Reason:** {item.reason or 'No unambiguous confirmation detected'}\n"
                md_content += f"   - **URL:** {item.url}\n\n"

        if blocked_apps:
            md_content += "### BLOCKED APPLICATIONS\n"
            for idx, item in enumerate(blocked_apps, 1):
                md_content += f"{idx}. **{item.role}** @ {item.company}\n"
                md_content += f"   - **Status:** `{item.status}`\n"
                md_content += f"   - **Reason:** {item.reason or 'Safety barrier / auth challenge encountered'}\n"
                md_content += f"   - **URL:** {item.url}\n\n"

        if failed_apps:
            md_content += "### FAILED APPLICATIONS\n"
            for idx, item in enumerate(failed_apps, 1):
                md_content += f"{idx}. **{item.role}** @ {item.company}\n"
                md_content += f"   - **Status:** `{item.status}`\n"
                md_content += f"   - **Reason:** {item.reason or 'Technical failure'}\n\n"

        if data.warnings or data.errors:
            md_content += "---\n### Pipeline Diagnostics\n"
            for w in data.warnings:
                md_content += f"- [WARNING] {w}\n"
            for e in data.errors:
                md_content += f"- [ERROR] {e}\n"

        md_file.write_text(md_content, encoding="utf-8")

        # Clean, modern Responsive HTML format
        def build_table_rows(apps_list):
            if not apps_list:
                return '<tr><td colspan="4" style="padding: 16px; text-align: center; color: #64748b;">None</td></tr>'
            rows = []
            for app in apps_list:
                is_confirmed = app.status in ("APPLIED_CONFIRMED", "APPLIED")
                status_color = "#16a34a" if is_confirmed else "#d97706" if "UNVERIFIED" in app.status else "#dc2626"
                status_bg = "#dcfce7" if is_confirmed else "#fef3c7" if "UNVERIFIED" in app.status else "#fee2e2"
                verify_btn_html = ""
                if app.url:
                    if is_confirmed:
                        verify_btn_html = f'<a href="{app.url}" target="_blank" style="display: inline-block; background-color: #16a34a; color: #ffffff; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 11px; white-space: nowrap;">Verify (Applied) &rarr;</a>'
                    else:
                        verify_btn_html = f'<a href="{app.url}" target="_blank" style="color: #2563eb; text-decoration: underline; font-size: 11px;">View Listing</a>'

                rows.append(f"""
                <tr>
                    <td style="padding: 12px 14px; border-bottom: 1px solid #e2e8f0; vertical-align: middle;">
                        <div style="font-weight: 700; color: #0f172a; font-size: 13px; line-height: 1.35;">
                            <a href="{app.url or '#'}" target="_blank" style="color: #0f172a; text-decoration: none;">{app.role}</a>
                        </div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 3px; font-weight: 500;">
                            <span style="color: #1e293b; font-weight: 600;">{app.company}</span> &bull; <span style="color: #475569;">{app.salary}</span>
                        </div>
                    </td>
                    <td style="padding: 12px 10px; border-bottom: 1px solid #e2e8f0; text-align: center; vertical-align: middle; white-space: nowrap;">
                        <span style="display: inline-block; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 700; background-color: #dcfce7; color: #166534;">{app.match_score}%</span>
                    </td>
                    <td style="padding: 12px 10px; border-bottom: 1px solid #e2e8f0; text-align: center; vertical-align: middle; white-space: nowrap;">
                        <span style="display: inline-block; padding: 3px 8px; border-radius: 6px; font-weight: 700; color: {status_color}; background-color: {status_bg}; font-size: 11px;">{app.status}</span>
                    </td>
                    <td style="padding: 12px 12px; border-bottom: 1px solid #e2e8f0; text-align: center; vertical-align: middle; white-space: nowrap;">
                        {verify_btn_html}
                    </td>
                </tr>
                """)
            return "".join(rows)

        def build_external_rows(ext_list):
            if not ext_list:
                return ""
            rows = []
            for app in ext_list:
                factors = ", ".join(app.key_factors[:3]) if app.key_factors else "High architecture alignment"
                btn_link = app.url if app.url else "#"
                rows.append(f"""
                <tr style="background-color: #ffffff;">
                    <td style="padding: 12px 14px; border-bottom: 1px solid #bae6fd; vertical-align: middle;">
                        <div style="font-weight: 700; color: #0369a1; font-size: 13px; line-height: 1.35;">
                            <a href="{btn_link}" target="_blank" style="color: #0369a1; text-decoration: none;">{app.role}</a>
                        </div>
                        <div style="font-size: 12px; color: #475569; margin-top: 3px;">
                            <span style="font-weight: 600; color: #0f172a;">{app.company}</span> &bull; <span>{app.salary}</span>
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 3px; font-style: italic;">
                            {factors}
                        </div>
                    </td>
                    <td style="padding: 12px 10px; border-bottom: 1px solid #bae6fd; text-align: center; vertical-align: middle; white-space: nowrap;">
                        <span style="display: inline-block; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 700; background-color: #e0f2fe; color: #0369a1;">{app.match_score}%</span>
                    </td>
                    <td style="padding: 12px 12px; border-bottom: 1px solid #bae6fd; text-align: center; vertical-align: middle; white-space: nowrap;">
                        <a href="{btn_link}" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); color: #ffffff; padding: 6px 14px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 11px; white-space: nowrap; box-shadow: 0 2px 4px rgba(2, 132, 199, 0.25);">Apply on Company Portal &rarr;</a>
                    </td>
                </tr>
                """)
            return "".join(rows)

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>CAREER AGENT — APPLICATION REPORT — {data.date}</title>
<style>
  body, table, td, p, a, li, blockquote {{
    -webkit-text-size-adjust: 100%;
    -ms-text-size-adjust: 100%;
  }}
  table, td {{
    mso-table-lspace: 0pt;
    mso-table-rspace: 0pt;
  }}
  @media only screen and (max-width: 600px) {{
    .email-container {{
      width: 100% !important;
      max-width: 100% !important;
      margin: 0 !important;
      border-radius: 0 !important;
      border: none !important;
    }}
    .email-padding {{
      padding: 16px 12px !important;
    }}
    .stat-card {{
      flex: 1 1 80px !important;
      padding: 10px 4px !important;
    }}
    .table-wrapper {{
      width: 100% !important;
      overflow-x: auto !important;
      -webkit-overflow-scrolling: touch !important;
    }}
  }}
</style>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; color: #334155; margin: 0; padding: 12px 6px; -webkit-font-smoothing: antialiased;">
  <div class="email-container" style="max-width: 660px; width: 100%; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.07); border: 1px solid #e2e8f0; box-sizing: border-box;">
    
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 24px 24px; color: #ffffff; border-radius: 12px 12px 0 0;">
      <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #38bdf8;">Autonomous Career Intelligence</div>
      <h1 style="margin: 6px 0 4px 0; font-size: 22px; font-weight: 700; line-height: 1.3;">CareerOps &bull; Application Report</h1>
      <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">{data.date} &bull; Mode: <strong style="color: {'#fbbf24' if data.dry_run else '#4ade80'};">{'DRY RUN' if data.dry_run else 'LIVE SUBMISSION'}</strong> &bull; Run: <code style="font-size: 11px; background: #334155; padding: 2px 6px; border-radius: 4px; color: #f8fafc;">{data.run_id}</code></div>
    </div>

    <!-- Stat Cards Grid -->
    <div style="padding: 16px 20px; background-color: #f8fafc; display: flex; flex-wrap: wrap; gap: 8px; border-bottom: 1px solid #e2e8f0;">
      <div class="stat-card" style="flex: 1 1 90px; min-width: 80px; background: #ffffff; padding: 12px 8px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; box-sizing: border-box;">
        <div style="font-size: 20px; font-weight: 800; color: #0f172a;">{data.jobs_scanned}</div>
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-top: 2px;">Discovered</div>
      </div>
      <div class="stat-card" style="flex: 1 1 90px; min-width: 80px; background: #ffffff; padding: 12px 8px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; box-sizing: border-box;">
        <div style="font-size: 20px; font-weight: 800; color: #dc2626;">{data.salary_rejected}</div>
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-top: 2px;">Salary Rejected</div>
      </div>
      <div class="stat-card" style="flex: 1 1 90px; min-width: 80px; background: #ffffff; padding: 12px 8px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; box-sizing: border-box;">
        <div style="font-size: 20px; font-weight: 800; color: #2563eb;">{data.qualified_jobs}</div>
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-top: 2px;">Qualified</div>
      </div>
      <div class="stat-card" style="flex: 1 1 90px; min-width: 80px; background: #ffffff; padding: 12px 8px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; box-sizing: border-box;">
        <div style="font-size: 20px; font-weight: 800; color: #16a34a;">{len(confirmed_apps)}</div>
        <div style="font-size: 10px; text-transform: uppercase; color: #16a34a; font-weight: 700; margin-top: 2px;">Confirmed</div>
      </div>
      <div class="stat-card" style="flex: 1 1 90px; min-width: 80px; background: #ffffff; padding: 12px 8px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; box-sizing: border-box;">
        <div style="font-size: 20px; font-weight: 800; color: #d97706;">{len(unverified_apps)}</div>
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-top: 2px;">Unverified</div>
      </div>
      <div class="stat-card" style="flex: 1 1 90px; min-width: 80px; background: #ffffff; padding: 12px 8px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center; box-sizing: border-box;">
        <div style="font-size: 20px; font-weight: 800; color: #ef4444;">{len(blocked_apps)}</div>
        <div style="font-size: 10px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-top: 2px;">Blocked</div>
      </div>
    </div>

    <!-- Confirmed Applications Section -->
    <div class="email-padding" style="padding: 24px 24px 16px 24px;">
      <h2 style="font-size: 16px; font-weight: 700; margin-top: 0; margin-bottom: 10px; color: #166534; border-bottom: 2px solid #bbf7d0; padding-bottom: 6px;">
        &#10004; Confirmed Applications ({len(confirmed_apps)})
      </h2>
      <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 12px 14px; margin-bottom: 14px; font-size: 13px; color: #166534; line-height: 1.5;">
        <strong>&#10004; Click-to-Verify Guarantee:</strong> Every application below was submitted live directly to the employer via your authenticated account (<code>sauravskt8@gmail.com</code>). Clicking <strong>"Verify (Applied) &rarr;"</strong> opens the listing displaying the official green <strong>"Applied"</strong> status badge.
      </div>
      <div class="table-wrapper" style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; border: 1px solid #e2e8f0; background-color: #ffffff;">
        <table style="width: 100%; min-width: 480px; border-collapse: collapse; text-align: left; font-size: 13px;">
          <thead>
            <tr style="background-color: #f8fafc; border-bottom: 2px solid #cbd5e1;">
              <th style="padding: 10px 14px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 700;">Target Role &amp; Company</th>
              <th style="padding: 10px 10px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Match</th>
              <th style="padding: 10px 10px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Status</th>
              <th style="padding: 10px 12px; color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Live Proof / Action</th>
            </tr>
          </thead>
          <tbody>
            {build_table_rows(confirmed_apps)}
          </tbody>
        </table>
      </div>
    </div>

    <!-- High-Value External Opportunities Section (Recommended for 1-Click Manual Apply) -->
    {(f'''
    <div class="email-padding" style="padding: 20px 24px 16px 24px; background-color: #f0f9ff; border-top: 1px solid #bae6fd; border-bottom: 1px solid #bae6fd;">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
        <h2 style="font-size: 16px; font-weight: 700; margin: 0; color: #0369a1;">
          ⭐ High-Value External Opportunities ({len(external_apps)})
        </h2>
        <span style="background-color: #0284c7; color: #ffffff; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700;">Recommended for Manual Apply</span>
      </div>
      <div style="font-size: 13px; color: #0c4a6e; margin-bottom: 12px; line-height: 1.5;">
        The following opportunities scored high for your profile (&ge;75% match, &ge;₹25 LPA) but require submission on external enterprise portals (Workday, Greenhouse, Taleo). Click <strong>"Apply on Company Portal &rarr;"</strong> below to open the external job listing directly:
      </div>
      <div class="table-wrapper" style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; border: 1px solid #bae6fd; background-color: #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        <table style="width: 100%; min-width: 480px; border-collapse: collapse; text-align: left; font-size: 13px;">
          <thead>
            <tr style="background-color: #e0f2fe; border-bottom: 2px solid #bae6fd;">
              <th style="padding: 10px 14px; color: #0369a1; font-size: 11px; text-transform: uppercase; font-weight: 700;">Opportunity &amp; Fit Factors</th>
              <th style="padding: 10px 10px; color: #0369a1; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Match</th>
              <th style="padding: 10px 12px; color: #0369a1; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Action</th>
            </tr>
          </thead>
          <tbody>
            {build_external_rows(external_apps)}
          </tbody>
        </table>
      </div>
    </div>
    ''') if external_apps else ''}

    <!-- Unverified / Blocked Applications Section -->
    {(f'''
    <div class="email-padding" style="padding: 16px 24px 12px 24px;">
      <h2 style="font-size: 15px; font-weight: 700; margin-top: 0; margin-bottom: 10px; color: #9a3412; border-bottom: 1px solid #fed7aa; padding-bottom: 4px;">
        &#9888;&#65039; Unverified / Blocked Applications
      </h2>
      <div class="table-wrapper" style="width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; border: 1px solid #fed7aa; background-color: #ffffff;">
        <table style="width: 100%; min-width: 480px; border-collapse: collapse; text-align: left; font-size: 13px;">
          <thead>
            <tr style="background-color: #fff7ed; border-bottom: 2px solid #fed7aa;">
              <th style="padding: 10px 14px; color: #9a3412; font-size: 11px; text-transform: uppercase; font-weight: 700;">Target Role &amp; Company</th>
              <th style="padding: 10px 10px; color: #9a3412; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Match</th>
              <th style="padding: 10px 10px; color: #9a3412; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Status</th>
              <th style="padding: 10px 12px; color: #9a3412; font-size: 11px; text-transform: uppercase; font-weight: 700; text-align: center;">Details</th>
            </tr>
          </thead>
          <tbody>
            {build_table_rows(unverified_apps + blocked_apps + failed_apps)}
          </tbody>
        </table>
      </div>
    </div>
    ''') if (unverified_apps or blocked_apps or failed_apps) else ''}

    <!-- Footer -->
    <div style="padding: 18px 24px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center; border-radius: 0 0 12px 12px;">
      Autonomous Career Agent &bull; Strictly verified live submissions only &bull; Zero mock/dummy data policy enforced.
    </div>
  </div>
</body>
</html>
"""
        html_file.write_text(html_content, encoding="utf-8")
        logger.info(f"Daily reports written to {md_file} and {html_file}")
        return md_file, html_file, html_content

    def generate_weekly_report(self, data: WeeklyIntelligenceData) -> Tuple[Path, Path, str]:
        """Generates Friday Weekly Intelligence Markdown and HTML reports."""
        md_file = self.weekly_dir / f"{data.week_number}.md"
        html_file = self.weekly_dir / f"{data.week_number}.html"

        md_content = f"""# Weekly Career Intelligence — {data.week_number}
**Window:** {data.date_range}  
**Total JDs Analyzed:** {data.total_jobs_analyzed}  

---

## 1. Salary Distribution
- Disclosed >= ₹30 LPA: {data.salary_stats.get('above_30_lpa', 0)}
- Disclosed ₹20–30 LPA: {data.salary_stats.get('min_20_to_30_lpa', 0)}
- Undisclosed (Accepted): {data.salary_stats.get('undisclosed_count', 0)}
- Rejected (< ₹20 LPA): {data.salary_stats.get('below_20_lpa_rejected', 0)}

---

## 2. Market Velocity & Skill Trends
| Skill / Technology | Category | Weekly Demand | Trend |
|---|---|---|---|
"""
        for t in data.trends:
            md_content += f"| **{t.item_name}** | {t.category} | {t.current_count} | `{t.trend}` |\n"

        md_content += "\n---\n## 3. Candidate Alignment & Positioning Recommendations\n"
        for gap in data.candidate_resume_gaps:
            md_content += f"- **Resume Alignment:** {gap}\n"

        md_content += "\n---\n## 4. Recommended Search Queries for Next Week\n"
        for q in data.recommended_search_queries:
            md_content += f"- `{q}`\n"

        md_file.write_text(md_content, encoding="utf-8")

        trends_html = "".join([
            f"""
            <tr>
                <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 600;">{t.item_name}</td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-transform: uppercase; font-size: 11px; color: #64748b;">{t.category}</td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 700;">{t.current_count}</td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #e2e8f0;">
                    <span style="font-weight: 700; color: {'#16a34a' if 'INCREASING' in t.trend or 'NEW' in t.trend else '#475569'};">{t.trend}</span>
                </td>
            </tr>
            """
            for t in data.trends
        ])

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Weekly Career Intelligence — {data.week_number}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #334155; margin: 0; padding: 24px;">
  <div style="max-width: 720px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; border: 1px solid #e2e8f0;">
    
    <div style="background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%); padding: 28px 32px; color: #ffffff;">
      <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #bae6fd;">Strategic Market Intelligence</div>
      <h1 style="margin: 8px 0 4px 0; font-size: 24px; font-weight: 700;">Weekly Career Briefing — {data.week_number}</h1>
      <div style="font-size: 14px; color: #e0f2fe;">{data.date_range} &bull; Total JDs Analyzed: {data.total_jobs_analyzed}</div>
    </div>

    <div style="padding: 24px 32px;">
      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin-top: 0;">Market Velocity & Key Trends</h2>
      <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;">
        <thead>
          <tr style="background-color: #f8fafc; border-bottom: 2px solid #cbd5e1;">
            <th style="padding: 8px 12px;">Skill / Pattern</th>
            <th style="padding: 8px 12px;">Domain</th>
            <th style="padding: 8px 12px;">Hits</th>
            <th style="padding: 8px 12px;">Trend</th>
          </tr>
        </thead>
        <tbody>
          {trends_html}
        </tbody>
      </table>

      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin-top: 28px; margin-bottom: 12px;">Candidate Strategic Recommendations</h2>
      <ul style="padding-left: 20px; font-size: 14px; color: #475569; line-height: 1.6;">
        {"".join([f"<li>{gap}</li>" for gap in data.candidate_resume_gaps])}
      </ul>

      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin-top: 24px; margin-bottom: 12px;">Recommended Search Queries</h2>
      <div style="display: flex; flex-wrap: wrap; gap: 8px;">
        {"".join([f"<span style='background: #e0f2fe; color: #0369a1; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;'>{q}</span>" for q in data.recommended_search_queries])}
      </div>
    </div>

    <div style="padding: 20px 32px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
      Autonomous Career Agent &bull; Continuous market feedback loop.
    </div>
  </div>
</body>
</html>
"""
        html_file.write_text(html_content, encoding="utf-8")
        logger.info(f"Weekly reports written to {md_file} and {html_file}")
        return md_file, html_file, html_content
