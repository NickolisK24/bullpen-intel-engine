"""Contract for the CI dependency-audit gate (#601 Slice D).

Two things are asserted here, and they protect different failure modes.

First, the evaluator itself: `backend/scripts/verify_dependency_audit.py` decides
whether a production npm advisory is allowed past CI. It must refuse anything
nobody reviewed, and it must also refuse an acceptance that has expired, names
the wrong package, is duplicated, is missing a field, points at a decision record
that no longer exists, or corresponds to an advisory npm no longer reports. That
last rule is what stops a solved exception from lingering and silently suppressing
the same advisory if it ever returns.

Deliberately database-free. It reads checked-in JSON and calls the evaluator
in-process.
"""

import json
import os
import subprocess
import sys
from datetime import date

import pytest

from scripts import verify_dependency_audit as gate

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_ROOT)
ACCEPTED_PATH = os.path.join(REPO_ROOT, '.github', 'dependency-audit-accepted.json')
EVALUATOR_PATH = os.path.join(BACKEND_ROOT, 'scripts', 'verify_dependency_audit.py')

# The production manifest is the acceptance-critical surface. requirements-dev.txt
# still carries the pytest advisory by design (#601 Slice B), so auditing it would
# make production CI permanently red for a dev-only tool.
RUNTIME_MANIFEST = 'backend/requirements.txt'
DEV_MANIFEST = 'backend/requirements-dev.txt'

# The three React Router advisories reviewed and time-boxed in Slice C. This is
# the live production baseline at the time the gate was added.
BASELINE_ADVISORIES = {
    'GHSA-wrjc-x8rr-h8h6': 'react-router',
    'GHSA-jjmj-jmhj-qwj2': 'react-router-dom',
    'GHSA-337j-9hxr-rhxg': 'react-router',
}
BASELINE_EXPIRY = '2026-11-13'
BASELINE_TRACKING_ISSUE = 645
DECISION_RECORD = 'docs/decisions/2026-08-13-react-router-v7-security-defer.md'

# A date comfortably inside the acceptance window, so the "happy path" tests do
# not start failing on their own the day the acceptance expires.
BEFORE_EXPIRY = date(2026, 8, 13)


# ── fixtures ──────────────────────────────────────────────────────────────────
# A trimmed but structurally faithful npm 10 (auditReportVersion 2) report. The
# shape matters more than the volume: `via` mixes advisory objects with plain
# dependency-propagation strings, and the advisory's own package is via["name"],
# which is not always the row key.
def _npm_report():
    return {
        'auditReportVersion': 2,
        'vulnerabilities': {
            'react-router': {
                'name': 'react-router',
                'severity': 'moderate',
                'isDirect': False,
                'range': '6.0.0 - 7.17.0',
                'via': [
                    {
                        'source': 1124268,
                        'name': 'react-router',
                        'dependency': 'react-router',
                        'title': 'React Router: Open redirect via backslash',
                        'url': 'https://github.com/advisories/GHSA-wrjc-x8rr-h8h6',
                        'severity': 'moderate',
                        'range': '>=6.0.0 <7.18.0',
                    },
                    {
                        'source': 1124272,
                        'name': 'react-router',
                        'dependency': 'react-router',
                        'title': 'React Router: Arbitrary Constructor Injection',
                        'url': 'https://github.com/advisories/GHSA-337j-9hxr-rhxg',
                        'severity': 'moderate',
                        'range': '>=6.0.0 <7.18.0',
                    },
                ],
                'effects': ['react-router-dom'],
                'nodes': ['node_modules/react-router'],
                'fixAvailable': {'name': 'react-router-dom', 'version': '7.18.2'},
            },
            'react-router-dom': {
                'name': 'react-router-dom',
                'severity': 'moderate',
                'isDirect': True,
                'range': '6.0.0-alpha.0 - 7.17.0',
                'via': [
                    {
                        'source': 1124270,
                        'name': 'react-router-dom',
                        'dependency': 'react-router-dom',
                        'title': 'React Router: Open redirect leading to XSS',
                        'url': 'https://github.com/advisories/GHSA-jjmj-jmhj-qwj2',
                        'severity': 'moderate',
                        'range': '>=6.0.0-alpha.0 <7.18.0',
                    },
                    # Plain string: propagation through react-router, NOT an advisory.
                    'react-router',
                ],
                'effects': [],
                'nodes': ['node_modules/react-router-dom'],
                'fixAvailable': {'name': 'react-router-dom', 'version': '7.18.2'},
            },
        },
        'metadata': {
            'vulnerabilities': {
                'info': 0, 'low': 0, 'moderate': 2, 'high': 0,
                'critical': 0, 'total': 2,
            }
        },
    }


