"""Claim-language linting for Phase 0D evidence templates."""

from __future__ import annotations

from dataclasses import dataclass
import re


class EvidenceLanguageError(AssertionError):
    """Raised when claim text violates the Phase 0D language rulebook."""


@dataclass(frozen=True)
class ForbiddenLanguageRule:
    rule_id: str
    pattern: re.Pattern
    description: str


FORBIDDEN_LANGUAGE_RULES = (
    ForbiddenLanguageRule(
        'forbidden_betting_language',
        re.compile(r'\b(bet|bets|betting|wager|wagers|sportsbook)\b', re.I),
        'betting language is not allowed',
    ),
    ForbiddenLanguageRule(
        'forbidden_odds_language',
        re.compile(r'\bodds?\b', re.I),
        'odds language is not allowed',
    ),
    ForbiddenLanguageRule(
        'forbidden_projection_language',
        re.compile(r'\b(project|projected|projection|projections|forecast|forecasts)\b', re.I),
        'projection language is not allowed',
    ),
    ForbiddenLanguageRule(
        'forbidden_prediction_framing',
        re.compile(r"\b(will|should|expect|expects|expected|likely|predict|prediction)\b", re.I),
        'prediction or availability-certainty framing is not allowed',
    ),
    ForbiddenLanguageRule(
        'forbidden_manager_intent_certainty',
        re.compile(
            r"\b(trusts|prefers|won't use|will not use|manager intent|plans to use)\b",
            re.I,
        ),
        'manager-intent certainty is not allowed',
    ),
    ForbiddenLanguageRule(
        'forbidden_health_language',
        re.compile(
            r'\b(healthy|injury-free|full strength|nobody is hurt|fully healthy)\b',
            re.I,
        ),
        'unsupported health language is not allowed',
    ),
    ForbiddenLanguageRule(
        'forbidden_score_grade_rank_framing',
        re.compile(
            r'\b(score|scores|grade|graded|rank|ranked|ranking|green|yellow|red)\b',
            re.I,
        ),
        'score, grade, rank, or color-state framing is not allowed',
    ),
    ForbiddenLanguageRule(
        'forbidden_official_role_title_claim',
        re.compile(r'\b(closer|setup man|fireman)\b', re.I),
        'official role-title assertions are not allowed in Phase 0D',
    ),
)


# Stands in for an exact proper noun while linting; it matches no rule.
PROPER_NOUN_MASK = 'NAMEDSUBJECT'


def mask_proper_nouns(text: str, proper_nouns=()) -> str:
    """Replace each exact proper noun (a player name the code inserted) with a
    neutral token, longest first, so a name such as "Will Vest" or "Chad Green"
    is not read as authored language. Only exact occurrences are masked; the
    authored text around them is still linted in full."""
    masked = text
    for noun in sorted({str(item) for item in proper_nouns or () if item}, key=len, reverse=True):
        masked = masked.replace(noun, PROPER_NOUN_MASK)
    return masked


def lint_claim_language(text: str, proper_nouns=()) -> list[dict]:
    """Return forbidden-language hits for claim template or rendered text.

    ``proper_nouns`` are exact names the caller inserted into ``text``; they
    are excluded from linting and nothing else is.
    """
    if text is None:
        return [{'rule_id': 'missing_claim_text', 'match': None}]
    text = mask_proper_nouns(text, proper_nouns)
    hits = []
    for rule in FORBIDDEN_LANGUAGE_RULES:
        match = rule.pattern.search(text)
        if match:
            hits.append({
                'rule_id': rule.rule_id,
                'match': match.group(0),
                'description': rule.description,
            })
    return hits


def assert_claim_language_allowed(text: str, proper_nouns=()) -> bool:
    hits = lint_claim_language(text, proper_nouns)
    if hits:
        first = hits[0]
        raise EvidenceLanguageError(
            f"claim language violates {first['rule_id']}: {first['match']!r}"
        )
    return True
