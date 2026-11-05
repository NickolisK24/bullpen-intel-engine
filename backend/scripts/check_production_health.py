"""Check BaseballOS production health from its public API (WP-0.2).

READ-ONLY and credential-free: it calls two public GET endpoints
(``/api/health`` and ``/api/bullpen/team-states``) and, when run inside a git
checkout of ``main``, compares the commit the API reports with the latest
commit that changed deployable backend code. It never touches the database.

    BASEBALLOS_API_BASE_URL=https://<api-host> \
      python backend/scripts/check_production_health.py --output health.json

``BASEBALLOS_API_BASE_URL`` may be omitted when ``BASEBALLOS_SYNC_URL`` (the
existing ``.../api/bullpen/sync`` secret) is set; the base is derived from it.

Exit status: 0 healthy or degraded, 1 critical, 2 usage error. A scheduled
GitHub Actions run that exits 1 is the alert: GitHub notifies the repository
owner of failed scheduled runs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.production_health import evaluate_production_health  # noqa: E402

SYNC_PATH_SUFFIX = '/api/bullpen/sync'
# Paths whose change redeploys the API. Generated preview pages under
# frontend/ never change the backend release.
BACKEND_PATHS = ('backend',)
# Render needs time to build and roll out a merge before it is "late".
DEPLOY_GRACE = timedelta(hours=2)
USER_AGENT = 'BaseballOS-health-check/1'


def api_base_url(environ=os.environ):
    base = (environ.get('BASEBALLOS_API_BASE_URL') or '').strip().rstrip('/')
    if base:
        return base
    sync_url = (environ.get('BASEBALLOS_SYNC_URL') or '').strip().rstrip('/')
    if sync_url.endswith(SYNC_PATH_SUFFIX):
        return sync_url[: -len(SYNC_PATH_SUFFIX)]
    return None


def fetch_json(url, *, timeout=60):
    """Return ``(status_code, payload_or_None)``; never raises for HTTP errors."""
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, None
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


def _git(*args):
    completed = subprocess.run(
        ['git', *args], cwd=REPO_DIR, capture_output=True, text=True, check=False,
    )
    return completed.returncode, completed.stdout.strip()


def expected_backend_release(now, *, ref='HEAD', grace=DEPLOY_GRACE):
    """Latest commit on ``ref`` that changed backend code and is past the grace period."""
    code, out = _git(
        'log', '-1', '--format=%H %ct', f'--until={int((now - grace).timestamp())}',
        ref, '--', *BACKEND_PATHS,
    )
    if code != 0 or not out:
        return None
    return out.split()[0]


def release_contains(release, expected):
    """True/False when both commits are known locally; ``None`` when not comparable."""
    if not release or not expected:
        return None
    for sha in (release, expected):
        code, _ = _git('cat-file', '-e', f'{sha}^{{commit}}')
        if code != 0:
            return None
    code, _ = _git('merge-base', '--is-ancestor', expected, release)
    return code == 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--output', help='Write the JSON result here as well as stdout.')
    parser.add_argument('--ref', default='HEAD', help='Git ref whose backend history defines the expected release.')
    args = parser.parse_args(argv)

    base = api_base_url()
    if not base:
        print('error: set BASEBALLOS_API_BASE_URL or BASEBALLOS_SYNC_URL', file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    health_status, health = fetch_json(f'{base}/api/health')
    listing_status, listing = fetch_json(f'{base}/api/bullpen/team-states')
    expected = expected_backend_release(now, ref=args.ref)
    release = (health or {}).get('release') if isinstance(health, dict) else None
    result = evaluate_production_health(
        health=health,
        health_status_code=health_status,
        listing=listing,
        listing_status_code=listing_status,
        now=now,
        expected_release=expected,
        release_is_current=release_contains(release, expected),
    )
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.output:
        Path(args.output).write_text(text + '\n', encoding='utf-8')
    return 1 if result['status'] == 'critical' else 0


if __name__ == '__main__':
    raise SystemExit(main())
