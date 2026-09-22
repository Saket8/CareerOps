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
        """Generates Daily Markdown and HTML reports."""
        md_file = self.daily_dir / f"{data.date}.md"
        html_file = self.daily_dir / f"{data.date}.html"

        # Markdown format
        md_content = f"""# Autonomous Career Agent — Daily Report ({data.date})
**Mode:** {'DRY RUN (No real applications)' if data.dry_run else 'LIVE PRODUCTION'}  
**Run ID:** `{data.run_id}`  
**Execution Window:** {data.start_time.strftime('%H:%M:%S UTC')} — {data.end_time.strftime('%H:%M:%S UTC')}  

---

## Executive Pipeline Summary
- **Jobs Scanned:** {data.jobs_scanned}
- **Salary Filtered (Rejected < ₹20 LPA):** {data.salary_rejected}
- **Qualified Opportunities:** {data.qualified_jobs}
- **Strong Matches (Score >= 85%):** {data.strong_matches}
- **ATS Resumes Generated:** {data.resumes_generated}
- **Applications Submitted:** {data.applications_submitted}
- **Safety Barriers / Blocked:** {data.blocked_applications}
- **Interview Packs Built:** {data.interview_packs_generated}

---

## Top Applications
| Company | Role | Match | Salary | Resume Version | Status |
|---|---|---|---|---|---|
"""
        for item in data.top_applications:
            md_content += f"| **{item.company}** | [{item.role}]({item.url}) | `{item.match_score}%` | {item.salary} | `{item.resume_used}` | **{item.status}** |\n"

        if data.warnings or data.errors:
            md_content += "\n---\n## Pipeline Notices\n"
            for w in data.warnings:
                md_content += f"- [WARNING] {w}\n"
            for e in data.errors:
                md_content += f"- [ERROR] {e}\n"

        md_file.write_text(md_content, encoding="utf-8")

        # Clean, modern Responsive HTML format
        top_apps_html = "".join([
            f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #1e293b;">{app.company}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0;"><a href="{app.url}" style="color: #2563eb; text-decoration: none; font-weight: 500;">{app.role}</a></td>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                    <span style="display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 700; background-color: #dcfce7; color: #166534;">{app.match_score}%</span>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; font-size: 13px; color: #475569;">{app.salary}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0;">
                    <span style="font-weight: 600; color: {'#16a34a' if app.status == 'APPLIED' else '#d97706'};">{app.status}</span>
                </td>
            </tr>
            """
            for app in data.top_applications
        ])

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Career Agent Daily Report — {data.date}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #334155; margin: 0; padding: 24px;">
  <div style="max-width: 720px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); overflow: hidden; border: 1px solid #e2e8f0;">
    
    <!-- Header -->
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 28px 32px; color: #ffffff;">
      <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: #38bdf8;">Autonomous Career Intelligence</div>
      <h1 style="margin: 8px 0 4px 0; font-size: 24px; font-weight: 700;">Daily Execution Report</h1>
      <div style="font-size: 14px; color: #94a3b8;">{data.date} &bull; Mode: <strong style="color: {'#fbbf24' if data.dry_run else '#4ade80'};">{'DRY RUN' if data.dry_run else 'LIVE SUBMISSION'}</strong></div>
    </div>

    <!-- Stat Cards Grid -->
    <div style="padding: 24px 32px; background-color: #f1f5f9; display: flex; flex-wrap: wrap; gap: 12px;">
      <div style="flex: 1 1 120px; background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;">
        <div style="font-size: 24px; font-weight: 800; color: #0f172a;">{data.jobs_scanned}</div>
        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Scanned</div>
      </div>
      <div style="flex: 1 1 120px; background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;">
        <div style="font-size: 24px; font-weight: 800; color: #dc2626;">{data.salary_rejected}</div>
        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">&lt; ₹20L Rejects</div>
      </div>
      <div style="flex: 1 1 120px; background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;">
        <div style="font-size: 24px; font-weight: 800; color: #2563eb;">{data.qualified_jobs}</div>
        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Qualified</div>
      </div>
      <div style="flex: 1 1 120px; background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0; text-align: center;">
        <div style="font-size: 24px; font-weight: 800; color: #16a34a;">{data.applications_submitted}</div>
        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600;">Applied</div>
      </div>
    </div>

    <!-- Top Applications Table -->
    <div style="padding: 28px 32px;">
      <h2 style="font-size: 18px; font-weight: 700; margin-top: 0; margin-bottom: 16px; color: #0f172a;">Top Applications Overview</h2>
      <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px;">
        <thead>
          <tr style="background-color: #f8fafc; border-bottom: 2px solid #cbd5e1;">
            <th style="padding: 10px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Company</th>
            <th style="padding: 10px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Role</th>
            <th style="padding: 10px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Match</th>
            <th style="padding: 10px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Salary</th>
            <th style="padding: 10px 12px; color: #475569; font-size: 11px; text-transform: uppercase;">Status</th>
          </tr>
        </thead>
        <tbody>
          {top_apps_html or '<tr><td colspan="5" style="padding: 16px; text-align: center; color: #64748b;">No new applications submitted today.</td></tr>'}
        </tbody>
      </table>
    </div>

    <!-- Footer -->
    <div style="padding: 20px 32px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center;">
      Generated autonomously by Naukri Career Agent &bull; Strictly verified against candidate ground truth.
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
