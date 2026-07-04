from argparse import ArgumentParser
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from models.pitcher import Pitcher  # noqa: E402
from services import dashboard_snapshot as dashboard_snapshot_service  # noqa: E402
from services import sync_metadata  # noqa: E402
from services.availability_reference_date import (  # noqa: E402
    product_availability_reference_date_from_sync_status,
    product_current_date,
)
from services.availability_snapshot import (  # noqa: E402
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from services.bullpen_eligibility import evaluate_bullpen_eligibility  # noqa: E402
from services.bullpen_population import (  # noqa: E402
    eligible_bullpen_pitcher_contexts,
    population_diagnostic,
    usage_logs_by_pitcher,
)
from services.role_authority import classify_role  # noqa: E402
from services.roster_status import classify_roster_status, allows_default_board  # noqa: E402


def _reference_date():
    sync_status = sync_metadata.build_sync_status_payload()
    return (
        product_availability_reference_date_from_sync_status(sync_status)
        or product_current_date()
    )


def _current_records(reference_date):
    pitchers = Pitcher.query.filter(Pitcher.active == True).order_by(Pitcher.id).all()
    logs_by = usage_logs_by_pitcher(
        [pitcher.id for pitcher in pitchers],
        include_stale=True,
        reference_date=reference_date,
    )
    rows = latest_fatigue_rows()
    classified = classify_latest_fatigue_rows(
        rows,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    dashboard_contexts = eligible_bullpen_pitcher_contexts(
        [record['pitcher'] for record in classified],
        include_stale=True,
        include_inactive_context=False,
        reference_date=reference_date,
        use_role_authority=False,
    )
    dashboard_ids = {context['pitcher'].id for context in dashboard_contexts}

    records = []
    for pitcher in pitchers:
        logs = logs_by.get(pitcher.id, [])
        roster = classify_roster_status(pitcher)
        eligibility = evaluate_bullpen_eligibility(
            pitcher,
            logs,
            reference_date=reference_date,
            respect_local_active=not roster.get('is_authoritative'),
        )
        role = classify_role(pitcher, logs, reference_date=reference_date)
        records.append({
            'pitcher_id': pitcher.id,
            'name': pitcher.full_name,
            'roster_allows_default': allows_default_board(roster),
            'eligibility_status': eligibility.get('status'),
            'eligibility_eligible': bool(eligibility.get('eligible')),
            'role': role.get('role'),
            'role_status': role.get('status'),
            'role_eligible': bool(role.get('eligible')),
            'dashboard_visible': pitcher.id in dashboard_ids,
        })
    return records


def _distribution(records, key):
    values = sorted({record.get(key) for record in records})
    return {
        value: sum(1 for record in records if record.get(key) == value)
        for value in values
    }


def _compare(before_records, after_records):
    before = {record['pitcher_id']: record for record in before_records}
    after = {record['pitcher_id']: record for record in after_records}
    common_ids = sorted(set(before) & set(after))

    role_changes = [
        pitcher_id for pitcher_id in common_ids
        if before[pitcher_id].get('role') != after[pitcher_id].get('role')
    ]
    eligibility_changes = [
        pitcher_id for pitcher_id in common_ids
        if (
            before[pitcher_id].get('eligibility_status'),
            before[pitcher_id].get('eligibility_eligible'),
        ) != (
            after[pitcher_id].get('eligibility_status'),
            after[pitcher_id].get('eligibility_eligible'),
        )
    ]
    before_dashboard = {pid for pid, record in before.items() if record.get('dashboard_visible')}
    after_dashboard = {pid for pid, record in after.items() if record.get('dashboard_visible')}

    return {
        'pitchers_with_changed_role_classification': len(role_changes),
        'pitchers_with_changed_bullpen_eligibility': len(eligibility_changes),
        'dashboard_population_before': len(before_dashboard),
        'dashboard_population_after': len(after_dashboard),
        'dashboard_population_delta': len(after_dashboard) - len(before_dashboard),
        'dashboard_added': sorted(after_dashboard - before_dashboard),
        'dashboard_removed': sorted(before_dashboard - after_dashboard),
    }


def main():
    parser = ArgumentParser(
        description='Report role and bullpen-population impact after games_started backfill.'
    )
    parser.add_argument('--baseline', default=None)
    parser.add_argument('--build-dashboard-snapshot', action='store_true')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        ref = _reference_date()
        after_records = _current_records(ref)
        payload = {
            'reference_date': ref.isoformat(),
            'active_pitchers': len(after_records),
            'role_distribution': _distribution(after_records, 'role'),
            'eligibility_status_distribution': _distribution(after_records, 'eligibility_status'),
            'dashboard_population_after': sum(
                1 for record in after_records if record.get('dashboard_visible')
            ),
        }

        if args.baseline:
            baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
            payload['baseline_reference_date'] = baseline.get('reference_date')
            payload['impact'] = _compare(baseline.get('records') or [], after_records)

        diagnostic = population_diagnostic(
            Pitcher.query.filter(Pitcher.active == True).order_by(Pitcher.full_name).all(),
            include_stale=True,
            reference_date=ref,
        )
        payload['role_authority_dry_run'] = {
            'enabled_for_live_population': diagnostic['use_role_authority_default'],
            'legacy_population': diagnostic['totals']['legacy_population'],
            'role_authority_population': diagnostic['totals']['role_population'],
            'population_delta': (
                diagnostic['totals']['role_population']
                - diagnostic['totals']['legacy_population']
            ),
            'different_population_count': (
                len(diagnostic['additions']) + len(diagnostic['removals'])
            ),
            'additions': diagnostic['additions'],
            'removals': diagnostic['removals'],
            'role_distribution': diagnostic['role_distribution'],
            'confidence_distribution': diagnostic['confidence_distribution'],
        }

        if args.build_dashboard_snapshot:
            payload['dashboard_snapshot'] = (
                dashboard_snapshot_service.build_bullpen_dashboard_snapshot_v2(
                    source=dashboard_snapshot_service.SNAPSHOT_SOURCE_BUILDER_V2,
                    publish=True,
                )
            )

    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
