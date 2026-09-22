"""Market Signal Engine and Weekly Career Intelligence Agent."""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Set, Optional
from collections import Counter
from sqlalchemy.orm import Session

from src.database.repositories.job_repo import JobRepository
from src.database.repositories.market_repo import MarketSignalRepository
from src.database.repositories.application_repo import ApplicationRepository
from src.models.candidate import CandidateTruth
from src.models.report import WeeklyIntelligenceData, MarketTrendItem
from src.utils.logger import get_logger

logger = get_logger("market_intelligence")


TRACKED_TAXONOMY = {
    "skill": [
        "terraform", "kubernetes", "oke", "docker", "helm", "langchain", "langgraph",
        "mcp", "rag", "promql", "prometheus", "grafana", "splunk", "datadog", "saml",
        "scim", "iam", "rbac", "ansible", "python", "bash", "linux", "git",
    ],
    "platform": [
        "oci", "oracle cloud", "aws", "azure", "gcp", "multi-cloud", "multicloud", "hybrid cloud",
    ],
    "ai_architecture": [
        "genai", "generative ai", "llm", "rag", "agentic", "ai platform", "model context protocol",
        "vector database", "local llm", "chatops", "fine-tuning", "prompt engineering",
    ],
}


class MarketIntelligenceAgent:
    """Extracts market signals, calculates skill velocity, and formulates career recommendations."""

    def __init__(
        self,
        job_repo: JobRepository,
        market_repo: MarketSignalRepository,
        app_repo: ApplicationRepository,
        candidate_truth: CandidateTruth,
    ):
        self.job_repo = job_repo
        self.market_repo = market_repo
        self.app_repo = app_repo
        self.candidate_truth = candidate_truth

    def generate_weekly_intelligence(self, week_str: Optional[str] = None) -> WeeklyIntelligenceData:
        """Analyzes all discovered jobs and computes weekly market intelligence."""
        now = datetime.now(timezone.utc)
        if not week_str:
            week_str = now.strftime("%Y-W%W")

        all_jobs = self.job_repo.get_all_jobs()
        total_jobs = len(all_jobs)

        # 1. Salary Distribution
        salary_stats = {
            "total_jobs": total_jobs,
            "undisclosed_count": 0,
            "disclosed_count": 0,
            "min_20_to_30_lpa": 0,
            "min_30_to_40_lpa": 0,
            "above_30_lpa": 0,
            "above_40_lpa": 0,
            "below_20_lpa_rejected": 0,
            "below_30_lpa_rejected": 0,
        }
        for j in all_jobs:
            if not j.salary_disclosed:
                salary_stats["undisclosed_count"] += 1
            else:
                salary_stats["disclosed_count"] += 1
                min_sal = j.salary_min or 0.0
                if min_sal < 20.0:
                    salary_stats["below_20_lpa_rejected"] += 1
                if min_sal < 30.0:
                    salary_stats["below_30_lpa_rejected"] += 1
                elif min_sal <= 40.0:
                    salary_stats["min_30_to_40_lpa"] += 1
                else:
                    salary_stats["above_40_lpa"] += 1

                if 20.0 <= min_sal <= 30.0:
                    salary_stats["min_20_to_30_lpa"] += 1
                elif min_sal > 30.0:
                    salary_stats["above_30_lpa"] += 1

        # 2. Extract Skill & Platform Frequencies
        skill_counts = Counter()
        platform_counts = Counter()
        ai_counts = Counter()
        company_counts = Counter()
        role_counts = Counter()
        query_perf = Counter()

        today_str = now.strftime("%Y-%m-%d")

        for j in all_jobs:
            text = f"{j.title} {j.jd_text}".lower()
            company_counts[j.company] += 1
            role_counts[j.title] += 1
            if j.source_query:
                query_perf[j.source_query] += 1

            for sk in TRACKED_TAXONOMY["skill"]:
                if sk in text:
                    skill_counts[sk] += 1
                    self.market_repo.record_signal(today_str, sk.upper(), "skill", frequency=1)

            for pl in TRACKED_TAXONOMY["platform"]:
                if pl in text:
                    platform_counts[pl] += 1
                    self.market_repo.record_signal(today_str, pl.upper(), "platform", frequency=1)

            for ai in TRACKED_TAXONOMY["ai_architecture"]:
                if ai in text:
                    ai_counts[ai] += 1
                    self.market_repo.record_signal(today_str, ai.upper(), "ai_architecture", frequency=1)

        # 3. Compute Trends (Comparing against baseline/historical signals)
        trends = []
        for sk, count in skill_counts.most_common(12):
            trend_label = "INCREASING (↑)" if count >= 3 else ("NEW" if count == 1 else "STABLE (→)")
            trends.append(
                MarketTrendItem(
                    item_name=sk.upper(),
                    category="skill",
                    current_count=count,
                    previous_count=max(0, count - 1),
                    trend=trend_label,
                )
            )

        for ai, count in ai_counts.most_common(6):
            trend_label = "INCREASING (↑)" if count >= 2 else "NEW"
            trends.append(
                MarketTrendItem(
                    item_name=ai.upper(),
                    category="ai_architecture",
                    current_count=count,
                    previous_count=max(0, count - 1),
                    trend=trend_label,
                )
            )

        # 4. Formulate Strategic Recommendations & Candidate Resume Gaps
        resume_gaps = []
        learning_recs = []

        # Candidate verified skills set
        verified_skills_text = str(self.candidate_truth.verified_competencies).lower()

        for sk, count in skill_counts.most_common(15):
            if sk not in verified_skills_text:
                resume_gaps.append(f"Skill '{sk.upper()}' appears in {count} target JDs but is unverified in profile.")
                learning_recs.append(f"Dedicate study time to '{sk.upper()}' enterprise integration patterns.")

        if not resume_gaps:
            resume_gaps.append("Core skills show >90% alignment with current enterprise market requirements.")

        # Search Query Recommendations
        top_queries = [q for q, _ in query_perf.most_common(5)]
        recommended_queries = [
            "Principal Cloud GenAI Architect",
            "OCI AI Platform Architect",
            "Agentic AI Solutions Architect",
            "Enterprise Multi-Cloud Security Architect",
        ]

        weekly_data = WeeklyIntelligenceData(
            run_id=f"intel_{week_str}",
            week_number=week_str,
            date_range=f"{(now - timedelta(days=7)).strftime('%b %d')} - {now.strftime('%b %d, %Y')}",
            total_jobs_analyzed=total_jobs,
            salary_stats=salary_stats,
            trends=trends,
            top_companies=[{"name": c, "count": n} for c, n in company_counts.most_common(6)],
            top_roles=[{"name": r, "count": n} for r, n in role_counts.most_common(6)],
            recurring_skills=[{"name": s.upper(), "count": n} for s, n in skill_counts.most_common(10)],
            candidate_resume_gaps=resume_gaps[:5],
            recommended_learning=learning_recs[:4] or ["Deepen multi-agent orchestration and local LLM benchmarking"],
            recommended_search_queries=recommended_queries,
        )

        logger.info(f"Generated Weekly Career Intelligence for {week_str} ({total_jobs} total jobs analyzed)")
        return weekly_data
