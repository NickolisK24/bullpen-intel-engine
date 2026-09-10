"""Deterministic Editorial Review (V2) — Storytelling Manifesto enforcement.

A report-only editorial validation layer. It inspects a generated story object and
checks the editorial principles that can be evaluated OBJECTIVELY. It is not an
LLM, not a subjective scorer, and not a rewriter: it never invents text, never
edits text, never suppresses a story, and never changes publication behavior.

It complements the existing Story Quality gate (technical correctness) with
Editorial Quality (manifesto adherence). The report is INTERNAL only.

Blueprint-aware, backward-compatible: when a story carries the 5-section Story
Blueprint, the structural checks validate those sections; when it does not (a
pre-blueprint story), structural checks that cannot be evaluated are marked
not-applicable rather than warned, so current stories never draw false warnings.
Content checks (prediction / certainty / recap / blame / drama / internal terms)
apply to every story.
"""

from __future__ import annotations

from typing import Any

# Reuse the engine's existing guardrail vocabularies so editorial review stays in
# lockstep with the writer/audit guardrails it is layered on top of.
from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS  # noqa: F401
from services.story_four_beat_interpreter_v1 import PUBLIC_BANNED_TERMS
from services.story_voice_library_v1 import BANNED_PUBLIC_LANGUAGE
from services.story_audit_preview_v1 import INTERNAL_TERMS


CAPABILITY = 'editorial_review_v1'
VERSION = '2026-06-25.v1'

# Report + check statuses. Report-only: status never suppresses a story.
STATUS_PASS = 'pass'
STATUS_WARN = 'warn'
STATUS_NEUTRAL = 'neutral'      # no available story to review
CHECK_PASS = 'pass'
CHECK_WARN = 'warn'
CHECK_NA = 'na'                 # not applicable to this story's structure

# Blueprint section keys (Story Blueprint, Phase A).
SAW = 'what_everyone_saw'
NOTICED = 'what_baseballos_noticed'
EVIDENCE = 'evidence'
WHY = 'why_it_matters'
TOMORROW = 'why_it_matters_tomorrow'
EXPECTED_BLUEPRINT_KEYS = (SAW, NOTICED, EVIDENCE, WHY, TOMORROW)

# ── Editorial term lists (new) ────────────────────────────────────────────────
# Deterministic, substring-matched, authored to be low-false-positive (e.g. bare
# "always"/"never"/"will" are intentionally excluded; only clearly-editorial
# phrases are listed).

PREDICTION_PHRASES = tuple(dict.fromkeys((
    *(t.lower() for t in PUBLIC_BANNED_TERMS),
    *(t.lower() for t in BANNED_PUBLIC_LANGUAGE),
    'on pace to', 'due for', 'bound to', 'destined to', 'projected to',
    'will likely', 'likely to win', 'should win', 'figures to', 'expect them to',
)))

CERTAINTY_PHRASES = (
    'guaranteed', 'certainly', 'definitely', 'undeniable', 'undeniably',
    'without a doubt', 'no doubt', 'inevitable', 'inevitably', 'proves that',
    'proven', 'proof that', 'unquestionably', 'will always', 'always will',
    'never fails', 'every single time',
)

RECAP_PHRASES = (
    'box score', 'final score', 'walk-off', 'walkoff', 'home run', 'grand slam',
    ' rbi ', 'rbi single', 'rbi double', 'bases loaded', 'sacrifice fly',
    'go-ahead run', 'tying run', 'base hit', 'batted in',
)

BLAME_PHRASES = (
    'collapse', 'collapsed', 'meltdown', 'melted down', 'imploded', 'choked',
    'choke', 'blew the', 'blown save', 'to blame', 'at fault', 'culprit',
    'the goat', 'cost them', 'gave it away', 'fell apart', 'disaster', 'fiasco',
)

DRAMA_PHRASES = (
    'stunning', 'shocking', 'epic ', 'dramatic', 'devastating', 'unbelievable',
    'jaw-dropping', 'masterclass', 'dominant', 'dominance', 'heroics', 'clutch',
    'lights out', 'nightmare', 'cinderella', 'roller coaster', 'rollercoaster',
    'thrilling', 'electrifying', 'shockwaves', 'for the ages', 'instant classic',
)

# Explicit second-topic connectors signalling more than one primary idea.
MULTI_IDEA_PHRASES = (
    'on the other hand', 'meanwhile,', 'two separate', 'unrelated',
    'in a separate', 'on a separate note', 'that aside', 'changing topics',
)

INTERNAL_PHRASES = tuple(t.lower() for t in INTERNAL_TERMS)

