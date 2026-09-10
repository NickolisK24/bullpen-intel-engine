"""Story Reasoning Engine V1 (V2).

A deterministic reasoning layer that sits BETWEEN Story Construction and the
Story Writer. It does not generate prose, does not rewrite the writer, does not
add baseball data, and never calls an external model. Given a construction frame
(and the observation it came from), it produces one *editorial intent object* —
the deterministic answer to the five editorial questions a good BaseballOS story
must answer:

  1. misconception          — the surface read the average fan already has
  2. structural_truth       — the deeper structural truth beneath that read
  3. supporting_evidence    — the specific frame facts that support the truth
  4. transferable_principle — the evergreen baseball lesson it teaches
  5. reader_shift           — how to watch the next game differently

The writer consumes this object (it carries it through its output) so the same
reasoning is available to every downstream layer. The object is INTERNAL ONLY:
it is attached to the writer output, which is never serialized to the public API
or into the canonical story feed.

Design contract:
  * Deterministic and LLM-free. Same inputs -> byte-identical object.
  * Additive and backward-compatible. It reads existing structures (the public
    beat map, the voice library, the construction frame) and creates no new
    baseball facts, no predictions, and no unsupported claims.
  * Governed copy. The surface read and the transferable principle reuse the
    already-approved voice library (PURPOSE_SURFACE / PURPOSE_LESSON). The two
    new copy banks (structural truth, reader shift) are generic, evergreen, and
    clear every existing guardrail vocabulary.
  * Fault-isolated. An unsupported observation type, or a sparse frame, yields a
    well-formed object with null fields and recorded limitations rather than an
    error.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.story_four_beat_interpreter_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
    PUBLIC_BEATS,
    public_beat_for_observation,
)
from services.story_voice_library_v1 import (
    PURPOSE_LESSON,
    PURPOSE_SURFACE,
    render_voice_line,
)


CAPABILITY = 'story_reasoning_engine_v1'
VERSION = '2026-06-25.v1'

# Editorial-intent field keys (the five answered questions, plus the evidence the
# answers rest on). Exported so callers/tests reference them symbolically.
FIELD_MISCONCEPTION = 'misconception'
FIELD_STRUCTURAL_TRUTH = 'structural_truth'
FIELD_SUPPORTING_EVIDENCE = 'supporting_evidence'
FIELD_TRANSFERABLE_PRINCIPLE = 'transferable_principle'
FIELD_READER_SHIFT = 'reader_shift'

EDITORIAL_QUESTIONS = {
    FIELD_MISCONCEPTION: 'What surface-level read does the average fan already have?',
    FIELD_STRUCTURAL_TRUTH: 'What deeper structural truth does the bullpen picture reveal?',
    FIELD_SUPPORTING_EVIDENCE: 'Which specific evidence best supports that truth?',
    FIELD_TRANSFERABLE_PRINCIPLE: 'What transferable baseball principle does this teach?',
    FIELD_READER_SHIFT: 'How should the reader watch the next game differently?',
}

# The deeper structural truth per public beat. Generic and evergreen: it names
# the structural reality beneath the surface read without asserting any specific
# result, number, within-game event, prediction, or blame. The story's concrete
# numbers live in supporting_evidence, not here.
TRUTH_BY_BEAT = {
    BEAT_ROUTE_CHANGE: (
        'The set of arms a manager reaches for in the late innings has quietly '
        'shifted, even though the roster looks the same.'
    ),
    BEAT_COVERAGE_PRESSURE: (
        'The bullpen is absorbing innings the rotation usually covers, so a '
        'steady result is sitting on top of a heavier real workload.'
    ),
    BEAT_DEPTH_CONSTRAINT: (
        'The arms a manager can truly use late are fewer than the roster count, '
        'because rest and trust decide how many are really available.'
    ),
    BEAT_SUSTAINABILITY_QUESTION: (
        'The recent work keeps returning to the same few arms, so the pattern '
        'leans on a narrow base rather than the whole group.'
    ),
    BEAT_AVAILABILITY_DEPTH: (
        'The bullpen has several rested, usable arms, so the manager has more '
        'than one clean way through the late innings.'
    ),
    BEAT_TRUST_LANE: (
        'The late-game plan really runs through a small circle of trusted arms, '
        'narrower than the full bullpen list suggests.'
    ),
    BEAT_BRIDGE: (
        'The hard part is the path to the late-inning arms, not the late-inning '
        'arms themselves.'
    ),
}

# How a reader should watch the next game differently, per public beat. These are
# observational instructions ("watch how / which / whether"), not predictions:
# they direct attention, they do not claim an outcome.
WATCH_BY_BEAT = {
    BEAT_ROUTE_CHANGE: (
        'Next game, watch which arms get the highest-leverage outs, not just who '
        'finishes.'
    ),
    BEAT_COVERAGE_PRESSURE: (
        'Next game, watch how early the bullpen has to start working, not just '
        'the final line.'
    ),
    BEAT_DEPTH_CONSTRAINT: (
        'Next game, watch how quickly a long night runs the bullpen short, not '
        'just how many arms are listed.'
    ),
    BEAT_SUSTAINABILITY_QUESTION: (
        'Over the next week, watch whether the work spreads out or keeps landing '
        'on the same arms.'
    ),
    BEAT_AVAILABILITY_DEPTH: (
        'Next close game, watch how many different rested arms the manager can '
        'call on late.'
    ),
    BEAT_TRUST_LANE: (
        'Next tight game, watch how small the group of arms the manager truly '
        'trusts really is.'
    ),
    BEAT_BRIDGE: (
        'Next game, watch how a team tries to get to its closer, not just the '
        'closer itself.'
    ),
}

# Frame fact sections the engine draws supporting evidence from, in editorial
# preference order (why it is happening, the comparison point, what it means,
# what was measured). One distinct fact is taken from each present section so the
# evidence spans the full picture rather than repeating one metric.
EVIDENCE_SECTIONS = (
    'cause_facts',
    'baseline_facts',
    'interpretation_facts',
    'observation_facts',
)

# Keys that are structural labels, not evidence.
_EVIDENCE_SKIP_KEYS = ('type', 'team_name')

MAX_SUPPORTING_EVIDENCE = 4


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _present(value: Any) -> bool:
    """A fact is present when it carries a real value.

    Zero is meaningful evidence (e.g. zero clean late-inning options), so only
    None, empty strings, and empty containers are treated as absent.
    """
    if value is None or value == '':
        return False
    if isinstance(value, (list, tuple, dict)) and not value:
        return False
    return True


def _frame_sections(frame: Any) -> dict:
    """Return the fact-section container, mirroring the writer/interpreter.

    Construction frames nest their fact sections under ``story_frame``; this
    accepts either a full frame or a bare sections dict so the engine is robust
    to how it is called.
    """
    frame = _dict(frame)
    sections = frame.get('story_frame')
    return sections if isinstance(sections, dict) else frame


def _resolve_beat(story_type: Any, observation_type: Any, frame: dict) -> str | None:
    """Resolve the public editorial beat for this story.

    Prefers an already-resolved public ``story_type`` (the four-beat interpreter's
    output); otherwise resolves it from the internal observation type with the
    same deterministic mapping the public layer uses. Returns ``None`` for an
    unsupported type so the caller degrades gracefully.
    """
    story_type = _clean_text(story_type)
    if story_type in PUBLIC_BEATS:
        return story_type
    beat = public_beat_for_observation(observation_type, frame=frame)
    return beat if beat in PUBLIC_BEATS else None


def select_supporting_evidence(frame: Any) -> list[dict]:
    """Select the frame facts that best support the story, deterministically.

    Takes the first present, non-label fact from each evidence section in
    preference order, de-duplicated by metric, capped at ``MAX_SUPPORTING_EVIDENCE``.
    Returns ``[]`` for an empty or factless frame.
    """
    sections = _frame_sections(frame)
    chosen: list[dict] = []
    seen_keys: set = set()
    for section in EVIDENCE_SECTIONS:
        facts = _dict(sections.get(section))
        for key, value in facts.items():
            if key in _EVIDENCE_SKIP_KEYS or key in seen_keys:
                continue
            if not _present(value):
                continue
            chosen.append({'section': section, 'key': key, 'value': deepcopy(value)})
            seen_keys.add(key)
            break
        if len(chosen) >= MAX_SUPPORTING_EVIDENCE:
            break
    return chosen


def _empty_intent(beat, observation_type, severity, confidence, limitations):
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'story_type': beat,
        'observation_type': observation_type,
        'severity': severity,
        'confidence': confidence,
        FIELD_MISCONCEPTION: None,
        FIELD_STRUCTURAL_TRUTH: None,
        FIELD_SUPPORTING_EVIDENCE: [],
        FIELD_TRANSFERABLE_PRINCIPLE: None,
        FIELD_READER_SHIFT: None,
        'limitations': list(limitations),
    }


def build_editorial_intent(
    *,
    story_type: Any = None,
    observation_type: Any = None,
    frame: Any = None,
    selected_observation: Any = None,
) -> dict:
    """Build the deterministic editorial intent object for one story candidate.

    The reasoning layer between Story Construction and the Story Writer. It
    answers the five editorial questions from already-existing structures (the
    public beat map, the approved voice library, and the construction frame's
    facts). It invents no baseball data, makes no prediction, and never mutates
    its inputs.
    """
    frame = _dict(frame)
    selected_observation = _dict(selected_observation)
    observation_type = (
        observation_type
        or frame.get('observation_type')
        or selected_observation.get('type')
    )
    severity = (
        _clean_text(selected_observation.get('severity'))
        or _clean_text(frame.get('severity'))
        or None
    )
    confidence = (
        _clean_text(frame.get('construction_confidence'))
        or _clean_text(frame.get('confidence'))
        or _clean_text(selected_observation.get('confidence'))
        or None
    )

    beat = _resolve_beat(story_type, observation_type, frame)
    if beat is None:
        return _empty_intent(
            None, observation_type, severity, confidence, ['unsupported_story_type'],
        )

    # Stable per-team, per-beat selection so the chosen surface read and lesson
    # are reproducible for the same story without randomness.
    stable_parts = (
        frame.get('team_id'),
        frame.get('team_abbreviation'),
        observation_type,
        beat,
    )

    misconception = _clean_text(
        render_voice_line(beat, purpose=PURPOSE_SURFACE, stable_parts=stable_parts)
    ) or None
    transferable_principle = _clean_text(
        render_voice_line(beat, purpose=PURPOSE_LESSON, stable_parts=stable_parts)
    ) or None
    structural_truth = _clean_text(TRUTH_BY_BEAT.get(beat)) or None
    reader_shift = _clean_text(WATCH_BY_BEAT.get(beat)) or None
    supporting_evidence = select_supporting_evidence(frame)

    limitations: list[str] = []
    if not misconception:
        limitations.append('misconception_unavailable')
    if not structural_truth:
        limitations.append('structural_truth_unavailable')
    if not supporting_evidence:
        limitations.append('no_structured_evidence')
    if not transferable_principle:
        limitations.append('transferable_principle_unavailable')
    if not reader_shift:
        limitations.append('reader_shift_unavailable')

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'story_type': beat,
        'observation_type': observation_type,
        'severity': severity,
        'confidence': confidence,
        FIELD_MISCONCEPTION: misconception,
        FIELD_STRUCTURAL_TRUTH: structural_truth,
        FIELD_SUPPORTING_EVIDENCE: supporting_evidence,
        FIELD_TRANSFERABLE_PRINCIPLE: transferable_principle,
        FIELD_READER_SHIFT: reader_shift,
        'limitations': limitations,
    }


def reasoning_engine_report() -> dict:
    """Compact deterministic metadata for audit tests and tooling."""
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'deterministic': True,
        'editorial_questions': dict(EDITORIAL_QUESTIONS),
        'beats_covered': sorted(set(TRUTH_BY_BEAT) & set(WATCH_BY_BEAT) & set(PUBLIC_BEATS)),
        'evidence_sections': list(EVIDENCE_SECTIONS),
        'max_supporting_evidence': MAX_SUPPORTING_EVIDENCE,
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'EDITORIAL_QUESTIONS',
    'EVIDENCE_SECTIONS',
    'FIELD_MISCONCEPTION',
    'FIELD_READER_SHIFT',
    'FIELD_STRUCTURAL_TRUTH',
    'FIELD_SUPPORTING_EVIDENCE',
    'FIELD_TRANSFERABLE_PRINCIPLE',
    'MAX_SUPPORTING_EVIDENCE',
    'TRUTH_BY_BEAT',
    'WATCH_BY_BEAT',
    'build_editorial_intent',
    'reasoning_engine_report',
    'select_supporting_evidence',
]