def _accepted_entry(advisory_id, package, **overrides):
    entry = {
        'advisory_id': advisory_id,
        'package': package,
        'expires_on': BASELINE_EXPIRY,
        'tracking_issue': BASELINE_TRACKING_ISSUE,
        'decision_record': DECISION_RECORD,
    }
    entry.update(overrides)
    return entry


def _baseline_accepted():
    return [
        _accepted_entry(advisory_id, package)
        for advisory_id, package in BASELINE_ADVISORIES.items()
    ]


def _run(report, accepted, today=BEFORE_EXPIRY, repo_root=REPO_ROOT):
    reported = gate.extract_reported_advisories(report)
    return gate.evaluate(reported, accepted, today, repo_root)


@pytest.fixture(scope='module')
def accepted_payload():
    with open(ACCEPTED_PATH, encoding='utf-8') as handle:
        return json.load(handle)


# ── npm JSON parsing ──────────────────────────────────────────────────────────
def test_the_real_npm_report_shape_yields_exactly_the_three_advisories():
    """Advisory ids come from via[].url; propagation strings are not advisories."""
    reported = gate.extract_reported_advisories(_npm_report())

    assert set(reported) == set(BASELINE_ADVISORIES)
    for advisory_id, package in BASELINE_ADVISORIES.items():
        assert reported[advisory_id]['package'] == package, (
            f'{advisory_id} must be attributed to the package the advisory is '
            'about (via["name"]), not to the row it was reported under'
        )
    # react-router-dom's row lists 'react-router' as a plain string. If that were
    # treated as an advisory the gate would invent a finding that does not exist.
    assert len(reported) == 3


def test_an_unrecognised_payload_is_never_treated_as_a_clean_audit():
    for payload in ({}, {'error': 'network unreachable'}, {'vulnerabilities': []}):
        with pytest.raises(gate.InputError):
            gate.extract_reported_advisories(payload)


def test_a_non_object_payload_is_rejected():
    with pytest.raises(gate.InputError):
        gate.extract_reported_advisories(['not', 'a', 'report'])


# ── the happy paths ───────────────────────────────────────────────────────────
def test_the_current_accepted_baseline_passes():
    violations, valid = _run(_npm_report(), _baseline_accepted())

    assert violations == []
    assert set(valid) == set(BASELINE_ADVISORIES)


def test_a_clean_audit_with_an_empty_allowlist_passes():
    empty_report = {'auditReportVersion': 2, 'vulnerabilities': {}, 'metadata': {}}
    violations, valid = _run(empty_report, [])

    assert violations == []
    assert valid == {}


# ── Rule A — unknown advisory ─────────────────────────────────────────────────
def test_an_unknown_advisory_is_refused():
    """The whole point of the gate: new production drift turns CI red."""
    report = _npm_report()
    report['vulnerabilities']['some-new-package'] = {
        'name': 'some-new-package',
        'severity': 'high',
        'isDirect': True,
        'range': '<9.9.9',
        'via': [{
            'source': 9999999,
            'name': 'some-new-package',
            'title': 'Something newly disclosed',
            'url': 'https://github.com/advisories/GHSA-xxxx-yyyy-zzzz',
            'severity': 'high',
        }],
        'effects': [],
        'nodes': ['node_modules/some-new-package'],
    }

    violations, valid = _run(report, _baseline_accepted())

    assert any('GHSA-xxxx-yyyy-zzzz' in v for v in violations)
    assert any('NEW production advisory' in v for v in violations)
    assert 'GHSA-xxxx-yyyy-zzzz' not in valid


# ── Rule B — wrong package ────────────────────────────────────────────────────
def test_an_advisory_accepted_for_the_wrong_package_is_refused():
    """An advisory id must never suppress an unrelated package."""
    accepted = [
        _accepted_entry('GHSA-wrjc-x8rr-h8h6', 'some-other-package'),
        _accepted_entry('GHSA-jjmj-jmhj-qwj2', 'react-router-dom'),
        _accepted_entry('GHSA-337j-9hxr-rhxg', 'react-router'),
    ]

    violations, valid = _run(_npm_report(), accepted)

    assert any(
        'GHSA-wrjc-x8rr-h8h6' in v and 'some-other-package' in v
        for v in violations
    )
    assert 'GHSA-wrjc-x8rr-h8h6' not in valid


# ── Rule C — expiry ───────────────────────────────────────────────────────────
def test_an_expired_acceptance_is_refused():
    violations, valid = _run(
        _npm_report(), _baseline_accepted(), today=date(2026, 12, 1)
    )

    assert len(violations) == 3
    assert all('expired' in v for v in violations)
    assert valid == {}


