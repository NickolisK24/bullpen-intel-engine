"""Private WP44 briefing assembly and durable editorial posting receipts."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from models.editorial_post_history import EditorialPostHistory
from services.slate_editorial_ranker import build_ranked_slate
from utils.db import db
from utils.time import utc_now_naive


EASTERN = ZoneInfo('America/New_York')
PLATFORMS = {'X', 'Instagram', 'LinkedIn', 'Reddit'}


class PostingValidationError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def eastern_today(now=None):
    if now is None:
        return datetime.now(EASTERN).date()
    if isinstance(now, date) and not isinstance(now, datetime):
        return now
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo('UTC'))
    return now.astimezone(EASTERN).date()


def resolve_briefing_date(value, *, now=None):
    today = eastern_today(now)
    normalized = str(value or 'today').strip().lower()
    if normalized == 'today':
        return today
    if normalized == 'tomorrow':
        return today + timedelta(days=1)
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise PostingValidationError('invalid_briefing_date') from exc


def _platform_drafts(candidate):
    if not candidate.get('publishable') or not candidate.get('plain_one_liner'):
        return {}
    line = candidate['plain_one_liner']
    matchup = candidate.get('matchup') or {}
    label = matchup.get('label') or 'Tonight\'s matchup'
    return {
        'X': {'text': line, 'partial': False},
        'Instagram': {'text': f'{label}\n\n{line}', 'partial': False},
        'LinkedIn': {'text': f'{label}: {line}', 'partial': False},
        'Reddit': {'text': f'{label}\n\n{line}', 'partial': False},
    }


def _team_label(team):
    return team.get('team_name') or team.get('team_abbreviation') or f"Team {team.get('team_id')}"


def _enrich_candidate(candidate, index):
    home = candidate.get('home_team') or {}
    away = candidate.get('away_team') or {}
    candidate['rank'] = index + 1
    candidate['ranked_highest'] = index == 0
    candidate['recommended_to_post'] = False
    candidate['matchup'] = {
        'home_team_id': home.get('team_id'),
        'home_team_name': _team_label(home),
        'home_team_abbreviation': home.get('team_abbreviation'),
        'away_team_id': away.get('team_id'),
        'away_team_name': _team_label(away),
        'away_team_abbreviation': away.get('team_abbreviation'),
        'label': f'{_team_label(away)} at {_team_label(home)}',
    }
    candidate['schedule_freshness'] = (candidate.get('data_freshness') or {}).get('schedule') or {}
    candidate['bullpen_data_freshness'] = {
        'home_team': home.get('data_freshness') or {},
        'away_team': away.get('data_freshness') or {},
    }
    candidate['named_arms_evidence'] = {
        'home_team': home.get('named_arms_evidence') or {},
        'away_team': away.get('named_arms_evidence') or {},
    }
    candidate['platform_drafts'] = _platform_drafts(candidate)
    return candidate


def build_slate_briefing(value='today', *, now=None):
    briefing_date = resolve_briefing_date(value, now=now)
    as_of = now.replace(tzinfo=None) if isinstance(now, datetime) and now.tzinfo else now
    ranked = [
        _enrich_candidate(candidate, index)
        for index, candidate in enumerate(build_ranked_slate(briefing_date, as_of=as_of))
    ]
    recommendation = next((candidate for candidate in ranked if candidate.get('publishable')), None)
    if recommendation:
        recommendation['recommended_to_post'] = True
    result = {
        'briefing_date': briefing_date.isoformat(),
        'ranked_highest': ranked[0]['candidate_id'] if ranked else None,
        'has_publishable_candidate': recommendation is not None,
        'candidates': ranked,
    }
    if recommendation:
        result['top_recommendation'] = recommendation['candidate_id']
    return result


def _valid_url(value):
    if not value:
        return True
    parsed = urlparse(value)
    return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def mark_candidate_posted(payload, *, now=None):
    payload = payload or {}
    candidate_id = str(payload.get('candidate_id') or '').strip()
    platform = str(payload.get('platform') or '').strip()
    final_text = str(payload.get('final_post_text') or '').strip()
    evidence_reference = str(payload.get('evidence_reference') or '').strip()
    generated_text = str(payload.get('generated_draft_text') or '').strip() or None
    external_url = str(payload.get('external_post_url') or '').strip() or None
    briefing_value = payload.get('source_briefing_date') or 'today'
    if platform not in PLATFORMS:
        raise PostingValidationError('invalid_platform')
    if not final_text:
        raise PostingValidationError('final_post_text_required')
    if not candidate_id:
        raise PostingValidationError('candidate_id_required')
    if not _valid_url(external_url):
        raise PostingValidationError('invalid_external_post_url')

    briefing = build_slate_briefing(briefing_value, now=now)
    candidate = next((item for item in briefing['candidates'] if item['candidate_id'] == candidate_id), None)
    if candidate is None:
        raise PostingValidationError('unknown_or_stale_candidate', 409)
    if candidate.get('publishable') is not True:
        raise PostingValidationError('candidate_not_publishable', 409)
    if not evidence_reference or evidence_reference != candidate.get('evidence_reference'):
        raise PostingValidationError('evidence_mismatch', 409)
    allowed_draft = ((candidate.get('platform_drafts') or {}).get(platform) or {}).get('text')
    if generated_text and generated_text != allowed_draft:
        raise PostingValidationError('generated_draft_mismatch', 409)

    team_ids = [candidate['home_team']['team_id'], candidate['away_team']['team_id']]
    featured_team_id = candidate['featured_team']['team_id']
    receipt = EditorialPostHistory(
        team_id=featured_team_id,
        story_shape=candidate['shape'],
        posted_at=(now.replace(tzinfo=None) if isinstance(now, datetime) and now.tzinfo else now) or utc_now_naive(),
        platform=platform,
        team_ids_json=json.dumps(team_ids),
        game_pks_json=json.dumps(candidate['game_pks']),
        candidate_id=candidate_id,
        evidence_reference=evidence_reference,
        evidence_snapshot_json=json.dumps(candidate, sort_keys=True, default=str),
        generated_draft_text=generated_text,
        final_post_text=final_text,
        external_post_url=external_url,
        score_version=candidate['score_version'],
        source_briefing_date=date.fromisoformat(briefing['briefing_date']),
    )
    db.session.add(receipt)
    db.session.commit()
    return receipt


def recent_posting_history(limit=10):
    limit = max(1, min(int(limit or 10), 50))
    return [
        row.to_dict()
        for row in EditorialPostHistory.query.order_by(
            EditorialPostHistory.posted_at.desc(), EditorialPostHistory.id.desc(),
        ).limit(limit).all()
    ]


__all__ = [
    'PLATFORMS', 'PostingValidationError', 'build_slate_briefing',
    'mark_candidate_posted', 'recent_posting_history', 'resolve_briefing_date',
]
