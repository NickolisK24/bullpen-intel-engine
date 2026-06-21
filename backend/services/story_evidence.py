"""Editorial evidence validation for backend-authored team stories."""

from __future__ import annotations

import re
from typing import Any

from services.story_observation_voice import (
    INTERNAL_PUBLIC_UNSAFE_TERMS,
    THROAT_CLEARING_CLOSERS,
    validate_observation_voice,
)


CAPABILITY = 'story_evidence_framework_v1'
VERSION = '2026-06-21'

# Headline -> first-body-sentence redundancy guard. The headline sets the frame;
# if body sentence 1 restates it, the card wastes its most valuable line. The
# four-beat body should open on the evidence beat instead. This is report-only:
# it scores the headline/opener pair and flags a near-duplicate, but does not
# gate the story. A token overlap at or above this fraction reads as a
# restatement; openers that lead on the evidence sit well below it.
HEADLINE_OPENER_REDUNDANCY_MAX = 0.6

GENERIC_LANGUAGE_DENYLIST = (
    'the bullpen picture remains stable',
    'bullpen picture remains stable',
    'steadies the picture',
    'shape of the picture',
    'shape of the bullpen remains stable',
    'cleanest part of the picture',
    'what happened on the mound is the cleanest part of the picture',
    'the back end gives the night structure',
    'gives the night structure',
    'the shape is less about one arm and more about the paths still open',
    'tells the story',
    'remains part of the equation',
    'still sits in a workable spot',
    'trusted late-inning options behind the workload',
    'current relief shape is easy to see',
    'relief shape starts there',
    'changed bullpen mix',
    'bullpen mix has been shifting',
    'the bullpen is under pressure',
    'limited flexibility',
)

PUBLIC_SCHEMA_LANGUAGE_DENYLIST = tuple(sorted(set(INTERNAL_PUBLIC_UNSAFE_TERMS + (
    'active capacity',
    'trusted-group breadth',
    'clean options',
    'coverage safety',
    'resource health',
    'bullpen identity',
    'trust hierarchy',
))))

INTERNAL_PROCESS_LANGUAGE_DENYLIST = (
    'source limit',
    'source limits',
    'source limitation',
    'source limitations',
    'model confidence',
    'confidence mechanics',
    'confidence state',
    'validation state',
    'available evidence',
    'available information',
    'current data limitation',
    'data acquisition',
    'data limitation',
    'narrative construction',
    'narrative scope',
    'observation generation',
    'observation scope',
    'signal strength',
    'methodology',
    'internal reasoning',
    'roster context',
    'this read is tied',
    'this read stays',
    'read tied',
    'read stays',
    'stops at usage',
)

POSITIVE_DEPTH_EVIDENCE_MARKERS = (
    'enough trusted relievers',
    'avoid forcing every important inning',
    'without making every important inning depend',
    'does not end there',
    'multiple ways',
    'more than one route',
    'more than one relief lane',
    'not forced back to one narrow group',
)

