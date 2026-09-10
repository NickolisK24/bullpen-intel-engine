"""One team page, one claim (H-8).

``/team/{ABBR}`` publishes two projections of the same publication: the social
unfurl a crawler reads and the small body a scriptless reader sees. They used to
be selected independently -- the metadata from a canonical story, the body from
the published Team Board -- under one shared snapshot id, with nothing comparing
them. That let one page carry two different bullpen claims:

    og:description  The Yankees bullpen is Fresh with seven close-game
                    options available. Data through 2026-08-13.
    body            BaseballOS Team State: Vulnerable.
                    5 relievers are Unavailable.
    snapshot        4821 for both

and pages whose story prose described one date beneath a stamp carrying another.

The published Team Board owns this page's claim: every receipt field, the Team
State and the baseball point come from it, and the page exists to hand the
reader to it. A canonical story may still supply the social wording (DIST-003 /
#594), but only when it agrees with the claim. When it disagrees the page falls
back to the board's own governed wording, so both projections keep describing
one claim rather than the reader's dated read being withheld.

Checks are structural: identity fields compared directly, Team State compared
against the canonical three-label catalogue. No sentence is parsed to guess at
meaning.
"""

import pytest

from services.team_story_previews import (
    REPRESENTATION_DATED_READ,
    REPRESENTATION_WITHHELD,
    STORY_REJECTED_DATE_MISMATCH,
    STORY_REJECTED_STATE_CONFLICT,
    STORY_REJECTED_TEAM_MISMATCH,
    WITHHELD_AUTHORITY_MISMATCH,
    WITHHELD_NO_DATA_THROUGH,
    WITHHELD_NO_TRUSTED_PUBLICATION,
    build_team_story_preview,
    render_team_story_html,
    story_claim_disagreement,
)


TEAM = {'team_id': 147, 'team_name': 'New York Yankees', 'team_abbreviation': 'NYY'}
SNAPSHOT = '4821'
DATA_THROUGH = '2026-08-13'
GENERATED_AT = '2026-08-13T15:00:00+00:00'


def _board(
    *,
    state='Stretched',
    data_through=DATA_THROUGH,
    unavailable=2,
    snapshot_id=SNAPSHOT,
    state_available=True,
    publication=True,
):
    board = {
        'team': TEAM,
        'context': {
            'health': {
                'state': 'elevated',
                'label': 'The bullpen is short on rested arms right now.',
                'reasons': [
                    f'{unavailable} relievers are Unavailable.',
                    'Availability classifications are workload-based only.',
                ],
            }
        },
        'team_shape': {'reads': []},
        'freshness': {'data_through': data_through},
        'team_state': (
            {'available': True, 'public_label': state}
            if state_available
            else {'available': False, 'unavailable_message': 'No current Team State read.'}
        ),
    }
    if publication:
        board['publication_authority'] = {
            'contract': 'trusted_public_serving_v1',
            'authority_type': 'trusted_snapshot',
            'snapshot_id': snapshot_id,
            'sync_run_id': '9001',
            'published_at': '2026-08-13T14:05:00+00:00',
            'snapshot_generated_at': '2026-08-13T14:00:00+00:00',
            'availability_reference_date': DATA_THROUGH,
        }
    return board


def _story(*, date=DATA_THROUGH, share_title=None, share_summary=None, team=TEAM):
    return {
        'story_id': f"{team['team_id']}:{date}",
        'team_id': team['team_id'],
        'team_name': team['team_name'],
        'team_abbreviation': team['team_abbreviation'],
        'date': date,
        'story_available': True,
        'story_type': 'coverage_pressure',
        'category': 'stressed',
        'tone': 'stress',
        'headline': share_title or 'Yankees bullpen note',
        'narrative': 'Supporting cause.',
        'share_title': share_title or 'Yankees bullpen: coverage pressure',
        'share_summary': share_summary
        or 'The Yankees leaned on a small group of late-inning arms.',
    }


def _preview(**kwargs):
    kwargs.setdefault('board', _board())
    kwargs.setdefault('generated_at', GENERATED_AT)
    return build_team_story_preview(TEAM, **kwargs)


