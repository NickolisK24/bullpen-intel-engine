"""Share Artifact why copy: evidence-specific, grammatical, deterministic.

Three defects are pinned here, each fixed at its owner rather than repaired in
the rendered sentence.

1. **Every Fresh club in the league read identically.** ``_why`` consulted the
   public state and two coarse constraint families, and nothing else. The
   governed ``count`` already sitting on every constraint row was ignored, so a
   bullpen with one arm out and a bullpen with six read the same, and all four
   Fresh fixtures below collapsed to one sentence.

2. **The club name was a sentence subject.** "New York Yankees is missing a few
   bullpen arms, narrowing its clean options" disagreed with itself twice: club
   names take plural agreement. The why is now written around a possessive slot,
   which is number-neutral, so the disagreement cannot be expressed.

3. **Composed fields named the club twice in adjacent clauses.** "New York
   Yankees' bullpen is Fresh. New York Yankees' bullpen has a full set..." One
   selection is now rendered with two referring expressions — a first reference
   for the standalone why, a second reference wherever the club was just named.

The determinism cases are load-bearing: this changed *which* deterministic
sentence is chosen, never *whether* it is deterministic.
"""

import pytest

from services.team_state_public_copy import (
    _countable,
    _why_template,
    build_evidence_receipts,
    build_public_copy,
    team_possessive,
)


FRESH = 'operationally_stable'
STRETCHED = 'operationally_constrained'
VULNERABLE = 'operationally_stressed'

TEAM = 'New York Yankees'
PRODUCT_DATE = '2026-08-13'


def _constraint(affected_area, count, *, category=None, severity='caution'):
    return {
        'constraint_id': f'{affected_area}_{count}',
        'affected_area': affected_area,
        'category': category,
        'count': count,
        'severity': severity,
    }


def _copy(status_code, constraints=(), *, confidence='high', team_name=TEAM):
    return build_public_copy(
        team_name=team_name,
        team_abbreviation='NYY',
        status_code=status_code,
        confidence=confidence,
        constraints=list(constraints),
        product_date=PRODUCT_DATE,
    )


# ── the corpus ──────────────────────────────────────────────────────────────
#
# Materially different evidence in each row. Confidence is held at 'low' for the
# coverage row because the copy authority deliberately reconciles away the
# coarse coverage receipt at high/medium confidence.

CORPUS = (
    ('fresh: nothing flagged', FRESH, (), 'high'),
    ('fresh: one arm out', FRESH, (_constraint('availability_distribution', 1),), 'high'),
    ('fresh: three arms out', FRESH, (_constraint('availability_distribution', 3),), 'high'),
    ('fresh: workload on two', FRESH, (_constraint('workload_pressure', 2),), 'high'),
    ('fresh: handedness gap', FRESH, (_constraint('handedness_coverage', 2),), 'high'),
    ('fresh: limited read', FRESH, (_constraint('readiness', 1),), 'low'),
    ('stretched: workload on one', STRETCHED, (_constraint('workload_pressure', 1),), 'high'),
    ('stretched: workload on five', STRETCHED, (_constraint('workload_pressure', 5),), 'high'),
    ('stretched: two arms out', STRETCHED, (_constraint('availability_distribution', 2),), 'high'),
    ('vulnerable: one arm out', VULNERABLE, (_constraint('availability_distribution', 1),), 'high'),
    ('vulnerable: six arms out', VULNERABLE, (_constraint('availability_distribution', 6),), 'high'),
    ('vulnerable: workload on four', VULNERABLE, (_constraint('workload_pressure', 4),), 'high'),
)


def _corpus_whys():
    return {label: _copy(state, cons, confidence=conf)['why']
            for label, state, cons, conf in CORPUS}


def test_materially_different_evidence_does_not_collapse_to_one_sentence():
    whys = _corpus_whys()
    clusters = {}
    for label, why in whys.items():
        clusters.setdefault(why, []).append(label)
    largest = max(len(labels) for labels in clusters.values())
    assert len(clusters) == len(CORPUS), {
        why: labels for why, labels in clusters.items() if len(labels) > 1
    }
    assert largest == 1