# Short content-word stoplist for the lesson-vs-evidence overlap heuristic.
_STOP = {
    'that', 'this', 'with', 'from', 'into', 'than', 'then', 'they', 'them',
    'their', 'there', 'here', 'what', 'when', 'which', 'while', 'where', 'have',
    'has', 'had', 'been', 'being', 'about', 'over', 'under', 'more', 'most',
    'less', 'some', 'same', 'such', 'only', 'just', 'still', 'keep', 'keeps',
    'the', 'and', 'but', 'for', 'not', 'are', 'was', 'were', 'its', 'his',
    'her', 'him', 'who', 'how', 'why',
}
_OVERLAP_WARN_THRESHOLD = 0.6


def _clean(value: Any) -> str:
    return ' '.join(str(value).split()) if isinstance(value, str) else ''


def _first_match(text: str, phrases) -> str | None:
    lowered = (text or '').lower()
    for phrase in phrases:
        if phrase and phrase in lowered:
            return phrase.strip()
    return None


def _content_words(text: str) -> set:
    out = set()
    word = []
    for ch in (text or '').lower():
        if ch.isalnum():
            word.append(ch)
        else:
            token = ''.join(word)
            if len(token) >= 4 and token not in _STOP:
                out.add(token)
            word = []
    token = ''.join(word)
    if len(token) >= 4 and token not in _STOP:
        out.add(token)
    return out


def _overlap(a: str, b: str) -> float:
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _blueprint_sections(story: dict) -> dict:
    sections = {}
    for section in (story.get('blueprint') or []):
        if isinstance(section, dict) and section.get('key'):
            sections[section['key']] = _clean(section.get('text'))
    return sections


def _beat_text(story: dict, key: str) -> str:
    for beat in (story.get('beats') or []):
        if isinstance(beat, dict) and beat.get('key') == key:
            return _clean(beat.get('text'))
    return ''


def _normalized_parts(story: dict) -> dict:
    """Resolve the editorial parts from the blueprint if present, else the beats.

    Returns the parts plus ``has_blueprint`` so structural checks know whether the
    5-section shape is available to validate.
    """
    bp = _blueprint_sections(story)
    has_blueprint = bool(bp)
    if has_blueprint:
        evidence = bp.get(EVIDENCE, '')
    else:
        evidence = '\n\n'.join(t for t in (_beat_text(story, 'baseline'), _beat_text(story, 'cause')) if t)
    return {
        'has_blueprint': has_blueprint,
        'blueprint': bp,
        SAW: bp.get(SAW, ''),
        NOTICED: bp.get(NOTICED) or _beat_text(story, 'observation'),
        EVIDENCE: evidence,
        WHY: bp.get(WHY, ''),
        TOMORROW: bp.get(TOMORROW) or _beat_text(story, 'constraint'),
    }


def _corpus(story: dict, parts: dict) -> str:
    pieces = [_clean(story.get('headline'))]
    if parts['has_blueprint']:
        pieces.extend(parts['blueprint'].values())
    else:
        pieces.append(_clean(story.get('narrative')))
        pieces.extend(_clean(b.get('text')) for b in (story.get('beats') or []) if isinstance(b, dict))
    return ' \n '.join(piece for piece in pieces if piece)