def _body_text(html_text):
    import re

    body = html_text.split('<body>', 1)[-1]
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', body)).strip()


# ── the agreement case still uses the story (DIST-003 preserved) ────────────

def test_an_agreeing_story_still_words_the_unfurl():
    preview = _preview(story=_story())
    assert preview['source'] == 'canonical_story'
    assert preview['og_title'] == 'Yankees bullpen: coverage pressure'
    assert preview['authority']['title'] == 'canonical_story.share_title'


def test_an_agreeing_story_may_name_the_pages_own_team_state():
    preview = _preview(
        story=_story(share_summary='The Yankees bullpen is Stretched after heavy use.'),
        board=_board(state='Stretched'),
    )
    assert preview['source'] == 'canonical_story'


# ── the H-8 defect: a story cannot contradict the claim ────────────────────

def test_a_story_naming_a_different_team_state_is_refused():
    preview = _preview(
        story=_story(
            share_title='Yankees bullpen: Fresh',
            share_summary='The Yankees bullpen is Fresh with seven close-game options available.',
        ),
        board=_board(state='Vulnerable', unavailable=5),
    )
    assert preview['source'] == 'trusted_team_board'
    assert STORY_REJECTED_STATE_CONFLICT in preview['authority']['description']
    assert 'Fresh' not in preview['og_description']
    assert 'Vulnerable' in preview['og_description']


def test_a_story_representing_another_date_is_refused():
    preview = _preview(
        story=_story(
            date='2026-08-08',
            share_summary='The Yankees leaned on a small group of arms on August 8.',
        ),
        board=_board(data_through=DATA_THROUGH),
    )
    assert preview['source'] == 'trusted_team_board'
    assert STORY_REJECTED_DATE_MISMATCH in preview['authority']['description']
    assert 'August 8' not in preview['og_description']


def test_a_story_for_another_team_is_refused():
    other = {'team_id': 111, 'team_name': 'Boston Red Sox', 'team_abbreviation': 'BOS'}
    preview = _preview(story=_story(team=other))
    assert preview['source'] == 'trusted_team_board'
    assert STORY_REJECTED_TEAM_MISMATCH in preview['authority']['description']


def test_a_story_may_not_introduce_a_state_the_board_did_not_publish():
    preview = _preview(
        story=_story(share_summary='The Yankees bullpen is Fresh tonight.'),
        board=_board(state_available=False),
    )
    assert preview['source'] == 'trusted_team_board'
    assert STORY_REJECTED_STATE_CONFLICT in preview['authority']['description']


# ── metadata and body project one claim ────────────────────────────────────

CLAIM_CASES = (
    ('agreeing story', dict(story=_story(), board=_board())),
    (
        'conflicting state',
        dict(
            story=_story(share_title='Yankees bullpen: Fresh', share_summary='Fresh and rested.'),
            board=_board(state='Vulnerable', unavailable=5),
        ),
    ),
    ('date mismatch', dict(story=_story(date='2026-08-08'), board=_board())),
    ('no story', dict(board=_board())),
    ('no team state', dict(board=_board(state_available=False))),
)


@pytest.mark.parametrize('label,kwargs', CLAIM_CASES)
def test_metadata_and_body_never_state_different_team_states(label, kwargs):
    preview = _preview(**kwargs)
    body = _body_text(render_team_story_html(preview))
    state = preview['team_state_label']
    for other in ('Fresh', 'Stretched', 'Vulnerable'):
        if other == state:
            continue
        assert other not in preview['og_description'], (label, other)
        assert other not in preview['og_title'], (label, other)
        assert f'Team State: {other}' not in body, (label, other)


@pytest.mark.parametrize('label,kwargs', CLAIM_CASES)
def test_the_page_carries_one_receipt_everywhere(label, kwargs):
    preview = _preview(**kwargs)
    html_text = render_team_story_html(preview)
    assert preview['snapshot_id'] == SNAPSHOT
    assert f'content="{SNAPSHOT}"' in html_text
    assert preview['data_through'] == DATA_THROUGH
    assert f'content="{DATA_THROUGH}"' in html_text
    assert DATA_THROUGH in _body_text(html_text)


