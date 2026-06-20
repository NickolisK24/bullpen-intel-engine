"""Editorial evidence validation for backend-authored team stories."""

from __future__ import annotations

import re
from typing import Any


CAPABILITY = 'story_evidence_framework_v1'
VERSION = '2026-06-19'

GENERIC_LANGUAGE_DENYLIST = (
    'steadies the picture',
    'shape of the picture',
    'cleanest part of the picture',
    'gives the night structure',
    'tells the story',
    'remains part of the equation',
    'still sits in a workable spot',
    'trusted late-inning options behind the workload',
)

CONSEQUENCE_MARKERS = (
    'heavier workload concentration',
    'narrower',
    'reduced flexibility',
    'less coverage margin',
    'less margin',
    'more stable bullpen shape',
    'more than one way',
    'not forced back',
    'fewer comfortable pivots',
)

_MEASURABLE_FACT_RE = re.compile(
    r'(\b\d+(?:\.\d+)?%?\b|\b\d+\s+of\s+\d+\b|\btop\s+\d+\b|\b\d+(?:\.\d+)?\s+season ERA\b)',
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r'[^.!?]+[.!?]')
_NUMBER_RE = re.compile(r'\b\d+(?:\.\d+)?%?\b')
_PUNCT_RE = re.compile(r'[^a-z0-9{} ]+')


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _normalize_text(value: Any) -> str:
    return _clean_text(value).lower()


def _sentences(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    matches = [item.strip() for item in _SENTENCE_RE.findall(text) if item.strip()]
    return matches or [text]


def _story_evidence(story: dict[str, Any]) -> dict[str, Any]:
    evidence = story.get('story_evidence')
    return evidence if isinstance(evidence, dict) else {}


def _pitcher_names(story: dict[str, Any]) -> list[str]:
    evidence = _story_evidence(story)
    names = list(evidence.get('pitcher_names') or [])
    lead_fields = story.get('lead_fields') or {}
    computed = story.get('computed') or {}
    for source in (
        lead_fields.get('high_risk_arm_names'),
        lead_fields.get('clean_trust_names'),
        computed.get('top_workload_names'),
        computed.get('clean_trust_names'),
        computed.get('high_risk_arm_names'),
    ):
        for name in source or []:
            if name and name not in names:
                names.append(name)
    return names


def story_public_text(story: dict[str, Any]) -> str:
    """Return the reader-facing story text used for editorial validation."""

    narrative = _clean_text(story.get('narrative'))
    body = _clean_text(story.get('body'))
    pieces = [
        story.get('title'),
        narrative or body,
        story.get('disclosure_note'),
    ]
    return _clean_text(' '.join(_clean_text(piece) for piece in pieces if _clean_text(piece)))


def _has_measurable_fact(text: str) -> bool:
    return bool(_MEASURABLE_FACT_RE.search(text or ''))


def _has_pitcher_name(text: str, names: list[str]) -> bool:
    lower = _normalize_text(text)
    return any(_normalize_text(name) in lower for name in names if _normalize_text(name))


def _has_consequence(text: str, story: dict[str, Any]) -> bool:
    evidence = _story_evidence(story)
    statement = _normalize_text(evidence.get('consequence_statement'))
    lower = _normalize_text(text)
    if statement and statement in lower:
        return True
    return any(marker in lower for marker in CONSEQUENCE_MARKERS)


def _generic_language_hits(text: str) -> list[str]:
    lower = _normalize_text(text)
    return [phrase for phrase in GENERIC_LANGUAGE_DENYLIST if phrase in lower]


def validate_story_evidence(story: dict[str, Any]) -> dict[str, Any]:
    """Validate that a story carries evidence, names, consequence, and clean language."""

    text = story_public_text(story)
    names = _pitcher_names(story)
    generic_hits = _generic_language_hits(text)
    checks = {
        'evidence_presence': _has_measurable_fact(text),
        'name_presence': _has_pitcher_name(text, names),
        'consequence_presence': _has_consequence(text, story),
        'generic_language_absent': not generic_hits,
        'phrase_diversity': True,
    }
    fail_reasons = [key for key, passed in checks.items() if not passed]
    evidence = _story_evidence(story)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'passed': not fail_reasons,
        'checks': checks,
        'fail_reasons': fail_reasons,
        'generic_language_hits': generic_hits,
        'pitcher_names': names,
        'evidence_statement': evidence.get('evidence_statement'),
        'consequence_category': evidence.get('consequence_category'),
        'consequence_statement': evidence.get('consequence_statement'),
    }


