"""V2 Story Blueprint (Phase A) — a 5-section teaching shape over existing beats.

Reframes an already-written four-beat story into the public teaching structure:

  1. What everyone saw       (surface framing — generic, evergreen public voice)
  2. What BaseballOS noticed (the existing observation beat)
  3. Evidence                (the existing baseline + cause beats)
  4. Why it matters          (a transferable baseball lesson — voice library)
  5. Why it matters tomorrow (the existing constraint beat)

It creates NO new facts and makes NO new claims: sections 2 / 3 / 5 reuse the
already-authored, already-validated beat prose; sections 1 / 4 are deterministic,
fact-free public copy from the approved voice library. Deterministic and
LLM-free, consistent with the existing story engine. Out-of-data archetypes
(within-game order, handoff chains, inning-level events) are intentionally not
introduced here.
"""

from __future__ import annotations

from typing import Any

from services.story_evidence_case_v1 import build_evidence_case
from services.story_voice_library_v1 import (
    PURPOSE_LESSON,
    PURPOSE_SURFACE,
    render_voice_line,
)


CAPABILITY = 'story_blueprint_v1'
VERSION = '2026-06-25.v1'

# Blueprint section keys + public labels (the teaching shape).
SECTION_SAW = 'what_everyone_saw'
SECTION_NOTICED = 'what_baseballos_noticed'
SECTION_EVIDENCE = 'evidence'
SECTION_WHY = 'why_it_matters'
SECTION_TOMORROW = 'why_it_matters_tomorrow'

SECTION_LABELS = {
    SECTION_SAW: 'What everyone saw',
    SECTION_NOTICED: 'What BaseballOS noticed',
    SECTION_EVIDENCE: 'Evidence',
    SECTION_WHY: 'Why it matters',
    SECTION_TOMORROW: 'Why it matters tomorrow',
}

SECTION_ORDER = (
    SECTION_SAW,
    SECTION_NOTICED,
    SECTION_EVIDENCE,
    SECTION_WHY,
    SECTION_TOMORROW,
)

# Which existing beat feeds each reused section.
_NOTICED_BEAT_KEY = 'observation'
_TOMORROW_BEAT_KEY = 'constraint'
_EVIDENCE_BEAT_KEYS = ('baseline', 'cause')


def _clean(value: Any) -> str:
    return ' '.join(str(value).split()) if isinstance(value, str) else ''


def _beat_text(beats, key) -> str:
    for beat in beats or ():
        if isinstance(beat, dict) and beat.get('key') == key:
            return _clean(beat.get('text'))
    return ''


def _evidence_text(beats) -> str:
    parts = [_beat_text(beats, key) for key in _EVIDENCE_BEAT_KEYS]
    return '\n\n'.join(part for part in parts if part)


def _section(key, text, source):
    return {'key': key, 'label': SECTION_LABELS[key], 'text': text, 'source': source}


def build_story_blueprint(*, story_type, beats, stable_parts=(), frame=None) -> list[dict]:
    """Build the 5-section teaching blueprint for one available story.

    Returns ``[]`` when there is no usable ``story_type`` or no authored beats, so
    a suppressed / empty story carries an empty blueprint (backward-compatible).
    Sections are emitted in canonical order and only when they carry text.

    When the construction ``frame`` is supplied, the Evidence section is a curated
    Evidence Case built from the frame's structured facts (strongest support, one
    corroborating fact, one plain-language meaning). Without a frame — or if the
    case cannot be built — Evidence falls back to the existing baseline + cause
    beat text, so output is never lost (backward-compatible).
    """
    story_type = _clean(story_type)
    if not story_type or not beats:
        return []

    surface = render_voice_line(
        story_type, purpose=PURPOSE_SURFACE, stable_parts=tuple(stable_parts),
    )
    lesson = render_voice_line(
        story_type, purpose=PURPOSE_LESSON, stable_parts=tuple(stable_parts),
    )

    evidence_text = (
        build_evidence_case(frame, story_type=story_type, variety_key=tuple(stable_parts))
        if frame else ''
    )
    evidence_source = 'evidence_case' if evidence_text else 'evidence'
    if not evidence_text:
        evidence_text = _evidence_text(beats)

    candidates = (
        _section(SECTION_SAW, _clean(surface), 'framing'),
        _section(SECTION_NOTICED, _beat_text(beats, _NOTICED_BEAT_KEY), _NOTICED_BEAT_KEY),
        _section(SECTION_EVIDENCE, evidence_text, evidence_source),
        _section(SECTION_WHY, _clean(lesson), 'lesson'),
        _section(SECTION_TOMORROW, _beat_text(beats, _TOMORROW_BEAT_KEY), _TOMORROW_BEAT_KEY),
    )
    return [section for section in candidates if section['text']]


__all__ = [
    'CAPABILITY',
    'VERSION',
    'SECTION_SAW',
    'SECTION_NOTICED',
    'SECTION_EVIDENCE',
    'SECTION_WHY',
    'SECTION_TOMORROW',
    'SECTION_LABELS',
    'SECTION_ORDER',
    'build_story_blueprint',
]
