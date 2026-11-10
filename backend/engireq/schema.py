"""Canonical record contract (proposal section 4.3).

Slots are null when the source does not state them. A missing value is never filled in.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Operator = Literal["<=", "<", ">=", ">", "="]
Modality = Literal["mandatory", "recommended", "permitted", "informational"]
RequirementType = Literal["functional", "performance", "interface", "safety", "environmental", "other"]
GoldLabel = Literal["requirement", "non_requirement", "uncertain"]
Decision = Literal["accepted", "rejected", "unreviewed"]
Partition = Literal["unassigned", "dev", "test"]


class Constraint(BaseModel):
    parameter: Optional[str] = None
    operator: Optional[Operator] = None
    value: Optional[float] = None
    tolerance: Optional[float] = None
    unit: Optional[str] = None
    condition: Optional[str] = None
    surface_text: str = Field(min_length=1)
    start_char: Optional[int] = None
    end_char: Optional[int] = None


class Evidence(BaseModel):
    page: Optional[int] = None
    section: Optional[str] = None
    block_id: str
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    quoted_text: str = Field(min_length=1)
    rects: list[list[float]] = Field(default_factory=list)


class Requirement(BaseModel):
    requirement_id: str
    document_id: str
    source_sha256: str
    span_id: str
    source_label: Optional[str] = None
    is_requirement: bool = True
    modality: Modality = "mandatory"
    requirement_type: RequirementType = "functional"
    component: Optional[str] = None
    action_or_state: Optional[str] = None
    negated: bool = False
    condition: Optional[str] = None
    exception: Optional[str] = None
    constraints: list[Constraint] = Field(default_factory=list)
    evidence: Evidence
    quality_flags: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    method: str


class Passage(BaseModel):
    span_id: str
    document_id: str
    page: Optional[int] = None
    block_id: str
    section: Optional[str] = None
    start_char: int
    end_char: int
    text: str
    rects: list[list[float]] = Field(default_factory=list)
    detected: bool = False
    modality: Modality = "informational"
    reason: str = ""
    record_ids: list[str] = Field(default_factory=list)


class ConstraintEdit(BaseModel):
    parameter: Optional[str] = None
    operator: Optional[Operator] = None
    value: Optional[float] = None
    tolerance: Optional[float] = None
    unit: Optional[str] = None
    condition: Optional[str] = None
    surface_text: str = Field(min_length=1, max_length=2000)
    start_char: Optional[int] = None
    end_char: Optional[int] = None


class RecordPatch(BaseModel):
    reviewer: str = Field(default="reviewer", max_length=80)
    elapsed_ms: int = Field(default=0, ge=0)
    requirement_type: Optional[RequirementType] = None
    component: Optional[str] = Field(default=None, max_length=500)
    action_or_state: Optional[str] = Field(default=None, max_length=500)
    condition: Optional[str] = Field(default=None, max_length=1000)
    exception: Optional[str] = Field(default=None, max_length=1000)
    negated: Optional[bool] = None
    constraints: Optional[list[ConstraintEdit]] = None


class DecisionBody(BaseModel):
    decision: Decision
    reviewer: str = Field(default="reviewer", max_length=80)
    elapsed_ms: int = Field(default=0, ge=0)
    note: Optional[str] = Field(default=None, max_length=1000)


class LabelBody(BaseModel):
    label: Optional[GoldLabel] = None
    reviewer: str = Field(default="reviewer", max_length=80)


class DocumentPatch(BaseModel):
    partition: Partition


class PlaygroundBody(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
