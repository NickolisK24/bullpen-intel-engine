"""Run repeatable, non-destructive SP-14 certification checks."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Inspect BaseballOS sync-pipeline certification gates.',
    )
    parser.add_argument('--environment', default=os.environ.get('APP_ENV', 'development'))
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--evidence-json', help='Optional reviewed gate-evidence JSON file.')
    parser.add_argument('--record', action='store_true', help='Persist certification evidence.')
    parser.add_argument(
        '--allow-production-record', action='store_true',
        help='Explicitly allow certification-evidence writes in production.',
    )
    parser.add_argument('--output')
    return parser.parse_args(argv)


def _command(*args, cwd=REPO_DIR):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _load_evidence(path):
    if not path:
        return {}
    with open(path, encoding='utf-8') as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError('Certification evidence must be a JSON object keyed by gate.')
    return value


def _parse_migration_heads(output):
    return [
        match.group(1)
        for line in output.splitlines()
        if (match := re.match(r'^([0-9a-f]{12})\s+\(head\)$', line.strip()))
    ]


def main(argv=None):
    args = _parse_args(argv)
    if args.record and args.environment == 'production' and not args.allow_production_record:
        print(json.dumps({
            'verdict': 'NO-GO',
            'error': 'production_record_requires_explicit_allow_production_record',
        }, sort_keys=True))
        return 2

    current_sha = _command('git', 'rev-parse', 'HEAD')
    migration_heads = _parse_migration_heads(_command(
        sys.executable, '-m', 'flask', '--app', 'app', 'db', 'heads',
        cwd=BACKEND_DIR,
    ))
    evidence = _load_evidence(args.evidence_json)

    from app import create_app
    from services.sync_pipeline_certification import (
        ActivationControls, certification_checks, collect_operational_health,
        evaluate_certification, legacy_responsibility_map,
        persist_certification_report, persist_legacy_responsibility_map,
    )

    app = create_app(args.environment)
    with app.app_context():
        controls = ActivationControls.from_environment(os.environ)
        health = collect_operational_health()
        checks = certification_checks(
            migration_heads=migration_heads,
            integration_sha_matches=current_sha == args.expected_sha,
            controls=controls,
            evidence=evidence.get('gates') or evidence,
            health=health,
        )
        report = evaluate_certification(checks)
        report.update({
            'integration_commit_sha': current_sha,
            'expected_integration_commit_sha': args.expected_sha,
            'migration_heads': migration_heads,
            'environment': args.environment,
            'configuration_fingerprint': controls.fingerprint,
            'activation_controls': controls.__dict__,
            'activation_violations': [
                row for check in checks
                for row in check.get('evidence', {}).get('violations', [])
            ],
            'operational_health': health,
            'legacy_responsibilities': list(legacy_responsibility_map()),
        })
        if args.record:
            persist_legacy_responsibility_map(
                evidence=evidence.get('legacy_responsibilities'),
            )
            row = persist_certification_report(
                report,
                integration_commit_sha=current_sha,
                migration_head=migration_heads[0] if len(migration_heads) == 1 else 'multiple',
                environment=args.environment,
                controls=controls,
                natural_proof=evidence.get('natural_proof'),
                production_identifiers=evidence.get('production_identifiers'),
            )
            report['certification_run_id'] = row.id

    body = json.dumps(report, indent=2, sort_keys=True, default=str)
    print(body)
    if args.output:
        Path(args.output).write_text(body + '\n', encoding='utf-8')
    return 0 if report['verdict'] == 'GO' else 1


if __name__ == '__main__':
    raise SystemExit(main())
