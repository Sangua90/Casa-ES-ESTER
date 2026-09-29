"""Data models for E.S.T.E.R."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImpactLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionStatus(StrEnum):
    SHADOW = "shadow"
    NEEDS_INPUT = "needs_input"
    SUPPRESSED = "suppressed"


@dataclass(slots=True)
class EntityProfile:
    entity_id: str
    domain: str
    name: str
    state: str | None
    area_id: str | None = None
    device_id: str | None = None
    unit: str | None = None
    device_class: str | None = None
    role: str | None = None
    controllable: bool = False
    sensitive: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Decision:
    decision_id: str
    created_at: datetime
    category: str
    title: str
    proposed_action: str
    reasoning: str
    confidence: float
    risk: RiskLevel
    impact: ImpactLevel
    status: DecisionStatus = DecisionStatus.SHADOW
    area_id: str | None = None
    entity_ids: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    alternatives: list[str] = field(default_factory=list)
    feedback: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["risk"] = self.risk.value
        data["impact"] = self.impact.value
        data["status"] = self.status.value
        return data


@dataclass(slots=True)
class ContextEvent:
    event_id: str
    label: str
    starts_at: datetime
    ends_at: datetime | None = None
    people: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    notes: str | None = None
    source: str = "user"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["starts_at"] = self.starts_at.isoformat()
        data["ends_at"] = self.ends_at.isoformat() if self.ends_at else None
        return data
