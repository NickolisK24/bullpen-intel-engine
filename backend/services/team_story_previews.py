"""Static per-team preview pages for shareable bullpen links.

``/team/{ABBR}`` is a REGENERATING DISTRIBUTION ENTRY PAGE. It is not an
immutable historical share artifact, it is not a second copy of the Team Board,
and it never becomes current truth — it cites current truth and hands the reader
to it.

What a reader actually consumes here is the social unfurl: the title and the
description. Before DIST-003 (#594) that unfurl said "Tonight's board" with no
date, in a vocabulary that belongs to no canonical catalogue, built partly from
a published snapshot and partly from live mutable tables. A link shared on
Sunday still read as a present-tense claim on Thursday.

So every claim-bearing representation this module builds now carries, from ONE
trusted publication:

* canonical public Team State (``Fresh`` / ``Stretched`` / ``Vulnerable``) or the
  governed non-state message — never a derived or adjective-shaped substitute;
* one concrete backend-authored baseball point;
* the baseball ``data_through`` date the claim describes;
* the time the representation was generated;
* the trusted snapshot receipt it was generated from;
* the link to the current Team Board.

``data_through``, ``generated_at``, ``published_at`` and ``snapshot_generated_at``
are four different facts and stay four different fields. A page generated on
August 9 legitimately describes baseball data through August 8; that is correct,
and it is only correct because the page says both.

Fail closed: with no trusted publication, or no provable ``data_through``, or a
board that resolved from a different snapshot than the story feed, this module
WITHHOLDS the claim rather than dating a guess. A withheld page keeps team
identity and the live handoff and says plainly that it has no dated read.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from services.bullpen_board import METHODOLOGY_REASON
from services.public_bullpen_copy import guard_public_prose
from services.team_state_public_vocabulary import PUBLIC_TEAM_STATE_LABEL_SET


DEFAULT_SITE_URL = 'https://baseballos.app'
DEFAULT_OG_IMAGE_PATH = '/og/baseballos-card.svg'
TEAM_PAGE_ROOT = '/team'
TEAM_SHARE_SOURCE = 'share'
TWITTER_CARD = 'summary'

# Canonical story tones that warrant a tension framing on the share card.
TENSION_TONES = {'stress', 'watch'}

# What this generated page is. The static scan and the frontend contract test key
# off it: a dated read must carry a data-through date and a snapshot receipt, and
# a withheld page must carry neither and must make no present-tense team claim.
REPRESENTATION_DATED_READ = 'dated_team_read'
REPRESENTATION_WITHHELD = 'withheld'

# Why a claim was withheld. Each one is a real fail-closed outcome, not an error.
WITHHELD_NO_TRUSTED_PUBLICATION = 'no_trusted_publication'
WITHHELD_NO_DATA_THROUGH = 'no_data_through'
WITHHELD_AUTHORITY_MISMATCH = 'publication_authority_mismatch'

# The governed non-state message a board publishes when Team State is
# unavailable is preferred; this is the floor when even that is missing.
NON_STATE_FALLBACK_MESSAGE = (
    'A current Team State read is not available for this bullpen.'
)

# The board's own governed limited-read label. A limited read is a real outcome
# and is stated, never dropped.
LIMITED_READ_LABEL = 'Limited Read'
LIMITED_READ_NOTE = 'Supporting bullpen reads are limited for this team.'

# Withheld copy. It describes the state of the REPRESENTATION, never the bullpen,
# so it is not a present-tense team claim.
WITHHELD_DESCRIPTION = (
    'A dated BaseballOS bullpen read is not published for this team right now. '
    'Open the team board for the current read.'
)


def _clean_text(value):
    return value.strip() if isinstance(value, str) else ''


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _strip_trailing_slash(value):
    return str(value or '').rstrip('/')


def _absolute_url(path, site_url=DEFAULT_SITE_URL):
    if not path:
        return ''
    if str(path).startswith(('http://', 'https://')):
        return str(path)
    return f'{_strip_trailing_slash(site_url)}{path if str(path).startswith("/") else f"/{path}"}'


def _team_abbreviation(team=None, story=None, board=None):
    candidates = [
        (team or {}).get('team_abbreviation'),
        (story or {}).get('team_abbreviation'),
        ((board or {}).get('team') or {}).get('team_abbreviation'),
    ]
    for candidate in candidates:
        text = _clean_text(candidate).upper()
        if text:
            return re.sub(r'[^A-Z0-9-]', '', text)
    return None


def _team_name(team=None, story=None, board=None):
    candidates = [
        (team or {}).get('team_name'),
        (story or {}).get('team_name'),
        ((board or {}).get('team') or {}).get('team_name'),
        _team_abbreviation(team=team, story=story, board=board),
    ]
    for candidate in candidates:
        text = _clean_text(candidate)
        if text:
            return text
    return 'This team'


def _story_key(story):
    if not isinstance(story, dict):
        return None
    if story.get('team_id') is not None:
        return str(story.get('team_id'))
    abbr = _clean_text(story.get('team_abbreviation')).upper()
    return abbr or None


def _board_key(board):
    team = (board or {}).get('team') or {}
    if team.get('team_id') is not None:
        return str(team.get('team_id'))
    abbr = _clean_text(team.get('team_abbreviation')).upper()
    return abbr or None


def _team_key(team):
    if not isinstance(team, dict):
        return None
    if team.get('team_id') is not None:
        return str(team.get('team_id'))
    abbr = _clean_text(team.get('team_abbreviation')).upper()
    return abbr or None


def _shape_reads(board):
    shape = (board or {}).get('team_shape') or {}
    reads = shape.get('reads')
    if isinstance(reads, list):
        return [read for read in reads if isinstance(read, dict)]
    return []


# ---------------------------------------------------------------------------
# Publication authority, Team State, and the baseball point.
#
# All three come from the trusted published board payload. Nothing here derives
# a state, a date, or a claim from counts, percentages, shape labels, or wall
# clock time.
# ---------------------------------------------------------------------------


def _identifier(value):
    if value is None:
        return None
    text = _clean_text(str(value))
    return text or None


def publication_receipt(board):
    """The trusted publication a board resolved from, as flat public fields.

    ``publication_authority`` is what ``build_published_team_board`` stamps onto
    a board it served from a trusted dashboard snapshot. ``freshness`` is only
    ever a source for ``data_through`` here — never for the snapshot identity,
    because a board with freshness but no publication authority did not come from
    a trusted publication and must not be presented as though it did.
    """
    board = board if isinstance(board, dict) else {}
    authority = board.get('publication_authority')
    authority = authority if isinstance(authority, dict) else {}
    freshness = board.get('freshness')
    freshness = freshness if isinstance(freshness, dict) else {}

    return {
        'contract': _identifier(authority.get('contract')),
        'authority_type': _identifier(authority.get('authority_type')),
        'snapshot_id': _identifier(authority.get('snapshot_id')),
        'sync_run_id': _identifier(authority.get('sync_run_id')),
        # The baseball date the claim describes.
        'data_through': (
            _identifier(authority.get('data_through'))
            or _identifier(freshness.get('data_through'))
        ),
        # The product-day availability evaluation date. NOT the baseball date.
        'availability_reference_date': _identifier(
            authority.get('availability_reference_date')
        ),
        # When the trusted snapshot was constructed. NOT the baseball date.
        'snapshot_generated_at': _identifier(authority.get('snapshot_generated_at')),
        # When the trusted snapshot was published. NOT the baseball date.
        'published_at': _identifier(authority.get('published_at')),
        'served_from': _identifier(board.get('served_from')),
    }


def _team_state_read(board):
    """``(label, non_state_message)`` from the board's governed Team State block.

    Fails closed: a block that is not marked available, or that carries a label
    outside the canonical public catalogue, yields no label. This module never
    maps, derives, or substitutes a Team State.
    """
    block = (board or {}).get('team_state')
    block = block if isinstance(block, dict) else {}
    label = _clean_text(block.get('public_label'))
    if block.get('available') is True and label in PUBLIC_TEAM_STATE_LABEL_SET:
        return label, None
    message = _clean_text(block.get('unavailable_message')) or NON_STATE_FALLBACK_MESSAGE
    return None, message


# The board publishes its governed reasons in a fixed order whose first entry
# is always the available-count sentence. Taking that first entry gave three
# clubs in three different Team States the same preview sentence, because an
# identical available count says nothing about why the states differ -- and that
# sentence is also the one that carries provenance ("from the latest completed
# workload data") inside a baseball claim.
#
# So the preview SELECTS among the reasons the board already authored, most
# state-discriminating first. Nothing is composed here, no count is recomputed,
# and no new metric was added: the ranking reads the canonical public
# availability labels that are already in the published sentences.
_DISCRIMINATING_STATUS_TOKENS = ('Unavailable', 'On Watch')


def _reason_rank(text):
    """Lower sorts first. Ranks a governed reason by how much it explains."""
    if 'Unavailable' in text and not text.lower().startswith('no relievers'):
        return 0                      # a non-zero constraint: the strongest why
    if 'On Watch' in text:
        return 1                      # partial constraint
    if 'Unavailable' in text:
        return 2                      # "No relievers are marked Unavailable."
    return 3                          # the generic available-count sentence


def _baseball_point(board):
    """The most state-discriminating baseball sentence the board authored.

    Preference is by explanatory strength rather than the board's publication
    order: a stated constraint (Unavailable, then On Watch) explains a Team
    State; a bare available count does not, and repeats across clubs whose
    states differ. Falls back to the governed health label, then to an honest
    limited-read note. Nothing is composed from counts here.
    """
    context = (board or {}).get('context')
    context = context if isinstance(context, dict) else {}
    health = context.get('health')
    health = health if isinstance(health, dict) else {}

    candidates = []
    for index, reason in enumerate(health.get('reasons') or []):
        text = _clean_text(reason)
        # The methodology line is a standing disclosure, not evidence about
        # this club, so it never becomes the preview's baseball point.
        if text and text != METHODOLOGY_REASON:
            candidates.append((_reason_rank(text), index, text))
    if candidates:
        # Sorting on (rank, original index) keeps selection fully deterministic:
        # equal-rank reasons resolve to the board's own published order.
        return sorted(candidates)[0][2]

    label = _clean_text(health.get('label'))
    if label:
        return label

    for read in _shape_reads(board):
        if _clean_text(read.get('label')) == LIMITED_READ_LABEL:
            return LIMITED_READ_NOTE
    return None


def data_through_sentence(data_through):
    return f'Data through {data_through}.'


# ---------------------------------------------------------------------------
# One claim per page (H-8).
#
# The published Team Board owns this page's claim. Every receipt field
# (snapshot, sync run, data_through, published_at, authority contract), the
# Team State and the baseball point all come from it, and the page exists to
# hand the reader to that board.
#
# A canonical story may supply the SOCIAL WORDING (DIST-003 / #594) but it is a
# different evidence family -- a completed-game narrative -- and it must not
# become a second author of the claim. It used to be able to: the metadata was
# selected from the story while the body was rendered from the board, under one
# shared snapshot id and with nothing comparing them. That published pages whose
# unfurl said "Fresh with seven close-game options available" above a body
# reading "BaseballOS Team State: Vulnerable. 5 relievers are Unavailable.", and
# pages whose summary described one date while the stamp carried another.
#
# So story wording is now checked against the claim before it is used. The
# checks are structural: identity fields compared directly, and Team State
# compared against the canonical three-label catalogue rather than by reading
# arbitrary English.
# ---------------------------------------------------------------------------

# Why a canonical story was refused as the source of this page's wording. Each
# is a real disagreement with the claim, not an error.
STORY_REJECTED_TEAM_MISMATCH = 'story_team_mismatch'
STORY_REJECTED_DATE_MISMATCH = 'story_represented_date_mismatch'
STORY_REJECTED_STATE_CONFLICT = 'story_team_state_conflict'


def _story_states_a_team_state(text):
    """The canonical Team State labels named in ``text``, as a set.

    Word-boundary matched against the canonical public catalogue only. This is
    a closed three-label vocabulary, not an attempt to parse the sentence.
    """
    found = set()
    for label in PUBLIC_TEAM_STATE_LABEL_SET:
        if re.search(rf'\b{re.escape(label)}\b', text or ''):
            found.add(label)
    return found


def _sole_state_named(text):
    """The single Team State ``text`` names, or ``None`` if it names 0 or 2+."""
    named = _story_states_a_team_state(text)
    return next(iter(named)) if len(named) == 1 else None


def story_claim_disagreement(story, *, abbr, team_id, state_label, data_through):
    """Why this story may not word the page's claim, or ``None`` if it may.

    Checked in a fixed order so the reported reason is deterministic.
    """
    if not isinstance(story, dict):
        return None

    story_abbr = _clean_text(story.get('team_abbreviation')).upper()
    story_team_id = story.get('team_id')
    if (story_abbr and abbr and story_abbr != abbr) or (
        story_team_id is not None and team_id is not None and story_team_id != team_id
    ):
        return STORY_REJECTED_TEAM_MISMATCH

    # The page stamps the board's data_through under the story's prose. A story
    # representing another date would date someone else's sentence.
    story_date = _clean_text(story.get('date'))
    if story_date and data_through and story_date != data_through:
        return STORY_REJECTED_DATE_MISMATCH

    # A story that names a Team State must name this page's Team State. When the
    # board publishes no state, a story may not introduce one.
    named = _story_states_a_team_state(
        f'{_clean_text(story.get("share_title"))} {_clean_text(story.get("share_summary"))}'
    )
    if named and named != ({state_label} if state_label else set()):
        return STORY_REJECTED_STATE_CONFLICT

    return None


def _story_title(story):
    """Share-card title: the canonical share title, falling back to the headline."""
    for key in ('share_title', 'headline'):
        text = _clean_text((story or {}).get(key))
        if text:
            return text
    return ''


def _story_description(story):
    """Share-card description: the canonical share summary, falling back to the headline."""
    for key in ('share_summary', 'headline'):
        text = _clean_text((story or {}).get(key))
        if text:
            return text
    return ''


def _story_framing(story):
    return 'tension' if (story or {}).get('tone') in TENSION_TONES else 'clean'


def _join_sentences(*parts):
    return ' '.join(part for part in parts if part)


def build_story_index(dashboard_payload):
    # Canonical story feed (dashboard.stories). Only publishable stories carry
    # share-ready copy; suppressed entries fall through to the neutral board read.
    feed = (dashboard_payload or {}).get('stories') or {}
    stories = feed.get('items') or []
    return {
        _story_key(story): story
        for story in stories
        if isinstance(story, dict) and story.get('story_available') is True and _story_key(story)
    }


def build_board_index(boards):
    return {
        _board_key(board): board
        for board in boards or []
        if _board_key(board)
    }


def _withheld_preview(
    *,
    team,
    story,
    board,
    abbr,
    team_name,
    reason,
    generated_at,
    team_page_url,
    redirect_path,
    og_image,
):
    """A page that keeps identity and the live handoff and makes no team claim."""
    return {
        'team_id': (
            (team or {}).get('team_id')
            or ((board or {}).get('team') or {}).get('team_id')
            or (story or {}).get('team_id')
        ),
        'team_abbreviation': abbr,
        'team_name': team_name,
        'representation': REPRESENTATION_WITHHELD,
        'withheld_reason': reason,
        'has_story': False,
        'framing': 'withheld',
        'source': 'withheld',
        'story_id': None,
        'story_type': None,
        'category': None,
        'tone': None,
        'team_state_label': None,
        'unfurl_team_state': None,
        'non_state_message': None,
        'baseball_point': None,
        'data_through': None,
        'generated_at': generated_at,
        'published_at': None,
        'snapshot_generated_at': None,
        'availability_reference_date': None,
        'snapshot_id': None,
        'sync_run_id': None,
        'authority_contract': None,
        'authority_type': None,
        'og_title': f'{team_name} Bullpen — BaseballOS',
        'og_description': WITHHELD_DESCRIPTION,
        'og_url': team_page_url,
        'canonical_url': team_page_url,
        'og_image': og_image,
        'twitter_card': TWITTER_CARD,
        'redirect_path': redirect_path,
        'authority': {
            'title': 'team_identity',
            'description': 'withheld_no_trusted_claim',
            'redirect': 'tonights_bullpen_board.deep_link',
            'publication': None,
        },
    }


def build_team_story_preview(
    team,
    *,
    story=None,
    board=None,
    generated_at=None,
    expected_snapshot_id=None,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    """Build one team's preview from a single trusted publication.

    ``expected_snapshot_id`` is the snapshot the story feed came from. A board
    that resolved from a different snapshot cannot be combined with that story on
    one page, so the claim is withheld rather than published with two clocks.
    """
    abbr = _team_abbreviation(team=team, story=story, board=board)
    if not abbr:
        raise ValueError('Team preview requires a team abbreviation.')

    team_name = _team_name(team=team, story=story, board=board)
    team_page_path = f'{TEAM_PAGE_ROOT}/{quote(abbr)}'
    team_page_url = _absolute_url(team_page_path, site_url=site_url)
    redirect_path = f'/bullpen?view=board&team={quote(abbr)}&source={TEAM_SHARE_SOURCE}'
    og_image = _absolute_url(og_image_path, site_url=site_url)
    generated_at = _clean_text(generated_at) or _utc_now_iso()

    receipt = publication_receipt(board)
    withheld_reason = None
    if not receipt['snapshot_id']:
        withheld_reason = WITHHELD_NO_TRUSTED_PUBLICATION
    elif not receipt['data_through']:
        withheld_reason = WITHHELD_NO_DATA_THROUGH
    elif (
        expected_snapshot_id is not None
        and receipt['snapshot_id'] != _identifier(expected_snapshot_id)
    ):
        withheld_reason = WITHHELD_AUTHORITY_MISMATCH

    if withheld_reason is not None:
        return _withheld_preview(
            team=team,
            story=story,
            board=board,
            abbr=abbr,
            team_name=team_name,
            reason=withheld_reason,
            generated_at=generated_at,
            team_page_url=team_page_url,
            redirect_path=redirect_path,
            og_image=og_image,
        )

    data_through = receipt['data_through']
    dated_clause = data_through_sentence(data_through)
    state_label, non_state_message = _team_state_read(board)
    baseball_point = _baseball_point(board)

    # The board's claim is settled above. A canonical story may word it only if
    # it agrees with it; otherwise the page falls back to the board's own
    # wording, so both projections still describe one claim.
    story_disagreement = story_claim_disagreement(
        story,
        abbr=abbr,
        team_id=(team or {}).get('team_id') or ((board or {}).get('team') or {}).get('team_id'),
        state_label=state_label,
        data_through=data_through,
    )
    if story_disagreement is not None:
        story = None

    if story:
        title = _story_title(story)
        if not title:
            raise ValueError(f'Canonical story for {abbr} is missing a share title.')
        summary = _story_description(story)
        if not summary:
            raise ValueError(f'Canonical story for {abbr} is missing a share summary.')
        # The canonical story sentence is published as written. #594 anchors it
        # in time; it does not rewrite a word of it.
        description = _join_sentences(summary, dated_clause)
        title_authority = 'canonical_story.share_title'
        description_authority = 'canonical_story.share_summary+data_through'
        source = 'canonical_story'
        framing = _story_framing(story)
    else:
        title = (
            f'{team_name} Bullpen: {state_label}'
            if state_label
            else f'{team_name} Bullpen Read'
        )
        state_sentence = (
            f'{team_name} bullpen state: {state_label}.'
            if state_label
            else non_state_message
        )
        description = guard_public_prose(
            'team_preview.description',
            _join_sentences(state_sentence, baseball_point, dated_clause),
        )
        title_authority = (
            'team_state.public_label' if state_label else 'team_state.non_state'
        )
        description_authority = 'team_state+context.health+data_through'
        source = 'trusted_team_board'
        framing = 'neutral'
        if story_disagreement is not None:
            # Visible and machine-readable: the page says which claim it is
            # publishing and why the story's wording was refused.
            title_authority = f'{title_authority}+{story_disagreement}'
            description_authority = f'{description_authority}+{story_disagreement}'

    return {
        'team_id': (team or {}).get('team_id') or ((board or {}).get('team') or {}).get('team_id'),
        'team_abbreviation': abbr,
        'team_name': team_name,
        'representation': REPRESENTATION_DATED_READ,
        'withheld_reason': None,
        'has_story': bool(story),
        'framing': framing,
        'source': source,
        'story_id': (story or {}).get('story_id'),
        'story_type': (story or {}).get('story_type'),
        'category': (story or {}).get('category'),
        'tone': (story or {}).get('tone'),
        'team_state_label': state_label,
        # Which Team State the unfurl copy itself names, if any. Canonical story
        # wording may legitimately name none; what it may never do is name a
        # different one, and this makes that checkable on the artifact.
        'unfurl_team_state': _sole_state_named(f'{title} {description}'),
        'non_state_message': None if state_label else non_state_message,
        'baseball_point': baseball_point,
        # Four separate temporal facts. They are never collapsed into each other.
        'data_through': data_through,
        'generated_at': generated_at,
        'published_at': receipt['published_at'],
        'snapshot_generated_at': receipt['snapshot_generated_at'],
        'availability_reference_date': receipt['availability_reference_date'],
        'snapshot_id': receipt['snapshot_id'],
        'sync_run_id': receipt['sync_run_id'],
        'authority_contract': receipt['contract'],
        'authority_type': receipt['authority_type'],
        'og_title': title,
        'og_description': description,
        'og_url': team_page_url,
        'canonical_url': team_page_url,
        'og_image': og_image,
        'twitter_card': TWITTER_CARD,
        'redirect_path': redirect_path,
        'authority': {
            'title': title_authority,
            'description': description_authority,
            'redirect': 'tonights_bullpen_board.deep_link',
            'publication': receipt['contract'] or receipt['served_from'],
        },
    }


def build_team_story_previews(
    teams,
    *,
    dashboard_payload,
    boards,
    generated_at=None,
    expected_snapshot_id=None,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    story_index = build_story_index(dashboard_payload)
    board_index = build_board_index(boards)
    generated_at = _clean_text(generated_at) or _utc_now_iso()
    previews = []
    for team in sorted(
        (teams or []),
        key=lambda item: (_clean_text(item.get('team_abbreviation')).upper(), item.get('team_id') or 0),
    ):
        key = _team_key(team)
        story = story_index.get(key)
        board = board_index.get(key)
        previews.append(
            build_team_story_preview(
                team,
                story=story,
                board=board,
                generated_at=generated_at,
                expected_snapshot_id=expected_snapshot_id,
                site_url=site_url,
                og_image_path=og_image_path,
            )
        )
    return previews


# ---------------------------------------------------------------------------
# Rendering.
# ---------------------------------------------------------------------------


def _meta_property(name, content):
    return f'    <meta property="{html.escape(name)}" content="{html.escape(str(content), quote=True)}" />'


def _meta_name(name, content):
    return f'    <meta name="{html.escape(name)}" content="{html.escape(str(content), quote=True)}" />'


def _authority_meta(preview):
    """Machine-separable publication metadata, one concept per tag.

    ``published-at`` is emitted only when it is a distinct fact from
    ``generated-at``; collapsing the two would be the exact conflation #594
    exists to prevent.
    """
    lines = [
        _meta_name('baseballos:representation', preview.get('representation') or REPRESENTATION_WITHHELD),
    ]
    if preview.get('withheld_reason'):
        lines.append(_meta_name('baseballos:withheld-reason', preview['withheld_reason']))
    if preview.get('generated_at'):
        lines.append(_meta_name('baseballos:generated-at', preview['generated_at']))
    if preview.get('data_through'):
        lines.append(_meta_name('baseballos:data-through', preview['data_through']))
    if preview.get('snapshot_id'):
        lines.append(_meta_name('baseballos:snapshot-id', preview['snapshot_id']))
    if preview.get('sync_run_id'):
        lines.append(_meta_name('baseballos:sync-run-id', preview['sync_run_id']))
    if preview.get('authority_contract'):
        lines.append(_meta_name('baseballos:authority-contract', preview['authority_contract']))
    if preview.get('team_state_label'):
        # The one Team State this page publishes. Both the unfurl copy and the
        # crawler-visible body are projections of this value, so a delivery gate
        # can prove they agree without re-deriving any baseball meaning.
        lines.append(_meta_name('baseballos:team-state', preview['team_state_label']))
    if preview.get('unfurl_team_state'):
        lines.append(_meta_name('baseballos:unfurl-team-state', preview['unfurl_team_state']))
    published_at = preview.get('published_at')
    if published_at and published_at != preview.get('generated_at'):
        lines.append(_meta_name('baseballos:published-at', published_at))
    if preview.get('story_id'):
        lines.append(_meta_name('baseballos:story-id', preview['story_id']))
    return lines


def _body_lines(preview):
    """A small crawler-visible representation. Not a product surface.

    A crawler and a reader with scripting disabled both see the same claim the
    unfurl carries: who, what state, one baseball point, which baseball date,
    when it was generated, and where the current board is.
    """
    redirect_attr = html.escape(preview['redirect_path'], quote=True)
    team_name = preview.get('team_name') or 'This team'
    lines = ['    <main>', f'      <h1>{html.escape(team_name)} Bullpen</h1>']

    if preview.get('representation') == REPRESENTATION_DATED_READ:
        if preview.get('team_state_label'):
            state_attr = html.escape(preview['team_state_label'], quote=True)
            lines.append(
                f'      <p data-baseballos-team-state="{state_attr}">BaseballOS Team '
                f'State: {html.escape(preview["team_state_label"])}.</p>'
            )
        elif preview.get('non_state_message'):
            lines.append(f'      <p>{html.escape(preview["non_state_message"])}</p>')
        if preview.get('baseball_point'):
            lines.append(f'      <p>{html.escape(preview["baseball_point"])}</p>')
        data_through = html.escape(preview['data_through'], quote=True)
        lines.append(
            f'      <p>Baseball data through <time datetime="{data_through}">'
            f'{html.escape(preview["data_through"])}</time>.</p>'
        )
        generated_at = html.escape(preview['generated_at'], quote=True)
        lines.append(
            f'      <p>This page was generated <time datetime="{generated_at}">'
            f'{html.escape(preview["generated_at"])}</time> from BaseballOS '
            f'published snapshot {html.escape(preview["snapshot_id"])}.</p>'
        )
    else:
        lines.append(f'      <p>{html.escape(WITHHELD_DESCRIPTION)}</p>')

    lines.append(
        f'      <p><a href="{redirect_attr}">Open the current '
        f'{html.escape(team_name)} bullpen board</a></p>'
    )
    lines.append('    </main>')
    return lines


def render_team_story_html(preview):
    title = html.escape(preview['og_title'])
    redirect = preview['redirect_path']
    redirect_json = json.dumps(redirect)
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '  <head>',
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f'    <title>{title}</title>',
        _meta_name('description', preview['og_description']),
        _meta_property('og:type', 'website'),
        _meta_property('og:site_name', 'BaseballOS'),
        _meta_property('og:title', preview['og_title']),
        _meta_property('og:description', preview['og_description']),
        _meta_property('og:url', preview['og_url']),
        _meta_property('og:image', preview['og_image']),
        _meta_name('twitter:card', preview['twitter_card']),
        _meta_name('twitter:title', preview['og_title']),
        _meta_name('twitter:description', preview['og_description']),
        _meta_name('twitter:image', preview['og_image']),
        *_authority_meta(preview),
        f'    <link rel="canonical" href="{html.escape(preview["canonical_url"], quote=True)}" />',
        '  </head>',
        '  <body>',
        *_body_lines(preview),
        f'    <script>window.location.replace({redirect_json});</script>',
        '  </body>',
        '</html>',
        '',
    ]
    return '\n'.join(lines)


def render_invalid_team_html(site_url=DEFAULT_SITE_URL, og_image_path=DEFAULT_OG_IMAGE_PATH):
    fallback_url = _absolute_url(f'{TEAM_PAGE_ROOT}/', site_url=site_url)
    preview = {
        'og_title': 'BaseballOS | Team Story Preview',
        'og_description': 'Open BaseballOS for current bullpen availability and trust reads.',
        'og_url': fallback_url,
        'canonical_url': fallback_url,
        'og_image': _absolute_url(og_image_path, site_url=site_url),
        'twitter_card': TWITTER_CARD,
        'redirect_path': '/',
        # The fallback names no team and makes no team claim, so it is neither a
        # dated read nor a withheld one — it is the invalid-team page.
        'representation': 'invalid_team',
        'team_name': 'BaseballOS',
    }
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '  <head>',
        '    <meta charset="UTF-8" />',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f'    <title>{html.escape(preview["og_title"])}</title>',
        _meta_name('description', preview['og_description']),
        _meta_property('og:type', 'website'),
        _meta_property('og:site_name', 'BaseballOS'),
        _meta_property('og:title', preview['og_title']),
        _meta_property('og:description', preview['og_description']),
        _meta_property('og:url', preview['og_url']),
        _meta_property('og:image', preview['og_image']),
        _meta_name('twitter:card', preview['twitter_card']),
        _meta_name('twitter:title', preview['og_title']),
        _meta_name('twitter:description', preview['og_description']),
        _meta_name('twitter:image', preview['og_image']),
        _meta_name('baseballos:representation', preview['representation']),
        f'    <link rel="canonical" href="{html.escape(preview["canonical_url"], quote=True)}" />',
        '  </head>',
        '  <body>',
        '    <main>',
        '      <p>Open BaseballOS for current bullpen availability and trust reads.</p>',
        '      <p><a href="/">Go to BaseballOS</a></p>',
        '    </main>',
        f'    <script>window.location.replace({json.dumps(preview["redirect_path"])});</script>',
        '  </body>',
        '</html>',
        '',
    ]
    return '\n'.join(lines)


def write_team_story_pages(
    previews,
    output_root,
    *,
    site_url=DEFAULT_SITE_URL,
    og_image_path=DEFAULT_OG_IMAGE_PATH,
):
    root = Path(output_root)
    team_root = root / 'team'
    team_root.mkdir(parents=True, exist_ok=True)
    written = []
    withheld = []
    for preview in previews:
        abbr = preview['team_abbreviation']
        target_dir = team_root / abbr
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / 'index.html'
        target.write_text(render_team_story_html(preview), encoding='utf-8')
        written.append(target)
        if preview.get('representation') == REPRESENTATION_WITHHELD:
            withheld.append(abbr)

    fallback = team_root / 'index.html'
    fallback.write_text(
        render_invalid_team_html(site_url=site_url, og_image_path=og_image_path),
        encoding='utf-8',
    )
    return {
        'count': len(written),
        'withheld_count': len(withheld),
        'withheld_teams': sorted(withheld),
        'team_page_root': str(team_root),
        'files': [str(path) for path in written],
        'fallback': str(fallback),
    }