NEGATIVE_FLEXIBILITY_CONSEQUENCE_MARKERS = (
    'reduced flexibility',
    'reduces flexibility',
    'less coverage margin',
    'less margin',
    'fewer comfortable pivots',
    'less room',
    'gets thinner',
    'thin once',
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


def _story_voice(story: dict[str, Any]) -> dict[str, Any]:
    voice = story.get('story_voice')
    return voice if isinstance(voice, dict) else {}


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


def _content_tokens(value: Any) -> set[str]:
    return {token for token in _normalize_text(value).split() if token}


def headline_opener_overlap(headline: Any, opener: Any) -> float:
    """Normalized lexical overlap (token Jaccard) between two sentences.

    1.0 means identical wording; 0.0 means no shared tokens. Reuses the scorer's
    existing text normalization, so it adds no new dependency. This is the same
    normalized lexical-overlap heuristic used to judge restated copy elsewhere.
    """
    headline_tokens = _content_tokens(headline)
    opener_tokens = _content_tokens(opener)
    if not headline_tokens or not opener_tokens:
        return 0.0
    shared = headline_tokens & opener_tokens
    union = headline_tokens | opener_tokens
    return len(shared) / len(union)


def _first_body_sentence(story: dict[str, Any]) -> str:
    narrative = _clean_text(story.get('narrative')) or _clean_text(story.get('body'))
    sentences = _sentences(narrative)
    return sentences[0] if sentences else ''


def headline_opener_redundancy(story: dict[str, Any]) -> dict[str, Any]:
    """Score whether body sentence 1 restates the headline.

    Report-only regression guard for the headline -> first-body-sentence echo.
    ``redundant`` is the failing signal: a near-duplicate opener fails this
    check, while an opener that leads on the evidence beat passes.
    """
    headline = _clean_text(story.get('title'))
    opener = _first_body_sentence(story)
    overlap = headline_opener_overlap(headline, opener)
    return {
        'headline': headline,
        'opener': opener,
        'overlap': round(overlap, 3),
        'threshold': HEADLINE_OPENER_REDUNDANCY_MAX,
        'redundant': bool(headline and opener and overlap >= HEADLINE_OPENER_REDUNDANCY_MAX),
    }


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


def _selected_observation_text(story: dict[str, Any]) -> str:
    observation = story.get('story_observation') or {}
    if not isinstance(observation, dict):
        observation = {}
    selected = observation.get('selected_observation') or {}
    if not isinstance(selected, dict):
        selected = {}
    return _clean_text(selected.get('text'))


def _references_selected_observation(text: str, story: dict[str, Any]) -> bool:
    selected_text = _selected_observation_text(story)
    if not selected_text:
        return True
    return selected_text in _clean_text(text)


def _generic_language_hits(text: str) -> list[str]:
    lower = _normalize_text(text)
    return [phrase for phrase in GENERIC_LANGUAGE_DENYLIST if phrase in lower]


def _schema_language_hits(text: str) -> list[str]:
    lower = _normalize_text(text)
    return [phrase for phrase in PUBLIC_SCHEMA_LANGUAGE_DENYLIST if phrase in lower]


def _closing_language_hits(text: str) -> list[str]:
    lower = _normalize_text(text)
    return [phrase for phrase in THROAT_CLEARING_CLOSERS if phrase in lower]


def _internal_process_language_hits(text: str) -> list[str]:
    lower = _normalize_text(text)
    return [phrase for phrase in INTERNAL_PROCESS_LANGUAGE_DENYLIST if phrase in lower]


def _consequence_consistent_with_evidence(story: dict[str, Any]) -> bool:
    evidence = _story_evidence(story)
    evidence_text = _normalize_text(evidence.get('evidence_statement'))
    selected_text = _normalize_text(_selected_observation_text(story))
    consequence_text = _normalize_text(evidence.get('consequence_statement'))
    category = _normalize_text(evidence.get('consequence_category'))
    combined_evidence = f'{evidence_text} {selected_text}'
    has_positive_depth = any(marker in combined_evidence for marker in POSITIVE_DEPTH_EVIDENCE_MARKERS)
    if not has_positive_depth:
        return True
    if category == 'reduced_flexibility':
        return False
    return not any(marker in consequence_text for marker in NEGATIVE_FLEXIBILITY_CONSEQUENCE_MARKERS)


def validate_story_evidence(story: dict[str, Any]) -> dict[str, Any]:
    """Validate that a story carries evidence, names, consequence, and clean language."""

    text = story_public_text(story)
    names = _pitcher_names(story)
    generic_hits = _generic_language_hits(text)
    schema_hits = _schema_language_hits(text)
    closing_hits = _closing_language_hits(text)
    process_hits = _internal_process_language_hits(text)
    voice = _story_voice(story)
    voice_validation = validate_observation_voice(voice) if voice else None
    if voice_validation:
        generic_hits = sorted(set(generic_hits + voice_validation.get('generic_frame_hits', [])))
        closing_hits = sorted(set(closing_hits + voice_validation.get('closing_language_hits', [])))
    checks = {
        'evidence_presence': _has_measurable_fact(text),
        'name_presence': _has_pitcher_name(text, names),
        'consequence_presence': _has_consequence(text, story),
        'selected_observation_referenced': _references_selected_observation(text, story),
        'generic_language_absent': not generic_hits,
        'public_schema_language_absent': not schema_hits,
        'internal_process_language_absent': not process_hits,
        'closing_language_informational': not closing_hits,
        'consequence_consistent_with_evidence': _consequence_consistent_with_evidence(story),
        'phrase_diversity': True,
    }
    if voice_validation:
        checks.update({
            f"voice_{reason}": False
            for reason in voice_validation.get('fail_reasons', [])
        })
    fail_reasons = [key for key, passed in checks.items() if not passed]
    evidence = _story_evidence(story)
    # Report-only regression guard: score the headline -> body-sentence-1 pair
    # and flag a near-duplicate. Surfaced for review but intentionally excluded
    # from `checks`/`fail_reasons`/`passed`, so it does not gate or suppress.
    headline_opener = headline_opener_redundancy(story)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'passed': not fail_reasons,
        'checks': checks,
        'fail_reasons': fail_reasons,
        'headline_opener': headline_opener,
        'headline_restates_opener': headline_opener['redundant'],
        'generic_language_hits': generic_hits,
        'schema_language_hits': schema_hits,
        'internal_process_language_hits': process_hits,
        'closing_language_hits': closing_hits,
        'pitcher_names': names,
        'evidence_statement': evidence.get('evidence_statement'),
        'consequence_category': evidence.get('consequence_category'),
        'consequence_statement': evidence.get('consequence_statement'),
        'selected_observation': _selected_observation_text(story),
        'observation_voice': voice_validation,
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
    voice = _story_voice(story)
    voice_frame = _clean_text(voice.get('human_frame'))
    first_sentence = sentences[0] if sentences else ''
    first_is_generic = (
        first_sentence
        and _normalize_text(first_sentence) != evidence_statement
        and _normalize_text(first_sentence) != _normalize_text(voice_frame)
        and not _has_measurable_fact(first_sentence)
        and not _has_pitcher_name(first_sentence, _pitcher_names(story))
    )
    generic_sentences = [
        sentence
        for sentence in sentences
        if _normalize_text(sentence) != evidence_statement
        and not _has_measurable_fact(sentence)
        and not _has_pitcher_name(sentence, _pitcher_names(story))
    ]
    if first_is_generic:
        signatures.append((
            'opening_construction',
            _signature_base(first_sentence, story, normalize_identity=False),
        ))
    consequence = _clean_text(evidence.get('consequence_statement'))
    if consequence:
        signatures.append((
            'consequence_construction',
            _signature_base(consequence, story, normalize_identity=False),
        ))
    lead_detail = story.get('lead_dimension_detail') or {}
    honest_sameness = (
        isinstance(lead_detail, dict)
        and (lead_detail.get('honest_sameness') or lead_detail.get('feed_wide_honest_sameness'))
    )
    if voice_frame and not honest_sameness:
        signatures.append((
            'voice_frame',
            _signature_base(voice_frame, story, normalize_identity=False),
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
    'HEADLINE_OPENER_REDUNDANCY_MAX',
    'INTERNAL_PROCESS_LANGUAGE_DENYLIST',
    'PUBLIC_SCHEMA_LANGUAGE_DENYLIST',
    'apply_story_evidence_framework',
    'headline_opener_overlap',
    'headline_opener_redundancy',
    'story_public_text',
    'validate_story_evidence',
]