@pytest.mark.parametrize('label,kwargs', CLAIM_CASES)
def test_team_identity_agrees_across_projections(label, kwargs):
    preview = _preview(**kwargs)
    body = _body_text(render_team_story_html(preview))
    assert preview['team_abbreviation'] == 'NYY'
    assert 'New York Yankees' in body


# ── lifecycle matrix ───────────────────────────────────────────────────────

LIFECYCLE = (
    ('current', dict(board=_board()), REPRESENTATION_DATED_READ, None),
    (
        'limited read',
        dict(board=_board(state_available=False)),
        REPRESENTATION_DATED_READ,
        None,
    ),
    (
        'missing publication',
        dict(board=_board(publication=False)),
        REPRESENTATION_WITHHELD,
        WITHHELD_NO_TRUSTED_PUBLICATION,
    ),
    (
        'no data through',
        dict(board=_board(data_through=None)),
        REPRESENTATION_WITHHELD,
        WITHHELD_NO_DATA_THROUGH,
    ),
    (
        'snapshot mismatch',
        dict(board=_board(snapshot_id='9999'), expected_snapshot_id=SNAPSHOT),
        REPRESENTATION_WITHHELD,
        WITHHELD_AUTHORITY_MISMATCH,
    ),
)


@pytest.mark.parametrize('label,kwargs,representation,withheld', LIFECYCLE)
def test_lifecycle_representation_and_withheld_reason(label, kwargs, representation, withheld):
    preview = _preview(story=_story(), **kwargs)
    assert preview['representation'] == representation, label
    assert preview['withheld_reason'] == withheld, label


@pytest.mark.parametrize('label,kwargs,representation,withheld', LIFECYCLE)
def test_a_withheld_page_makes_no_present_tense_bullpen_claim(
    label, kwargs, representation, withheld
):
    preview = _preview(story=_story(), **kwargs)
    if representation != REPRESENTATION_WITHHELD:
        return
    body = _body_text(render_team_story_html(preview))
    assert preview['team_state_label'] is None, label
    assert preview['data_through'] is None, label
    assert preview['snapshot_id'] is None, label
    for state in ('Fresh', 'Stretched', 'Vulnerable'):
        assert state not in preview['og_description'], (label, state)
        assert f'Team State: {state}' not in body, (label, state)
    # Identity and the live handoff survive a withheld claim.
    assert 'New York Yankees' in body
    assert 'bullpen board' in body


def test_a_withheld_page_never_inherits_story_wording():
    """A story cannot supply a claim the board refused to publish."""
    preview = _preview(
        story=_story(share_summary='The Yankees bullpen is Fresh and rested.'),
        board=_board(publication=False),
    )
    assert preview['representation'] == REPRESENTATION_WITHHELD
    assert 'Fresh' not in preview['og_description']
    assert preview['source'] != 'canonical_story'


# ── the disagreement helper, directly ──────────────────────────────────────

def test_disagreement_helper_returns_none_when_the_story_agrees():
    assert story_claim_disagreement(
        _story(), abbr='NYY', team_id=147, state_label='Stretched', data_through=DATA_THROUGH
    ) is None


def test_disagreement_helper_ignores_a_missing_story():
    assert story_claim_disagreement(
        None, abbr='NYY', team_id=147, state_label='Stretched', data_through=DATA_THROUGH
    ) is None


def test_disagreement_reasons_are_reported_in_a_fixed_order():
    """Team identity is checked before date, and date before state."""
    other = {'team_id': 111, 'team_name': 'Boston Red Sox', 'team_abbreviation': 'BOS'}
    story = _story(team=other, date='2026-08-01', share_summary='Fresh bullpen.')
    assert story_claim_disagreement(
        story, abbr='NYY', team_id=147, state_label='Stretched', data_through=DATA_THROUGH
    ) == STORY_REJECTED_TEAM_MISMATCH


