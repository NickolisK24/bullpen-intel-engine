"""Feed-level editorial variety coordinator (V2 Feed Variety Pass).

The Editorial Calibration Lab found that, read together, same-beat stories felt
mass-produced: identical headlines, surface openers, and lessons recurred across
cards. This coordinator runs once during canonical feed assembly, after every
story is built, and de-duplicates the highest-visibility phrasing across the feed
so adjacent cards feel individually authored.

It is deterministic and conservative:
  * It only re-selects from the ALREADY-APPROVED voice library forms for the same
    beat and the same slot — it never writes new copy, never changes a fact, and
    never alters story meaning.
  * It only varies a slot when the current line is a GENERIC (team-only / slot-
    free) approved line that another card already used, and only swaps in an
    alternate it can fully render from team-level fields (team / possessive). A
    name-bearing line is left untouched (it is already distinct per team and its
    player names cannot be reconstructed here), so no names are ever invented or
    dropped.
  * Same input feed -> same output feed: stories are processed in feed order and
    each choice is a stable hash of the story id and slot.

It varies the headline, the "what everyone saw" opener, the "why it matters"
lesson, and the fact-free Evidence meaning sentence. The "why it matters
tomorrow" carry line is intentionally left alone — it mirrors the constraint beat
and is mostly name-bearing — so the blueprint never diverges from the underlying
beats. The factual Evidence sentences (numbers and names) are never touched here;
only the closing meaning line is swapped, and only for another approved line from
the same bank.
"""

from __future__ import annotations

from copy import deepcopy
from string import Formatter
from typing import Any

from services.story_evidence_case_v1 import MEANING_VARIANTS
from services.story_voice_library_v1 import (
    PURPOSE_LESSON,
    PURPOSE_OPENING,
    PURPOSE_SURFACE,
    approved_sentence_forms,
    contains_banned_public_language,
    contains_denied_public_phrase,
    stable_voice_index,
)


CAPABILITY = 'story_feed_variety_v1'
VERSION = '2026-06-25.v1'

SLOT_HEADLINE = 'headline'
SLOT_SAW = 'what_everyone_saw'
SLOT_WHY = 'why_it_matters'
SLOT_EVIDENCE = 'evidence'

# Flat lookup from an approved Evidence meaning line to the bank it belongs to.
# The meaning lines are fact-free and unique per bank, so a feed-wide de-dup can
# swap one for another approved line in the same bank without touching any fact.
_MEANING_BY_TEXT = {
    ' '.join(str(line).split()).lower(): tuple(bank)
    for bank in MEANING_VARIANTS.values()
    for line in bank
}

# (slot key, voice-library purpose). Order = resolution order across the feed.
VARIETY_SLOTS = (
    (SLOT_HEADLINE, PURPOSE_OPENING),
    (SLOT_SAW, PURPOSE_SURFACE),
    (SLOT_WHY, PURPOSE_LESSON),
)