@pytest.mark.parametrize('today,expect_accepted', [
    (date(2026, 11, 12), True),   # last valid day
    (date(2026, 11, 13), False),  # expires_on itself is already invalid
    (date(2026, 11, 14), False),
])
def test_the_expiry_boundary_is_deterministic(today, expect_accepted):
    """An acceptance is invalid from 00:00 UTC on expires_on.

    So 2026-11-13 is the FIRST refused day, not the last accepted one. Pinned
    because an off-by-one here silently extends every exception by a day.
    """
    violations, valid = _run(_npm_report(), _baseline_accepted(), today=today)

    if expect_accepted:
        assert violations == []
        assert len(valid) == 3
    else:
        assert violations
        assert valid == {}


# ── Rule D — stale acceptance ─────────────────────────────────────────────────
def test_a_stale_acceptance_is_refused():
    """A solved advisory must have its exception deleted, not left behind."""
    report = _npm_report()
    # GHSA-jjmj-jmhj-qwj2 gets fixed; its row keeps only the propagation string.
    report['vulnerabilities']['react-router-dom']['via'] = ['react-router']

    violations, valid = _run(report, _baseline_accepted())

    assert any(
        'GHSA-jjmj-jmhj-qwj2' in v and 'no longer reported' in v
        for v in violations
    )
    assert 'GHSA-jjmj-jmhj-qwj2' not in valid
    # The still-real advisories remain accepted; only the stale one is refused.
    assert set(valid) == {'GHSA-wrjc-x8rr-h8h6', 'GHSA-337j-9hxr-rhxg'}


# ── Rule E — required metadata ────────────────────────────────────────────────
@pytest.mark.parametrize('missing_field', [
    'advisory_id', 'package', 'expires_on', 'tracking_issue', 'decision_record',
])
def test_an_entry_missing_required_metadata_is_refused(missing_field):
    entry = _accepted_entry('GHSA-wrjc-x8rr-h8h6', 'react-router')
    del entry[missing_field]

    violations, _ = _run(_npm_report(), [entry])

    assert any('missing required field' in v for v in violations)


def test_a_non_date_expiry_is_refused():
    accepted = [_accepted_entry(
        'GHSA-wrjc-x8rr-h8h6', 'react-router', expires_on='whenever'
    )]

    violations, valid = _run(_npm_report(), accepted)

    assert any('not a YYYY-MM-DD date' in v for v in violations)
    assert valid == {}


# ── Rule F — decision record must exist ───────────────────────────────────────
def test_an_entry_whose_decision_record_is_missing_is_refused():
    accepted = [_accepted_entry(
        'GHSA-wrjc-x8rr-h8h6',
        'react-router',
        decision_record='docs/decisions/this-file-does-not-exist.md',
    )]

    violations, valid = _run(_npm_report(), accepted)

    assert any('decision record not found' in v for v in violations)
    assert valid == {}


# ── Rule G — duplicates ───────────────────────────────────────────────────────
def test_a_duplicated_advisory_entry_is_refused():
    accepted = _baseline_accepted()
    accepted.append(_accepted_entry('GHSA-wrjc-x8rr-h8h6', 'react-router'))

    violations, _ = _run(_npm_report(), accepted)

    assert any('listed more than once' in v for v in violations)


# ── malformed inputs ──────────────────────────────────────────────────────────
def test_a_malformed_allowlist_payload_is_rejected():
    for payload in (['not', 'an', 'object'], {'frontend': 'not-a-list'},
                    {'frontend': ['not-an-object']}):
        with pytest.raises(gate.InputError):
            gate.load_accepted(payload, ACCEPTED_PATH)


def test_malformed_json_files_exit_with_the_input_error_code(tmp_path):
    """A broken input must never look like a passing gate."""
    broken = tmp_path / 'broken.json'
    broken.write_text('{ this is not json', encoding='utf-8')

    exit_code = gate.main([
        '--audit', str(broken),
        '--accepted', ACCEPTED_PATH,
        '--repo-root', REPO_ROOT,
        '--today', BEFORE_EXPIRY.isoformat(),
    ])

    assert exit_code == gate.EXIT_INPUT_ERROR


def test_a_missing_audit_file_exits_with_the_input_error_code(tmp_path):
    exit_code = gate.main([
        '--audit', str(tmp_path / 'nope.json'),
        '--accepted', ACCEPTED_PATH,
        '--repo-root', REPO_ROOT,
        '--today', BEFORE_EXPIRY.isoformat(),
    ])

    assert exit_code == gate.EXIT_INPUT_ERROR


def test_an_invalid_today_override_is_rejected(tmp_path):
    audit = tmp_path / 'audit.json'
    audit.write_text(json.dumps(_npm_report()), encoding='utf-8')

    exit_code = gate.main([
        '--audit', str(audit),
        '--accepted', ACCEPTED_PATH,
        '--repo-root', REPO_ROOT,
        '--today', 'not-a-date',
    ])

    assert exit_code == gate.EXIT_INPUT_ERROR


