"""Shadow decision engine for E.S.T.E.R.

This module deliberately produces proposals only. It never calls Home Assistant
services and therefore cannot actuate devices in Shadow Mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .models import Decision, DecisionStatus, ImpactLevel, RiskLevel


@dataclass(slots=True)
class RiskPolicy:
    """Minimum confidence required before future autonomous actuation."""

    low: float = 0.60
    medium: float = 0.80
    high: float = 0.93
    critical: float = 0.99

    def threshold(self, risk: RiskLevel) -> float:
        return {
            RiskLevel.LOW: self.low,
            RiskLevel.MEDIUM: self.medium,
            RiskLevel.HIGH: self.high,
            RiskLevel.CRITICAL: self.critical,
        }[risk]


class EsterDecisionEngine:
    """Central decision engine. v0.1 generates safe shadow proposals only."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.risk_policy = RiskPolicy()

    def build_decision(
        self,
        *,
        category: str,
        title: str,
        proposed_action: str,
        reasoning: str,
        confidence: float,
        risk: RiskLevel,
        impact: ImpactLevel,
        area_id: str | None = None,
        entity_ids: list[str] | None = None,
        evidence: dict | None = None,
        alternatives: list[str] | None = None,
    ) -> Decision:
        """Create a shadow decision and decide if user input would be needed."""
        confidence = max(0.0, min(1.0, confidence))
        threshold = self.risk_policy.threshold(risk)

        status = (
            DecisionStatus.SHADOW
            if confidence >= threshold
            else DecisionStatus.NEEDS_INPUT
        )

        return Decision(
            decision_id=str(uuid4()),
            created_at=dt_util.utcnow(),
            category=category,
            title=title,
            proposed_action=proposed_action,
            reasoning=reasoning,
            confidence=confidence,
            risk=risk,
            impact=impact,
            status=status,
            area_id=area_id,
            entity_ids=entity_ids or [],
            evidence=evidence or {},
            alternatives=alternatives or [],
        )

    def confidence_from_evidence(
        self,
        *,
        evidence_quality: float,
        historical_similarity: float,
        sensor_agreement: float,
        data_freshness: float,
    ) -> float:
        """Compute an explainable confidence score from independent factors."""
        values = [
            max(0.0, min(1.0, evidence_quality)),
            max(0.0, min(1.0, historical_similarity)),
            max(0.0, min(1.0, sensor_agreement)),
            max(0.0, min(1.0, data_freshness)),
        ]
        weights = [0.35, 0.30, 0.20, 0.15]
        return round(sum(v * w for v, w in zip(values, weights, strict=True)), 3)

    async def evaluate_snapshot(self, inventory: dict) -> list[Decision]:
        """Run initial generic checks against the current home snapshot.

        v0.1 intentionally avoids pretending to understand the house before
        learning enough context. It creates onboarding/quality decisions only.
        """
        decisions: list[Decision] = []

        unassigned = inventory.get("unassigned_entities", 0)
        if unassigned:
            decisions.append(
                self.build_decision(
                    category="model",
                    title="Improve room mapping",
                    proposed_action=f"Classify {unassigned} entities that have no Home Assistant area.",
                    reasoning=(
                        "Room context is one of the strongest signals for climate, "
                        "presence and comfort decisions. Missing area assignments "
                        "lower confidence."
                    ),
                    confidence=0.98,
                    risk=RiskLevel.LOW,
                    impact=ImpactLevel.MEDIUM,
                    evidence={"unassigned_entities": unassigned},
                )
            )

        return decisions