def test_every_fresh_read_no_longer_reads_identically():
    """The specific collapse this package fixed: four Fresh rows, one sentence."""
    fresh = [why for label, why in _corpus_whys().items() if label.startswith('fresh')]
    assert len(fresh) == 6
    assert len(set(fresh)) == 6


def test_the_governed_count_reaches_the_sentence():
    assert '1 reliever' in _copy(VULNERABLE, (_constraint('availability_distribution', 1),))['why']
    assert '6 relievers' in _copy(VULNERABLE, (_constraint('availability_distribution', 6),))['why']


def test_the_why_never_predicts_or_advises():
    for label, why in _corpus_whys().items():
        lowered = why.lower()
        for forbidden in ('will ', 'expect', 'should ', 'tonight', 'tomorrow',
                          'next game', 'likely', 'projected'):
            assert forbidden not in lowered, (label, forbidden)


def test_the_why_never_repeats_the_state_label():
    for state in (FRESH, STRETCHED, VULNERABLE):
        why = _copy(state, (_constraint('availability_distribution', 2),))['why']
        for label in ('Fresh', 'Stretched', 'Vulnerable'):
            assert label not in why, (state, label)


# ── grammar ─────────────────────────────────────────────────────────────────

def test_the_club_name_is_never_a_bare_sentence_subject():
    """The audit's sentence disagreed with itself twice; the frame prevents it."""
    for label, state, cons, conf in CORPUS:
        why = _copy(state, cons, confidence=conf)['why']
        assert f'{TEAM} is ' not in why, label
        assert f'{TEAM} are ' not in why, label
        assert why.startswith(f"The {TEAM}'"), (label, why)


def test_a_team_name_carries_its_article_in_running_prose():
    assert team_possessive('New York Yankees') == "the New York Yankees'"
    assert team_possessive('Chicago White Sox') == "the Chicago White Sox's"
    assert team_possessive('') == "The team's"


def test_composed_fields_name_the_club_once_then_refer_back():
    copy = _copy(FRESH)
    assert copy['description'].startswith(f"The {TEAM}' bullpen is Fresh.")
    assert copy['description'].count(TEAM) == 1
    assert 'Their bullpen' in copy['description']

    assert copy['alt_text'].startswith(f'{TEAM} bullpen is Fresh.')
    assert copy['alt_text'].count(TEAM) == 1
    assert 'Their bullpen' in copy['alt_text']


def test_the_standalone_why_and_the_composed_why_are_one_claim():
    """Two referring expressions, one selection — they may not drift apart."""
    for label, state, cons, conf in CORPUS:
        copy = _copy(state, cons, confidence=conf)
        first = copy['why']
        tail = first.split(' bullpen', 1)[-1] if ' bullpen' in first else None
        if tail is None:
            continue
        assert tail in copy['description'], label
        assert tail in copy['alt_text'], label


# ── count and noun agreement ────────────────────────────────────────────────

@pytest.mark.parametrize('count,expected', [
    (1, '1 reliever '), (2, '2 relievers '), (11, '11 relievers '),
])
def test_count_and_noun_agree_in_the_why(count, expected):
    why = _copy(VULNERABLE, (_constraint('availability_distribution', count),))['why']
    assert expected in why.replace(',', ' ')


@pytest.mark.parametrize('count,fragment', [
    (1, '1 reliever is limited or unavailable.'),
    (2, '2 relievers are limited or unavailable.'),
])
def test_count_and_noun_agree_in_evidence_receipts(count, fragment):
    receipts = build_evidence_receipts([_constraint('availability_distribution', count)])
    assert receipts[0]['detail'] == fragment


# ── an unusable count never reaches a reader ────────────────────────────────

@pytest.mark.parametrize('bad', [None, 'x', -1, 2.5, True])
def test_an_unusable_count_is_not_published_as_a_number(bad):
    """The literal ``None relievers are limited or unavailable.`` shipped before."""
    detail = build_evidence_receipts([_constraint('availability_distribution', bad)])[0]['detail']
    assert 'None' not in detail
    assert str(bad) not in detail
    assert detail == 'Relievers are limited or unavailable.'


