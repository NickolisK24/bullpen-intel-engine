"""Data contracts for Recommendation Engine V1 foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from recommendation.enums import (
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationFreshnessState,
    RefusalReason,
)


DEFAULT_REFUSAL_MESSAGE = (
    'BaseballOS cannot make a current recommendation because trusted current '
    'workload data is insufficient.'
)


@dataclass(frozen=True)
class RecommendationExplanation:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            'code': self.code,
            'message': self.message,
            'details': dict(self.details),
        }


@dataclass(frozen=True)
class RecommendationLimitation:
    code: str
    message: str

    def to_dict(self):
        return {
            'code': self.code,
            'message': self.message,
        }


BASE_RECOMMENDATION_LIMITATIONS = (
    RecommendationLimitation(
        code='public_workload_data_only',
        message='Based on public workload data tracked by BaseballOS.',
    ),
    RecommendationLimitation(
        code='not_injury_or_medical',
        message='Not a medical or injury conclusion.',
    ),
    RecommendationLimitation(
        code='not_performance_forecast',
        message='Not a performance forecast.',
    ),
    RecommendationLimitation(
        code='not_team_reported_status',
        message='Not a team-reported availability status.',
    ),
    RecommendationLimitation(
        code='no_private_context',
        message=(
            'Does not know bullpen warm-ups, travel, illness, clubhouse '
            'context, or manager intent.'
        ),
    ),
    RecommendationLimitation(
        code='user_decides',
        message='The user remains responsible for the final decision.',
    ),
)


@dataclass(frozen=True)
class RecommendationConfidenceContext:
    level: RecommendationConfidence = RecommendationConfidence.UNKNOWN
    reasons: tuple[str, ...] = ()

    def to_dict(self):
        return {
            'level': self.level.value,
            'level_code': self.level.name,
            'reasons': list(self.reasons),
        }


@dataclass(frozen=True)
class RecommendationFreshnessContext:
    state: RecommendationFreshnessState = RecommendationFreshnessState.UNKNOWN
    data_through: str | None = None
    last_successful_sync: str | None = None
    latest_sync_status: str | None = None
    limitations: tuple[str, ...] = ()

    def to_dict(self):
        return {
            'state': self.state.value,
            'state_code': self.state.name,
            'data_through': self.data_through,
            'last_successful_sync': self.last_successful_sync,
            'latest_sync_status': self.latest_sync_status,
            'limitations': list(self.limitations),
        }


@dataclass(frozen=True)
class RecommendationCandidate:
    pitcher_id: int | None = None
    pitcher_name: str | None = None
    team_id: int | None = None
    team_name: str | None = None
    availability: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            'pitcher_id': self.pitcher_id,
            'pitcher_name': self.pitcher_name,
            'team_id': self.team_id,
            'team_name': self.team_name,
            'availability': dict(self.availability),
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True)
class RecommendationRequest:
    category: RecommendationCategory | None = None
    team_id: int | None = None
    team_name: str | None = None
    candidates: tuple[RecommendationCandidate, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            'category': self.category.value if self.category else None,
            'category_code': self.category.name if self.category else None,
            'team_id': self.team_id,
            'team_name': self.team_name,
            'candidates': [candidate.to_dict() for candidate in self.candidates],
            'metadata': dict(self.metadata),
        }


@dataclass(frozen=True)
class RecommendationRefusal:
    reason: RefusalReason = RefusalReason.INSUFFICIENT_DATA
    message: str = DEFAULT_REFUSAL_MESSAGE
    confidence: RecommendationConfidenceContext = field(
        default_factory=RecommendationConfidenceContext
    )
    freshness: RecommendationFreshnessContext = field(
        default_factory=RecommendationFreshnessContext
    )
    explanations: tuple[RecommendationExplanation, ...] = ()
    limitations: tuple[RecommendationLimitation, ...] = BASE_RECOMMENDATION_LIMITATIONS

    def to_dict(self):
        return {
            'reason': self.reason.value,
            'reason_code': self.reason.name,
            'message': self.message,
            'confidence': self.confidence.to_dict(),
            'freshness': self.freshness.to_dict(),
            'explanations': [
                explanation.to_dict() for explanation in self.explanations
            ],
            'limitations': [limitation.to_dict() for limitation in self.limitations],
        }
