"""The public serialization boundary for fatigue-derived reads.

BaseballOS's public product is evidence-first and de-scored. The internal
workload model still produces a 0-100 composite, component sub-scores, and an
internal risk tier, and those values still drive availability classification —
but they are implementation detail, never a public claim. A public response may
say "Avoid, worked back-to-back, 41 pitches in three days". It may not say "73".

Nothing in this module changes the fatigue formula, its thresholds, availability
classification, roster authority, freshness semantics, or publication gates. It
only decides what a fatigue-derived read is allowed to *say* when the caller is
anonymous.

Two mechanisms live here:

1. ``public_workload_facts`` — the purpose-built public view model that replaces
   broad ``FatigueScore.to_dict()`` ORM serialization on public routes. It
   carries honest observed workload facts and the row's freshness stamp, and no
   scores, no risk tier, and no database identifiers.

2. ``install_public_score_boundary`` — a response-level backstop that recursively
   removes the internal scoring vocabulary from any anonymous JSON response. The
   narrowed view models above are the actual fix; this exists so a future nested
   payload, a stored snapshot written before this change, or a new surface cannot
   silently reintroduce the exposure.

Authorized internal/admin surfaces keep the scored view. ``require_admin_token``
marks the request as authorized and the backstop leaves those responses alone —
see ``/api/bullpen/fatigue/snapshot``.
"""

from __future__ import annotations

import json

from utils.auth import request_is_admin_authorized


# Internal scoring vocabulary that must never appear in an anonymous response.
#
# This is an explicit list rather than a ``*_score`` pattern on purpose: real
# baseball facts such as ``home_score`` and ``away_score`` are legitimate public
# values, and a blanket suffix rule would silently eat them. When a new internal
# scoring artifact is added to the model, add its key here too — renaming a
# forbidden value does not make it public.
FORBIDDEN_PUBLIC_SCORE_FIELDS = frozenset({
    # The composite and its component sub-scores (models/fatigue_score.py).
    'raw_score',
    'fatigue_score',
    'avg_fatigue_score',
    'pitch_count_score',
    'rest_days_score',
    'appearances_score',
    'leverage_score',
    'innings_score',
    # Internal risk tiers and tier rollups.
    'risk_level',
    'fatigue_risk_level',
    'risk_breakdown',
})

# Database-correlation identifiers carried by ``FatigueScore`` serialization:
# ``id`` is the score row's primary key and ``pitcher_id`` is its foreign key.
# Neither is public identity — a consumer that needs to address a pitcher reads
# the pitcher object beside the workload facts, not the score row's keys.
#
# Scope note: these two are the identifiers SEC-001 removes. The platform-wide
# ``Pitcher.id`` routing identity is a separate, pre-existing concern — it is
# still a sequential database identifier, it is still published on public
# surfaces because they deep-link on it, and migrating it to ``mlb_id`` would
# affect public routes, frontend deep links, persisted Dashboard snapshots, and
# potentially immutable historical Share Artifacts. Nothing here should be read
# as having resolved that.
#
# These are handled by the narrowed view models below rather than by the
# response backstop, because ``id`` and ``pitcher_id`` are ordinary key names
# elsewhere in the API and a recursive strip would break unrelated payloads.
FORBIDDEN_PUBLIC_SCORE_IDENTIFIERS = frozenset({'id', 'pitcher_id'})

# Observed workload facts. These are counted baseball events, not model output,
# and they are what the public Reliever Finder and Pitcher Detail already render.
PUBLIC_WORKLOAD_FACT_FIELDS = (
    'days_since_last_appearance',
    'appearances_last_7',
    'appearances_last_14',
    'pitches_last_7_days',
    'innings_last_7_days',
)


def public_workload_facts(score):
    """Narrow one ``FatigueScore`` row to its public workload view model.

    Returns ``None`` when the pitcher has no scored row, preserving the previous
    ``to_dict() if score else None`` shape for consumers that branch on it.
    """
    if score is None:
        return None

    calculated_at = getattr(score, 'calculated_at', None)
    facts = {
        # Freshness of the read, not a score. Public surfaces show provenance.
        'calculated_at': calculated_at.isoformat() if calculated_at is not None else None,
    }
    for field in PUBLIC_WORKLOAD_FACT_FIELDS:
        facts[field] = getattr(score, field, None)
    return facts


def public_availability(availability):
    """Narrow one availability read for publication.

    ``classify_availability`` keeps the composite and the internal tier in
    ``inputs`` because the classifier and the internal audits read them. The
    public read keeps everything a reader can act on — the status, the
    confidence, the reasons, the limitations, and the counted workload behind
    them — and drops the model's own numbers.

    The classification itself is untouched: this narrows what is published, not
    how availability is decided.
    """
    if not isinstance(availability, dict):
        return availability

    public = dict(availability)
    inputs = public.get('inputs')
    if isinstance(inputs, dict):
        public['inputs'] = {
            key: value
            for key, value in inputs.items()
            if key not in FORBIDDEN_PUBLIC_SCORE_FIELDS
        }
    return public


def scrub_internal_scoring(payload):
    """Recursively drop the internal scoring vocabulary from a JSON structure.

    Returns a new structure; the input is not mutated, so internal callers that
    still read the composite keep working on their own objects.
    """
    if isinstance(payload, dict):
        return {
            key: scrub_internal_scoring(value)
            for key, value in payload.items()
            if key not in FORBIDDEN_PUBLIC_SCORE_FIELDS
        }
    if isinstance(payload, list):
        return [scrub_internal_scoring(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(scrub_internal_scoring(item) for item in payload)
    return payload


def install_public_score_boundary(app):
    """Strip internal scoring artifacts from anonymous JSON responses.

    Admin-authorized requests are passed through untouched: internal scored
    access is intentionally retained behind ``require_admin_token``.
    """

    @app.after_request
    def _enforce_public_score_boundary(response):  # pragma: no cover - wiring
        if request_is_admin_authorized():
            return response
        if not response.is_json or response.direct_passthrough:
            return response

        try:
            payload = response.get_json(silent=True)
        except Exception:
            return response
        if payload is None:
            return response

        scrubbed = scrub_internal_scoring(payload)
        if scrubbed == payload:
            return response

        # set_data updates Content-Length for us.
        response.set_data(json.dumps(scrubbed))
        return response

    return app