# ── end-to-end exit codes ─────────────────────────────────────────────────────
def test_the_committed_allowlist_passes_against_the_baseline_report(tmp_path):
    audit = tmp_path / 'audit.json'
    audit.write_text(json.dumps(_npm_report()), encoding='utf-8')

    exit_code = gate.main([
        '--audit', str(audit),
        '--accepted', ACCEPTED_PATH,
        '--repo-root', REPO_ROOT,
        '--today', BEFORE_EXPIRY.isoformat(),
    ])

    assert exit_code == gate.EXIT_OK


def test_the_evaluator_exits_non_zero_on_an_unknown_advisory(tmp_path):
    report = _npm_report()
    report['vulnerabilities']['react-router']['via'].append({
        'source': 9999998,
        'name': 'react-router',
        'title': 'Newly disclosed router issue',
        'url': 'https://github.com/advisories/GHSA-xxxx-yyyy-zzzz',
        'severity': 'critical',
    })
    audit = tmp_path / 'audit.json'
    audit.write_text(json.dumps(report), encoding='utf-8')

    exit_code = gate.main([
        '--audit', str(audit),
        '--accepted', ACCEPTED_PATH,
        '--repo-root', REPO_ROOT,
        '--today', BEFORE_EXPIRY.isoformat(),
    ])

    assert exit_code == gate.EXIT_REFUSED


def test_the_evaluator_is_runnable_as_a_script(tmp_path):
    """CI invokes it as a subprocess, so the module must work that way too."""
    audit = tmp_path / 'audit.json'
    audit.write_text(json.dumps(_npm_report()), encoding='utf-8')

    result = subprocess.run(
        [
            sys.executable, EVALUATOR_PATH,
            '--audit', str(audit),
            '--accepted', ACCEPTED_PATH,
            '--repo-root', REPO_ROOT,
            '--today', BEFORE_EXPIRY.isoformat(),
        ],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert 'PASS WITH 3 REVIEWED EXCEPTION(S)' in result.stdout


# ── the committed allowlist itself ────────────────────────────────────────────
def test_the_committed_allowlist_matches_the_reviewed_baseline(accepted_payload):
    entries = accepted_payload['frontend']
    by_id = {entry['advisory_id']: entry for entry in entries}

    assert set(by_id) == set(BASELINE_ADVISORIES), (
        'the machine allowlist must contain exactly the reviewed advisories; '
        'adding one is a security decision, not a CI fix'
    )
    for advisory_id, package in BASELINE_ADVISORIES.items():
        assert by_id[advisory_id]['package'] == package


def test_every_committed_entry_carries_the_required_metadata(accepted_payload):
    for entry in accepted_payload['frontend']:
        for field in gate.REQUIRED_FIELDS:
            assert entry.get(field), f'{entry.get("advisory_id")} lacks {field}'


def test_the_committed_allowlist_uses_no_wildcards_or_severity_suppression(
    accepted_payload,
):
    raw = json.dumps(accepted_payload['frontend'])

    assert '*' not in raw, 'no wildcard advisory or package is permitted'
    for forbidden in ('"ignore"', '"severity"', '"min_severity"', '"all"'):
        assert forbidden not in raw, (
            f'{forbidden} would turn an exact exception into a broad suppression'
        )
    for entry in accepted_payload['frontend']:
        assert entry['advisory_id'].startswith('GHSA-')


def test_no_dev_only_advisory_is_listed_as_a_production_exception(accepted_payload):
    """Dev/build findings are informational and must never be accepted here."""
    dev_only_packages = {
        '@babel/core', 'esbuild', 'nanoid', 'picomatch', 'postcss', 'vite',
    }
    listed = {entry['package'] for entry in accepted_payload['frontend']}

    assert not (listed & dev_only_packages)


def test_the_allowlist_has_no_duplicate_advisory_ids(accepted_payload):
    ids = [entry['advisory_id'] for entry in accepted_payload['frontend']]

    assert len(ids) == len(set(ids))


# ── human / machine consistency ───────────────────────────────────────────────
def test_the_machine_allowlist_agrees_with_the_human_decision_record(
    accepted_payload,
):
    """Durable identifiers only — the prose itself is not machine-parsed."""
    record_path = os.path.join(REPO_ROOT, DECISION_RECORD)
    assert os.path.isfile(record_path), 'the decision record must exist'
    with open(record_path, encoding='utf-8') as handle:
        prose = handle.read()

    for entry in accepted_payload['frontend']:
        assert entry['advisory_id'] in prose, (
            f'{entry["advisory_id"]} is machine-accepted but absent from the '
            'human decision record'
        )
        assert entry['expires_on'] in prose, (
            'the expiry in the machine file must match the human record'
        )
        assert str(entry['tracking_issue']) in prose, (
            'the tracking issue in the machine file must match the human record'
        )
        assert entry['decision_record'] == DECISION_RECORD
