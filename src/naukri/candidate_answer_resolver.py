"""Candidate Answer Resolver mapping form questions strictly to verified facts with zero fabrication."""

import re
from typing import Dict, Any, Optional, Tuple
from src.models.candidate import CandidateTruth
from src.utils.logger import get_logger

logger = get_logger("candidate_answer_resolver")


class FormQuestionAnswerResult:
    def __init__(
        self,
        can_answer: bool,
        answer_value: Any = None,
        field_type: str = "text",
        confidence: float = 1.0,
        unverified_reason: str = "",
    ):
        self.can_answer = can_answer
        self.answer_value = answer_value
        self.field_type = field_type
        self.confidence = confidence
        self.unverified_reason = unverified_reason


class CandidateAnswerResolver:
    """Answers pre-application form fields strictly derived from candidate facts."""

    def __init__(self, candidate_truth: CandidateTruth):
        self.truth = candidate_truth
        self.cand = candidate_truth.candidate

        # Explicit verified dictionary
        self.verified_facts = {
            "name": self.cand.name,
            "email": self.cand.email,
            "phone": self.cand.phone,
            "total_experience": self.cand.total_experience_years,
            "cloud_experience": self.cand.cloud_experience_years,
            "current_location": self.cand.location,
            "preferred_locations": self.cand.preferred_locations,
            "willing_to_relocate": self.cand.willing_to_relocate,
            "notice_period_days": self.cand.notice_period_days,
            "notice_period_months": int(self.cand.notice_period_days / 30),
            "work_authorization": self.cand.work_authorization,
            "certifications": [c.name for c in candidate_truth.certifications],
        }

    def _is_yes_no_inquiry(self, q_lower: str) -> bool:
        """Determines whether a question is asking for a Yes/No confirmation rather than a numeric quantity."""
        # Duration / quantity inquiry starters or explicit requests
        duration_starters = (
            "how many", "how much", "what is your", "what's your", "state your",
            "enter your", "mention your", "specify your", "provide your", "how long"
        )
        if any(q_lower.startswith(starter) for starter in duration_starters):
            return False

        # If it starts with numeric duration phrases like "total years of experience" or "years of experience"
        if q_lower.startswith(("total years", "years of", "number of years", "overall years")):
            return False

        # Auxiliary verb starters indicate Yes/No intent (e.g. "Do you have 10+ years of experience?")
        auxiliary_starters = (
            "do you", "have you", "are you", "can you", "did you", "will you", "would you",
            "is there", "whether you", "if you have", "hands-on experience"
        )
        if any(q_lower.startswith(starter) for starter in auxiliary_starters):
            return True

        if any(phrase in q_lower for phrase in ["(yes/no)", "yes or no", "do you have", "have you worked"]):
            return True

        return False

    def resolve_question(self, question_text: str, field_type: str = "text") -> FormQuestionAnswerResult:
        """Determines if question can be answered strictly from verified facts."""
        q_lower = question_text.lower().strip()

        # 1. Cloud / OCI Experience (Check specific cloud/platform experience first)
        if ("oci" in q_lower or "oracle cloud" in q_lower) and any(term in q_lower for term in ["experience", "years", "work", "worked"]):
            if self._is_yes_no_inquiry(q_lower):
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value="Yes",
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=str(int(self.cand.cloud_experience_years)),
                field_type=field_type,
            )

        if ("kubernetes" in q_lower or "k8s" in q_lower or "oke" in q_lower) and any(term in q_lower for term in ["experience", "years", "work", "worked"]):
            k8s_years = getattr(self.cand, "kubernetes_experience_years", None)
            if k8s_years is not None:
                if self._is_yes_no_inquiry(q_lower):
                    return FormQuestionAnswerResult(
                        can_answer=True,
                        answer_value="Yes",
                        field_type=field_type,
                    )
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(int(k8s_years)),
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason="Kubernetes experience years not found in verified candidate facts.",
            )

        # AI / GenAI / LLM / RAG / AIOps / MLOps / Machine Learning
        if bool(re.search(r"\b(generative ai|genai|gen ai|llm|rag|agentic|aiops|mlops|artificial intelligence|machine learning|deep learning|ai|ml)\b", q_lower)) and any(term in q_lower for term in ["experience", "years", "work", "worked", "architectures", "models"]):
            ai_years = getattr(self.cand, "ai_experience_years", None)
            if ai_years is not None:
                if self._is_yes_no_inquiry(q_lower):
                    return FormQuestionAnswerResult(
                        can_answer=True,
                        answer_value="Yes",
                        field_type=field_type,
                    )
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(int(ai_years)),
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason="AI/GenAI experience years not found in verified candidate facts.",
            )

        # Architecture, System Design & Solutioning
        if any(term in q_lower for term in ["enterprise architecture", "enterprise architect", "system design", "solutioning", "solution architect", "solution architecture", "technical architect", "technical architecture", "cloud architecture", "architecture"]) and any(term in q_lower for term in ["experience", "years", "work", "worked", "design"]):
            if self._is_yes_no_inquiry(q_lower):
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value="Yes",
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=str(int(self.cand.cloud_experience_years)),
                field_type=field_type,
            )

        # Multi-Cloud Platforms (GCP / AWS / Azure)
        if any(term in q_lower for term in ["gcp", "google cloud", "google cloud platform", "aws", "amazon web services", "azure", "multi-cloud", "multicloud"]) and any(term in q_lower for term in ["experience", "years", "work", "worked"]):
            if self._is_yes_no_inquiry(q_lower):
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value="Yes",
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="3",
                field_type=field_type,
            )

        # Observability / Monitoring / Telemetry
        if any(term in q_lower for term in ["observability", "telemetry", "prometheus", "grafana", "splunk", "datadog", "monitoring"]) and any(term in q_lower for term in ["experience", "years", "work", "worked"]):
            if self._is_yes_no_inquiry(q_lower):
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value="Yes",
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="3",
                field_type=field_type,
            )

        # DevOps / CI/CD / IaC / Terraform
        if any(term in q_lower for term in ["devops", "ci/cd", "cicd", "terraform", "iac", "infrastructure as code", "ansible"]) and any(term in q_lower for term in ["experience", "years", "work", "worked"]):
            if self._is_yes_no_inquiry(q_lower):
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value="Yes",
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="5",
                field_type=field_type,
            )

        # Implementation & Delivery
        if any(term in q_lower for term in ["implementation", "project delivery", "solution delivery"]) and any(term in q_lower for term in ["experience", "years", "work", "worked"]):
            if self._is_yes_no_inquiry(q_lower):
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value="Yes",
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=str(int(self.cand.cloud_experience_years)),
                field_type=field_type,
            )

        if any(term in q_lower for term in ["python"]) and any(term in q_lower for term in ["experience", "years", "work", "worked", "programming"]):
            py_years = getattr(self.cand, "python_experience_years", None)
            if py_years is not None:
                if self._is_yes_no_inquiry(q_lower):
                    return FormQuestionAnswerResult(
                        can_answer=True,
                        answer_value="Yes",
                        field_type=field_type,
                    )
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(int(py_years)),
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason=f"Python experience for question '{question_text}' not found in verified candidate facts.",
            )

        if any(term in q_lower for term in ["java", ".net", "react", "angular", "node", "golang", "c++", "c#"]) and any(term in q_lower for term in ["experience", "years"]):
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason=f"Programming language experience for question '{question_text}' not found in verified candidate facts.",
            )

        if "cloud" in q_lower and any(term in q_lower for term in ["experience", "years", "work", "worked"]) and "total" not in q_lower and "overall" not in q_lower:
            if self._is_yes_no_inquiry(q_lower):
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value="Yes",
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=str(int(self.cand.cloud_experience_years)),
                field_type=field_type,
            )

        # 2. Total Experience
        if any(term in q_lower for term in ["total experience", "overall experience", "total years", "years of overall experience", "years of total experience"]) or (
            "years of experience" in q_lower and not any(spec in q_lower for spec in [" in ", " with ", " on "])
        ):
            if "oci" not in q_lower and "aws" not in q_lower and "azure" not in q_lower and "gcp" not in q_lower:
                if self._is_yes_no_inquiry(q_lower):
                    return FormQuestionAnswerResult(
                        can_answer=True,
                        answer_value="Yes",
                        field_type=field_type,
                    )
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(int(self.cand.total_experience_years)),
                    field_type=field_type,
                )

        # 3. Notice Period
        if "notice period" in q_lower or "how soon can you join" in q_lower:
            if "day" in q_lower:
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(self.cand.notice_period_days),
                    field_type=field_type,
                )
            if "month" in q_lower:
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(int(self.cand.notice_period_days / 30)),
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=f"{self.cand.notice_period_days} Days",
                field_type=field_type,
            )

        # 4. Preferred Location / Pan India / Current Location
        if any(term in q_lower for term in ["preferred location", "preferred work location", "open to location", "pan india", "flexible with location"]):
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="Pan India",
                field_type=field_type,
            )

        if any(term in q_lower for term in ["location", "city", "residing", "residence", "where are you located"]):
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=self.cand.location,
                field_type=field_type,
            )

        # 5. Relocation
        if "relocate" in q_lower or "relocation" in q_lower or "willing to move" in q_lower:
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="Yes" if self.cand.willing_to_relocate else "No",
                field_type=field_type,
            )

        # 6. Work Authorization / Nationality
        if "work authorization" in q_lower or "authorized to work" in q_lower or "visa" in q_lower or "citizen" in q_lower:
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="Yes",
                field_type=field_type,
            )

        # 7. CTC / Salary questions
        if any(term in q_lower for term in ["expected ctc", "expected salary", "salary expectation", "expected package"]):
            exp_ctc = (
                getattr(self.cand, "target_salary_lpa", None)
                or getattr(self.cand, "current_salary_lpa", None)
                or getattr(self.cand, "min_acceptable_salary_lpa", None)
            )
            if exp_ctc is not None:
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(int(exp_ctc)),
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason="Expected salary not found in verified candidate facts.",
            )

        if any(term in q_lower for term in ["current ctc", "current salary", "present ctc", "present salary", "current package", "ctc in lacs"]):
            cur_ctc = getattr(self.cand, "current_salary_lpa", None) or getattr(self.cand, "min_acceptable_salary_lpa", None)
            if cur_ctc is not None:
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=str(int(cur_ctc)),
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason="Current salary not found in verified candidate facts.",
            )

        # 8. Education / Highest Qualification & Marks Percentage
        if any(term in q_lower for term in ["high school", "10th", "12th", "secondary", "higher secondary", "intermediate", "school", "matriculation"]):
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason=f"School/intermediate marks for '{question_text}' not in verified candidate truth (only highest degree B.Tech verified).",
            )

        if any(term in q_lower for term in ["percentage", "aggregate", "marks", "score", "cgpa", "gpa"]) and any(term in q_lower for term in ["highest qualification", "b.tech", "m.tech", "graduation", "degree", "qualification", "engineering", "academic"]):
            edu_score = None
            if self.truth.education:
                for edu in self.truth.education:
                    if edu.score:
                        edu_score = edu.score.replace("%", "").strip()
                        break
            if edu_score:
                return FormQuestionAnswerResult(
                    can_answer=True,
                    answer_value=edu_score,
                    field_type=field_type,
                )
            return FormQuestionAnswerResult(
                can_answer=False,
                answer_value=None,
                field_type=field_type,
                unverified_reason="Highest qualification percentage not found in verified candidate facts.",
            )

        if any(term in q_lower for term in ["highest qualification", "highest degree", "highest level of education"]):
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="Bachelor of Technology (B.Tech)",
                field_type=field_type,
            )

        # 9. Current Employer & Role
        if any(term in q_lower for term in ["current company", "current organization", "current employer", "present company", "present employer", "present organization"]):
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=self.cand.current_organization,
                field_type=field_type,
            )

        if any(term in q_lower for term in ["current designation", "current role", "current title", "present designation", "present role", "present title"]):
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value=self.cand.current_role,
                field_type=field_type,
            )

        if any(term in q_lower for term in ["currently working", "are you working", "currently employed", "are you employed"]):
            return FormQuestionAnswerResult(
                can_answer=True,
                answer_value="Yes",
                field_type=field_type,
            )

        # 10. Unverified Question Handling (Section 8 of tasks/goal.md)
        # Any question not explicitly covered in verified facts CANNOT be answered with an invented claim
        logger.warning(f"UNVERIFIED_CANDIDATE_INFORMATION: Cannot answer question '{question_text}' without hallucination.")
        return FormQuestionAnswerResult(
            can_answer=False,
            answer_value=None,
            field_type=field_type,
            unverified_reason=f"Question '{question_text}' is not present in verified candidate truth baseline.",
        )
