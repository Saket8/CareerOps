"""Scoring and evidence models."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class JobScore(BaseModel):
    job_id: str
    overall_score: float
    architecture_score: float
    cloud_score: float
    oci_score: float
    ai_score: float
    agentic_ai_score: float
    kubernetes_score: float
    security_score: float
    multicloud_score: float
    experience_alignment: float
    skill_alignment: float
    passed_threshold: bool = False
    match_reasons: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)


class JobEvidence(BaseModel):
    job_id: str
    observed_facts: List[str] = Field(default_factory=list)
    inferred_signals: List[str] = Field(default_factory=list)
    generated_actions: List[str] = Field(default_factory=list)
    skills_found: List[str] = Field(default_factory=list)
    tools_found: List[str] = Field(default_factory=list)
    architecture_patterns: List[str] = Field(default_factory=list)
