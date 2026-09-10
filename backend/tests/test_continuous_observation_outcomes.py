import pytest

from services import continuous_observation_outcomes as outcomes


@pytest.mark.parametrize(('classification', 'reason', 'current', 'expected'), [
    ('unchanged', '', True, (outcomes.DUPLICATE, outcomes.HEALTHY, False)),
    ('stale_observation', 'older_upstream_observation', True,
     (outcomes.STALE, outcomes.HEALTHY, False)),
    ('stale_observation', 'weaker_source_authority', True,
     (outcomes.SUPERSEDED, outcomes.HEALTHY, False)),
    ('ambiguous_observation', 'final_evidence_regression', True,
     (outcomes.SAFE_REJECTION, outcomes.WARNING, False)),
    ('ambiguous_observation', 'equal_revision_with_different_material_content', True,
     (outcomes.AMBIGUOUS_NONBLOCKING, outcomes.WARNING, False)),
    ('ambiguous_observation', 'incomparable_source_authority', True,
     (outcomes.AMBIGUOUS_BLOCKING, outcomes.BLOCKING, True)),
    ('partial_observation', '', True,
     (outcomes.OPTIONAL_PARTIAL, outcomes.WARNING, False)),
    ('partial_observation', '', False,
     (outcomes.AMBIGUOUS_BLOCKING, outcomes.BLOCKING, True)),
    ('malformed_observation', '', False,
     (outcomes.MALFORMED, outcomes.BLOCKING, True)),
    ('source_failure', '', False,
     (outcomes.SOURCE_FAILURE, outcomes.BLOCKING, True)),
])
def test_controlled_observation_outcomes(
    classification, reason, current, expected,
):
    result = outcomes.classify(
        classification,
        reason=reason,
        current_authority_satisfied=current,
    )
    assert (
        result.outcome,
        result.severity,
        result.blocks_required_obligation,
    ) == expected