def review_story(story: dict) -> dict:
    """Produce an internal editorial report for one story. Never mutates input."""
    story = story if isinstance(story, dict) else {}
    story_id = story.get('story_id')

    if story.get('story_available') is not True:
        return {
            'capability': CAPABILITY, 'version': VERSION, 'story_id': story_id,
            'story_available': False, 'status': STATUS_NEUTRAL, 'checks': [], 'warnings': [],
        }

    parts = _normalized_parts(story)
    corpus = _corpus(story, parts)
    checks: list[dict] = []
    warnings: list[str] = []

    def record(key, label, status, warning=None):
        checks.append({'key': key, 'label': label, 'status': status})
        if status == CHECK_WARN and warning:
            warnings.append(warning)

    # 1. One primary idea (single story type + no explicit second-topic connector).
    multi = _first_match(parts[NOTICED], MULTI_IDEA_PHRASES)
    if not story.get('story_type'):
        record('one_primary_idea', 'One idea', CHECK_WARN, 'No story type set.')
    elif multi:
        record('one_primary_idea', 'One idea', CHECK_WARN, 'Multiple competing ideas detected.')
    else:
        record('one_primary_idea', 'One idea', CHECK_PASS)

    # 2. Structure complete (validate the 5 sections only when a blueprint exists).
    if parts['has_blueprint']:
        missing = [k for k in EXPECTED_BLUEPRINT_KEYS if not parts['blueprint'].get(k)]
        if missing:
            record('structure_complete', 'Structure complete', CHECK_WARN,
                   f"Missing blueprint section(s): {', '.join(missing)}.")
        else:
            record('structure_complete', 'Structure complete', CHECK_PASS)
    else:
        record('structure_complete', 'Structure complete', CHECK_NA)

    # 3. Evidence present.
    if parts[EVIDENCE]:
        record('evidence_present', 'Evidence present', CHECK_PASS)
    else:
        record('evidence_present', 'Evidence present', CHECK_WARN, 'No evidence section.')

    # 4. Educational principle ("why it matters" teaches, not restates). Only when
    #    a dedicated lesson section exists (blueprint); otherwise not applicable.
    lesson = parts[WHY]
    if not parts['has_blueprint'] or not lesson:
        record('educational_principle', 'Educational principle', CHECK_NA)
    else:
        team_tokens = [t for t in (
            _clean(story.get('team_name')).lower(),
            _clean(story.get('team_abbreviation')).lower(),
        ) if len(t) >= 3]
        repeats_evidence = _overlap(lesson, parts[EVIDENCE]) >= _OVERLAP_WARN_THRESHOLD
        too_specific = any(ch.isdigit() for ch in lesson) or any(t in lesson.lower() for t in team_tokens)
        if repeats_evidence:
            record('educational_principle', 'Educational principle', CHECK_WARN, 'Lesson repeats evidence.')
        elif too_specific:
            record('educational_principle', 'Educational principle', CHECK_WARN,
                   'Lesson restates a specific result rather than a transferable principle.')
        else:
            record('educational_principle', 'Educational principle', CHECK_PASS)

    # 5. Reader-facing takeaway present (the forward "carry"/constraint).
    if parts[TOMORROW]:
        record('reader_takeaway_present', 'Reader takeaway', CHECK_PASS)
    else:
        record('reader_takeaway_present', 'Reader takeaway', CHECK_WARN, 'No reader-facing takeaway.')

    # 6-11. Content guardrails (apply to the whole story).
    for key, label, phrases, warn_label in (
        ('avoids_prediction', 'No prediction', PREDICTION_PHRASES, 'Prediction language'),
        ('avoids_unsupported_certainty', 'Calibrated certainty', CERTAINTY_PHRASES, 'Unsupported certainty'),
        ('avoids_recap_wording', 'Not a recap', RECAP_PHRASES, 'Recap-heavy wording'),
        ('avoids_blame_language', 'No blame', BLAME_PHRASES, 'Blame language'),
        ('avoids_dramatic_journalism', 'No drama', DRAMA_PHRASES, 'Dramatic journalism'),
        ('avoids_internal_terminology', 'Plain language', INTERNAL_PHRASES, 'Internal terminology'),
    ):
        hit = _first_match(corpus, phrases)
        if hit:
            record(key, label, CHECK_WARN, f"{warn_label}: '{hit}'.")
        else:
            record(key, label, CHECK_PASS)

    return {
        'capability': CAPABILITY, 'version': VERSION, 'story_id': story_id,
        'story_available': True,
        'status': STATUS_WARN if warnings else STATUS_PASS,
        'checks': checks,
        'warnings': warnings,
    }


def review_canonical_feed(feed: dict) -> dict:
    """Review every available story in a canonical feed. Report-only; no mutation."""
    feed = feed if isinstance(feed, dict) else {}
    reviews = [
        review_story(item)
        for item in (feed.get('items') or [])
        if isinstance(item, dict) and item.get('story_available') is True
    ]
    pass_count = sum(1 for r in reviews if r['status'] == STATUS_PASS)
    warn_count = sum(1 for r in reviews if r['status'] == STATUS_WARN)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'reviewed': len(reviews),
        'pass_count': pass_count,
        'warn_count': warn_count,
        'summary': f'editorial review: {len(reviews)} stories, {pass_count} pass, {warn_count} with warnings',
        'reviews': reviews,
    }


__all__ = [
    'CAPABILITY', 'VERSION',
    'STATUS_PASS', 'STATUS_WARN', 'STATUS_NEUTRAL',
    'CHECK_PASS', 'CHECK_WARN', 'CHECK_NA',
    'EXPECTED_BLUEPRINT_KEYS',
    'PREDICTION_PHRASES', 'CERTAINTY_PHRASES', 'RECAP_PHRASES',
    'BLAME_PHRASES', 'DRAMA_PHRASES', 'MULTI_IDEA_PHRASES',
    'review_story', 'review_canonical_feed',
]