def _signature_base(sentence: str, story: dict[str, Any], *, normalize_identity: bool = True) -> str:
    signature = _normalize_text(sentence)
    if normalize_identity:
        team_name = _normalize_text(story.get('team_name'))
        team_abbreviation = _normalize_text(story.get('team_abbreviation'))
        if team_name:
            signature = signature.replace(team_name, '{team}')
        if team_abbreviation:
            signature = re.sub(rf'\b{re.escape(team_abbreviation)}\b', '{team}', signature)
        for name in _pitcher_names(story):
            normalized = _normalize_text(name)
            if normalized:
                signature = signature.replace(normalized, '{pitcher}')
    signature = _NUMBER_RE.sub('{num}', signature)
    signature = _PUNCT_RE.sub(' ', signature)
    return _clean_text(signature)


def _story_phrase_signatures(story: dict[str, Any]) -> list[tuple[str, str]]:
    narrative = _clean_text(story.get('narrative')) or _clean_text(story.get('body'))
    sentences = _sentences(narrative)
    signatures: list[tuple[str, str]] = []
    evidence = _story_evidence(story)
    evidence_statement = _normalize_text(evidence.get('evidence_statement'))
    generic_sentences = [
        sentence
        for sentence in sentences
        if _normalize_text(sentence) != evidence_statement
        and not _has_measurable_fact(sentence)
        and not _has_pitcher_name(sentence, _pitcher_names(story))
    ]
    if generic_sentences:
        signatures.append((
            'opening_construction',
            _signature_base(generic_sentences[0], story, normalize_identity=False),
        ))
    consequence = _clean_text(evidence.get('consequence_statement'))
    if consequence:
        signatures.append((
            'consequence_construction',
            _signature_base(consequence, story, normalize_identity=False),
        ))
    return [
        (kind, signature)
        for kind, signature in signatures
        if signature and len(signature.split()) >= 5
    ]


def _suppression_record(story: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    return {
        'team_id': story.get('team_id'),
        'team_name': story.get('team_name'),
        'team_abbreviation': story.get('team_abbreviation'),
        'rule_key': story.get('rule_key'),
        'story_id': story.get('story_id'),
        'reasons': reasons,
    }


def apply_story_evidence_framework(
    stories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fail closed for invalid stories and repeated phrase patterns."""

    published: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}

    for story in stories:
        validation = validate_story_evidence(story)
        story['story_evidence_framework'] = validation
        if not validation['passed']:
            suppressed.append(_suppression_record(story, validation['fail_reasons']))
            continue

        duplicate_reasons: list[str] = []
        signatures = _story_phrase_signatures(story)
        for kind, signature in signatures:
            prior = seen.get((kind, signature))
            if prior:
                duplicate_reasons.append(f'duplicate_{kind}')

        if duplicate_reasons:
            validation['checks']['phrase_diversity'] = False
            validation['passed'] = False
            validation['fail_reasons'] = sorted(set(validation['fail_reasons'] + duplicate_reasons))
            suppressed.append(_suppression_record(story, validation['fail_reasons']))
            continue

        for kind, signature in signatures:
            seen[(kind, signature)] = story
        published.append(story)

    return published, suppressed


__all__ = [
    'CAPABILITY',
    'VERSION',
    'CONSEQUENCE_MARKERS',
    'GENERIC_LANGUAGE_DENYLIST',
    'apply_story_evidence_framework',
    'story_public_text',
    'validate_story_evidence',
]