def test_a_team_state_word_inside_ordinary_prose_still_counts():
    """The catalogue is matched on word boundaries, so this is not a substring."""
    story = _story(share_summary='Refreshed arms are back.')
    assert story_claim_disagreement(
        story, abbr='NYY', team_id=147, state_label='Stretched', data_through=DATA_THROUGH
    ) is None


# ── determinism ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('label,kwargs', CLAIM_CASES)
def test_the_same_publication_yields_a_byte_identical_claim(label, kwargs):
    renders = [render_team_story_html(_preview(**kwargs)) for _ in range(3)]
    assert renders[0] == renders[1] == renders[2], label


def test_generated_at_moves_without_changing_the_baseball_claim():
    first = build_team_story_preview(
        TEAM, story=_story(), board=_board(), generated_at='2026-08-13T15:00:00+00:00'
    )
    second = build_team_story_preview(
        TEAM, story=_story(), board=_board(), generated_at='2026-08-14T09:30:00+00:00'
    )
    assert first['generated_at'] != second['generated_at']
    for field in (
        'team_state_label',
        'baseball_point',
        'data_through',
        'snapshot_id',
        'sync_run_id',
        'authority_contract',
        'og_title',
        'og_description',
    ):
        assert first[field] == second[field], field


# ── the artifact satisfies the delivery gate ───────────────────────────────
#
# The checks above prove the SERVICE cannot build two claims. These prove the
# bytes it ships carry that guarantee out to CI, where the fail-closed delivery
# gate re-derives it from the artifact alone.

@pytest.mark.parametrize('label,kwargs', CLAIM_CASES)
def test_the_rendered_page_passes_the_delivery_gates_claim_check(label, kwargs):
    from scripts.verify_generated_team_previews import (
        _claim_violations,
        _read_authority_meta,
    )

    text = render_team_story_html(_preview(**kwargs))
    meta = _read_authority_meta(text)
    assert _claim_violations(f'team/NYY/index.html ({label})', meta, text) == []


@pytest.mark.parametrize('label,kwargs', CLAIM_CASES)
def test_the_rendered_page_declares_the_state_it_publishes(label, kwargs):
    from scripts.verify_generated_team_previews import _read_authority_meta

    preview = _preview(**kwargs)
    meta = _read_authority_meta(render_team_story_html(preview))
    assert meta.get('team-state') == (preview['team_state_label'] or None), label
    # A page may word its unfurl without naming a state; it may never name one
    # the page does not publish.
    if meta.get('unfurl-team-state'):
        assert meta['unfurl-team-state'] == preview['team_state_label'], label


def test_a_contradicting_page_would_be_refused_by_the_delivery_gate():
    """Proof the gate has teeth: hand-corrupt one projection and it fails closed."""
    from scripts.verify_generated_team_previews import (
        _claim_violations,
        _read_authority_meta,
    )

    text = render_team_story_html(_preview(board=_board(state='Vulnerable')))
    corrupted = text.replace(
        '<p data-baseballos-team-state="Vulnerable">BaseballOS Team State: Vulnerable.</p>',
        '<p data-baseballos-team-state="Fresh">BaseballOS Team State: Fresh.</p>',
    )
    assert corrupted != text
    assert _claim_violations('team/NYY/index.html', _read_authority_meta(corrupted), corrupted)


# ── 30-team corpus ─────────────────────────────────────────────────────────
#
# Honest limitation: this is a synthesized league, not a production run. It
# cannot prove what the real feed contained on any date, and no production
# workflow was run to manufacture one. What it does prove is coverage across the
# combinations a real league produces in one publication -- every Team State,
# limited reads, agreeing stories, contradicting stories, stale-dated stories,
# cross-team stories, and teams with no story at all -- rather than exercising
# one happy path thirty times.

MLB_ABBRS = (
    'ARI', 'ATL', 'BAL', 'BOS', 'CHC', 'CIN', 'CLE', 'COL', 'CWS', 'DET',
    'HOU', 'KC', 'LAA', 'LAD', 'MIA', 'MIL', 'MIN', 'NYM', 'NYY', 'OAK',
    'PHI', 'PIT', 'SD', 'SEA', 'SF', 'STL', 'TB', 'TEX', 'TOR', 'WSH',
)
CORPUS_STATES = ('Fresh', 'Stretched', 'Vulnerable')