def test_countable_accepts_only_non_negative_integers():
    assert _countable(0) == 0
    assert _countable(4) == 4
    assert _countable(None) is None
    assert _countable(-1) is None
    assert _countable('3') is None
    assert _countable(True) is None  # bool is an int subclass; not a count


def test_an_unusable_count_does_not_steer_the_why():
    """A missing count must not silently read as a family with evidence."""
    why = _copy(VULNERABLE, (_constraint('availability_distribution', None),))['why']
    assert 'None' not in why
    assert why == f"The {TEAM}' bullpen has fewer clean options available after recent work."


# ── determinism (mandatory) ─────────────────────────────────────────────────

def test_identical_evidence_yields_byte_identical_copy_across_repeats():
    for label, state, cons, conf in CORPUS:
        runs = [_copy(state, cons, confidence=conf) for _ in range(3)]
        assert runs[0] == runs[1] == runs[2], label


def test_the_copy_authority_introduces_no_randomness():
    import services.team_state_public_copy as module
    source = open(module.__file__, encoding='utf-8').read()
    for banned in ('import random', 'random.choice', 'random.shuffle',
                   'datetime.now', 'utcnow', 'time.time'):
        assert banned not in source, banned


def test_selection_depends_on_evidence_not_on_team_name():
    a = _copy(VULNERABLE, (_constraint('availability_distribution', 3),), team_name='Miami Marlins')
    b = _copy(VULNERABLE, (_constraint('availability_distribution', 3),), team_name=TEAM)
    assert a['why'].split(' bullpen', 1)[-1] == b['why'].split(' bullpen', 1)[-1]


# ── immutable history ───────────────────────────────────────────────────────

def test_stored_artifact_copy_is_read_back_verbatim_not_regenerated():
    """A published artifact keeps the sentence it was published with.

    The public read service returns stored ``public_copy.evidence`` when the
    document carries it, so a generator change cannot restate an old artifact.
    """
    from services.share_artifact_public import _evidence_items

    frozen = {
        'evidence': [
            {'evidence_id': 'availability_constrained',
             'kind': 'availability',
             'label': 'Available bullpen options',
             'detail': '2 relievers are limited or unavailable.',
             'severity': 'caution',
             'count': 2},
        ],
    }
    # Constraints that would generate different copy today.
    team_state = {'constraints': [_constraint('workload_pressure', 9)]}
    assert _evidence_items(team_state, frozen) == frozen['evidence']


def test_a_legacy_document_without_stored_copy_still_renders_safely():
    from services.share_artifact_public import _evidence_items

    items = _evidence_items({'constraints': [_constraint('availability_distribution', 2)]}, {})
    assert items[0]['detail'] == '2 relievers are limited or unavailable.'
    assert 'availability_distribution' not in items[0]['label']


# ── clean options: one concept, three governed scopes ───────────────────────
#
# The audit flagged "clean options" as a cross-surface conflict. It is not
# drift; it is surface scoping that had never been written down. Pinned here so
# a future change has to break a test rather than a reader's page.

def test_share_artifact_copy_may_say_clean_options():
    """The Share Artifact guard is the owner on this surface, and it allows it."""
    copy = _copy(FRESH)
    assert 'clean options' in copy['why']
    # build_public_copy runs guard_public_copy internally; reaching here is the
    # proof that the owning guard permits the phrase.


def test_the_editorial_deny_list_is_not_the_share_artifact_guard():
    """Widening the review deny list into a global ban would unpublish the why."""
    from services.editorial_voice_contract_v1 import EDITORIAL_BANNED_LANGUAGE
    from services.team_state_public_vocabulary import find_banned_public_language

    assert 'clean options' in EDITORIAL_BANNED_LANGUAGE
    # The Share Artifact guard is a different authority and does not ban it.
    assert find_banned_public_language('why', _copy(FRESH)['why']) is None


def test_the_review_surfaces_still_deny_clean_options():
    """The narrower scope keeps its rule; this package did not weaken it."""
    from services.editorial_voice_contract_v1 import find_editorial_violations

    violations = find_editorial_violations('The bullpen has four clean options tonight.')
    assert any('clean option' in str(v).lower() for v in violations)
