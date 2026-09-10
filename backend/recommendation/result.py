"""Result schema for Recommendation Engine V1 foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from recommendation.contracts import (
    DEFAULT_REFUSAL_MESSAGE,
    BASE_RECOMMENDATION_LIMITATIONS,
    RecommendationConfidenceContext,
    RecommendationExplanation,
    RecommendationFreshnessContext,
    RecommendationLimitation,
    RecommendationRefusal,
)
from recommendation.enums import (
    RecommendationCategory,
    RecommendationOutcome,
    RefusalReason,
)


@dataclass(frozen=True)
class RecommendationResult:
    category: RecommendationCategory | None = None
    pitcher_id: int | None = None
    pitcher_name: str | None = None
    confidence: RecommendationConfidenceContext = field(
        default_factory=RecommendationConfidenceContext
    )
    freshness: RecommendationFreshnessContext = field(
        default_factory=RecommendationFreshnessContext
    )
    explanations: tuple[RecommendationExplanation, ...] = ()
    limitations: tuple[RecommendationLimitation, ...] = BASE_RECOMMENDATION_LIMITATIONS
    alternatives: tuple[Mapping[str, Any], ...] = ()
    refusal: RecommendationRefusal | None = field(default_factory=RecommendationRefusal)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def refuse(
        cls,
        reason: RefusalReason = RefusalReason.INSUFFICIENT_DATA,
        message: str = DEFAULT_REFUSAL_MESSAGE,
        confidence: RecommendationConfidenceContext | None = None,
        freshness: RecommendationFreshnessContext | None = None,
        explanations: tuple[RecommendationExplanation, ...] | None = None,
        limitations: tuple[RecommendationLimitation, ...] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        refusal = RecommendationRefusal(
            reason=reason,
            message=message,
            confidence=confidence or RecommendationConfidenceContext(),
            freshness=freshness or RecommendationFreshnessContext(),
            explanations=tuple(explanations or ()),
            limitations=tuple(limitations or BASE_RECOMMENDATION_LIMITATIONS),
        )
        return cls(
            confidence=refusal.confidence,
            freshness=refusal.freshness,
            explanations=refusal.explanations,
            limitations=refusal.limitations,
            refusal=refusal,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def recommendation(
        cls,
        category: RecommendationCategory,
        pitcher_id: int,
        pitcher_name: str,
        confidence: RecommendationConfidenceContext,
        freshness: RecommendationFreshnessContext,
        explanations: tuple[RecommendationExplanation, ...],
        limitations: tuple[RecommendationLimitation, ...],
        alternatives: tuple[Mapping[str, Any], ...] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ):
        return cls(
            category=category,
            pitcher_id=pitcher_id,
            pitcher_name=pitcher_name,
            confidence=confidence,
            freshness=freshness,
            explanations=tuple(explanations),
            limitations=tuple(limitations),
            alternatives=tuple(alternatives or ()),
            refusal=None,
            metadata=dict(metadata or {}),
        )

    @property
    def is_refusal(self):
        return self.refusal is not None

    @property
    def has_recommendation(self):
        return (
            self.refusal is None
            and self.category is not None
            and self.pitcher_id is not None
            and bool(self.pitcher_name)
        )

    @property
    def outcome(self):
        if self.is_refusal:
            return RecommendationOutcome.REFUSAL
        return RecommendationOutcome.RECOMMENDATION

    @property
    def refusal_reason(self):
        return self.refusal.reason if self.refusal else None

    def to_dict(self):
        return {
            'outcome': self.outcome.value,
            'outcome_code': self.outcome.name,
            'category': self.category.value if self.category else None,
            'category_code': self.category.name if self.category else None,
            'pitcher_id': self.pitcher_id,
            'pitcher_name': self.pitcher_name,
            'confidence': self.confidence.to_dict(),
            'freshness': self.freshness.to_dict(),
            'explanations': [
                explanation.to_dict() for explanation in self.explanations
            ],
            'limitations': [limitation.to_dict() for limitation in self.limitations],
            'alternatives': [dict(alternative) for alternative in self.alternatives],
            'refusal_reason': (
                self.refusal.reason.value if self.refusal else None
            ),
            'refusal_reason_code': (
                self.refusal.reason.name if self.refusal else None
            ),
            'refusal': self.refusal.to_dict() if self.refusal else None,
            'is_refusal': self.is_refusal,
            'has_recommendation': self.has_recommendation,
            'metadata': dict(self.metadata),
        }