# Fields fillable from a canonical story without player names or new data. Forms
# needing {names} (or anything else) are not eligible candidates.
_TEAM_SLOT_FIELDS = frozenset({'team', 'possessive'})


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _possessive(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ''
    low = text.lower()
    if low.endswith('sox'):
        return f"{text}'"
    return f"{text}'" if low.endswith('s') else f"{text}'s"


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ''


def _template_fields(template: str) -> set:
    fields = set()
    for _, field, _, _ in Formatter().parse(template):
        if field:
            fields.add(field)
    return fields


def _render(template: str, slots: dict) -> str:
    return _clean(template.format_map(_SafeDict({k: _clean(v) for k, v in slots.items()})))


def _is_clean(text: str) -> bool:
    return (
        bool(text)
        and '{' not in text and '}' not in text
        and not contains_banned_public_language(text)
        and not contains_denied_public_phrase(text)
    )


def _team_slots(item: dict) -> dict:
    team = _clean(item.get('team_name'))
    return {'team': team, 'possessive': _possessive(team)}


def _renderable_candidates(beat: str, purpose: str, team_slots: dict) -> list:
    """Approved forms for (beat, purpose) renderable from team-level fields only."""
    out: list = []
    seen: set = set()
    for form in approved_sentence_forms(beat, purpose):
        if not _template_fields(form) <= _TEAM_SLOT_FIELDS:
            continue
        text = _render(form, team_slots)
        if not _is_clean(text) or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _get_slot(item: dict, slot: str) -> str:
    if slot == SLOT_HEADLINE:
        return _clean(item.get('headline'))
    for section in item.get('blueprint') or []:
        if isinstance(section, dict) and section.get('key') == slot:
            return _clean(section.get('text'))
    return ''


def _set_slot(item: dict, slot: str, text: str) -> None:
    if slot == SLOT_HEADLINE:
        old = _clean(item.get('headline'))
        item['headline'] = text
        # share_title only mirrors the headline in the fallback case (no team +
        # label); keep it consistent there, leave the team+label form alone.
        if _clean(item.get('share_title')) == old:
            item['share_title'] = text
        return
    for section in item.get('blueprint') or []:
        if isinstance(section, dict) and section.get('key') == slot:
            section['text'] = text
            return


def _pick_alternate(candidates: list, used: set, seed_parts: tuple) -> str | None:
    """First unused candidate, scanning from a stable per-story offset."""
    fresh = [c for c in candidates if c not in used]
    if not fresh:
        return None
    start = stable_voice_index(seed_parts, len(fresh))
    return fresh[start]


def _evidence_text(item: dict) -> str:
    for section in item.get('blueprint') or []:
        if isinstance(section, dict) and section.get('key') == SLOT_EVIDENCE:
            return _clean(section.get('text'))
    return ''


def _set_evidence_text(item: dict, text: str) -> None:
    for section in item.get('blueprint') or []:
        if isinstance(section, dict) and section.get('key') == SLOT_EVIDENCE:
            section['text'] = text
            return


def _split_sentences(text: str) -> list:
    # Evidence sentences are simple declaratives joined by '. '; decimals (e.g.
    # "4.2") have no following space, so they are never split.
    return [s.strip().rstrip('.') for s in text.split('. ') if s.strip()]


def _vary_evidence_meanings(result: list) -> None:
    """De-duplicate the Evidence meaning sentence across the feed.

    The meaning sentence is fact-free and a member of an approved bank, so when a
    later card repeats one already used, swap it for another approved line from
    the same bank. Facts (the lead and corroborating sentences) are untouched.
    """
    used: set = set()
    for item in result:
        if not isinstance(item, dict) or item.get('story_available') is not True:
            continue
        text = _evidence_text(item)
        if not text:
            continue
        sentences = _split_sentences(text)
        idx = next(
            (i for i, s in enumerate(sentences) if _clean(s).lower() in _MEANING_BY_TEXT),
            None,
        )
        if idx is None:
            continue
        current = _clean(sentences[idx])
        key = current.lower()
        if key not in used:
            used.add(key)
            continue
        bank = _MEANING_BY_TEXT[key]
        fresh = [v for v in bank if _clean(v).lower() not in used]
        if fresh:
            alt = fresh[stable_voice_index((CAPABILITY, SLOT_EVIDENCE, _clean(item.get('story_id'))), len(fresh))]
            sentences[idx] = _clean(alt)
            _set_evidence_text(item, '. '.join(sentences) + '.')
            used.add(_clean(alt).lower())
        else:
            used.add(key)  # no approved alternative left: keep, allow repeat


def apply_feed_variety(items: Any) -> list:
    """Return a variety-adjusted copy of the ordered canonical story items.

    Deterministic and pure: the input list/items are never mutated. Suppressed or
    typeless items pass through unchanged.
    """
    items = list(items or [])
    result = [deepcopy(item) if isinstance(item, dict) else item for item in items]

    for slot, purpose in VARIETY_SLOTS:
        used: set = set()
        for item in result:
            if not isinstance(item, dict) or item.get('story_available') is not True:
                continue
            beat = _clean(item.get('story_type'))
            if not beat:
                continue
            current = _get_slot(item, slot)
            if not current:
                continue
            if current not in used:
                used.add(current)
                continue
            # Collision. Only swap a generic (team-only/slot-free) line; never a
            # name-bearing one.
            candidates = _renderable_candidates(beat, purpose, _team_slots(item))
            if current not in candidates:
                used.add(current)  # name-bearing or unrecognized: leave as-is
                continue
            alternate = _pick_alternate(
                candidates, used, (CAPABILITY, slot, beat, _clean(item.get('story_id'))),
            )
            if alternate:
                _set_slot(item, slot, alternate)
                used.add(alternate)
            else:
                used.add(current)  # no approved alternative left: keep, allow dup

    # Evidence body: de-duplicate the fact-free meaning sentence across the feed.
    _vary_evidence_meanings(result)
    return result


def feed_variety_report() -> dict:
    """Compact deterministic metadata for audit tests."""
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'deterministic': True,
        'varied_slots': [slot for slot, _ in VARIETY_SLOTS] + [SLOT_EVIDENCE],
        'reuses_approved_copy_only': True,
        'changes_facts': False,
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'SLOT_HEADLINE',
    'SLOT_SAW',
    'SLOT_WHY',
    'SLOT_EVIDENCE',
    'VARIETY_SLOTS',
    'apply_feed_variety',
    'feed_variety_report',
]