def _corpus():
    """One publication over 30 teams, cycling through the real variation."""
    teams, boards, stories = [], [], []
    for index, abbr in enumerate(MLB_ABBRS):
        team = {'team_id': 100 + index, 'team_name': f'{abbr} Club', 'team_abbreviation': abbr}
        teams.append(team)

        board = _board(state=CORPUS_STATES[index % 3], unavailable=index % 6)
        board['team'] = team
        if index % 10 == 7:  # a few teams carry no publishable Team State
            board['team_state'] = {
                'available': False,
                'unavailable_message': 'No current Team State read.',
            }
        boards.append(board)

        kind = index % 5
        if kind == 0:
            continue  # no story for this team
        if kind == 1:
            story = _story(team=team)
        elif kind == 2:  # story naming a state the board did not publish
            wrong = CORPUS_STATES[(index + 1) % 3]
            story = _story(
                team=team,
                share_title=f'{abbr} bullpen: {wrong}',
                share_summary=f'The {abbr} bullpen is {wrong} tonight.',
            )
        elif kind == 3:  # story representing an earlier date
            story = _story(team=team, date='2026-08-08')
        else:  # a story carrying another club's identity
            story = _story(team=team)
            story['team_abbreviation'] = 'ZZZ'
        story['story_id'] = f'{abbr}:{DATA_THROUGH}'
        stories.append(story)

    payload = {'stories': {'items': stories}}
    return teams, payload, boards


def test_no_team_in_a_thirty_team_publication_carries_two_claims():
    from services.team_story_previews import build_team_story_previews
    from scripts.verify_generated_team_previews import (
        _claim_violations,
        _read_authority_meta,
    )

    teams, payload, boards = _corpus()
    previews = build_team_story_previews(
        teams,
        dashboard_payload=payload,
        boards=boards,
        generated_at=GENERATED_AT,
        expected_snapshot_id=SNAPSHOT,
    )
    assert len(previews) == 30

    for preview in previews:
        abbr = preview['team_abbreviation']
        text = render_team_story_html(preview)
        meta = _read_authority_meta(text)
        assert _claim_violations(f'team/{abbr}/index.html', meta, text) == [], abbr

        state = preview['team_state_label']
        for other in CORPUS_STATES:
            if other == state:
                continue
            assert other not in preview['og_title'], (abbr, other)
            assert other not in preview['og_description'], (abbr, other)
            assert f'Team State: {other}' not in _body_text(text), (abbr, other)


def test_the_corpus_actually_exercises_both_outcomes():
    """A corpus that never rejects a story would prove nothing."""
    from services.team_story_previews import build_team_story_previews

    teams, payload, boards = _corpus()
    previews = build_team_story_previews(
        teams,
        dashboard_payload=payload,
        boards=boards,
        generated_at=GENERATED_AT,
        expected_snapshot_id=SNAPSHOT,
    )
    sources = [preview['source'] for preview in previews]
    assert sources.count('canonical_story') >= 5, sources
    rejected = [
        preview['team_abbreviation']
        for preview in previews
        if any(
            reason in preview['authority']['description']
            for reason in (
                STORY_REJECTED_STATE_CONFLICT,
                STORY_REJECTED_DATE_MISMATCH,
                STORY_REJECTED_TEAM_MISMATCH,
            )
        )
    ]
    assert len(rejected) >= 10, rejected
    assert len({preview['team_state_label'] for preview in previews}) >= 3


def test_a_thirty_team_publication_is_byte_identical_across_repeats():
    from services.team_story_previews import build_team_story_previews

    def render_all():
        teams, payload, boards = _corpus()
        return [
            render_team_story_html(preview)
            for preview in build_team_story_previews(
                teams,
                dashboard_payload=payload,
                boards=boards,
                generated_at=GENERATED_AT,
                expected_snapshot_id=SNAPSHOT,
            )
        ]

    runs = [render_all() for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
