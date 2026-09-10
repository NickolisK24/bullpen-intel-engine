"""Post-publication handoff to the generated distribution workflow.

This module does not generate content and never mutates baseball data. It sends
one narrow GitHub Actions workflow-dispatch request after a trusted publication
has committed. Callers treat every result as operational evidence only: a
delivery failure must never invalidate the publication that triggered it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_REPOSITORY = 'NickolisK24/bullpen-intel-engine'
DEFAULT_WORKFLOW = 'baseballos-generated-distribution.yml'
DEFAULT_REF = 'main'
DEFAULT_TIMEOUT_SECONDS = 10.0

TOKEN_ENV = 'BASEBALLOS_DISTRIBUTION_GITHUB_TOKEN'
REPOSITORY_ENV = 'BASEBALLOS_DISTRIBUTION_GITHUB_REPOSITORY'
WORKFLOW_ENV = 'BASEBALLOS_DISTRIBUTION_GITHUB_WORKFLOW'
REF_ENV = 'BASEBALLOS_DISTRIBUTION_GITHUB_REF'
TIMEOUT_ENV = 'BASEBALLOS_DISTRIBUTION_DISPATCH_TIMEOUT_SECONDS'


@dataclass(frozen=True)
class DistributionDeliveryRequest:
    snapshot_id: int
    sync_run_id: int
    data_through: str
    publication_source: str
    publication_type: str

    def workflow_inputs(self):
        return {
            'mode': 'distribution',
            'snapshot_id': str(self.snapshot_id),
            'sync_run_id': str(self.sync_run_id),
            'data_through': str(self.data_through),
            'publication_source': str(self.publication_source),
            'publication_type': str(self.publication_type),
        }


def _configured_timeout(environ):
    raw = str(environ.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT_SECONDS).strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


def request_distribution_delivery(
    delivery,
    *,
    environ=None,
    opener=urlopen,
):
    """Request one exact-publication distribution run.

    The return value is deliberately sanitized. It never contains a token,
    response body, database URL, or exception text that could expose runtime
    configuration in a Render log.
    """
    environ = os.environ if environ is None else environ
    token = str(environ.get(TOKEN_ENV) or '').strip()
    if not token:
        return {
            'status': 'failed_to_request',
            'reason': 'dispatch_token_missing',
            'snapshot_id': delivery.snapshot_id,
        }

    repository = str(environ.get(REPOSITORY_ENV) or DEFAULT_REPOSITORY).strip()
    workflow = str(environ.get(WORKFLOW_ENV) or DEFAULT_WORKFLOW).strip()
    ref = str(environ.get(REF_ENV) or DEFAULT_REF).strip()
    if repository.count('/') != 1 or not all(repository.split('/')):
        return {
            'status': 'failed_to_request',
            'reason': 'repository_configuration_invalid',
            'snapshot_id': delivery.snapshot_id,
        }
    if not workflow or not ref:
        return {
            'status': 'failed_to_request',
            'reason': 'workflow_configuration_invalid',
            'snapshot_id': delivery.snapshot_id,
        }

    url = (
        f'https://api.github.com/repos/{repository}/actions/workflows/'
        f'{quote(workflow, safe="")}/dispatches'
    )
    body = json.dumps({
        'ref': ref,
        'inputs': delivery.workflow_inputs(),
    }).encode('utf-8')
    request = Request(
        url,
        data=body,
        method='POST',
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'BaseballOS-Distribution-Handoff',
            'X-GitHub-Api-Version': '2022-11-28',
        },
    )

    try:
        response = opener(request, timeout=_configured_timeout(environ))
        status_code = getattr(response, 'status', None) or response.getcode()
    except HTTPError as exc:
        return {
            'status': 'failed_to_request',
            'reason': f'github_http_{exc.code}',
            'snapshot_id': delivery.snapshot_id,
        }
    except (URLError, OSError, TimeoutError):
        return {
            'status': 'failed_to_request',
            'reason': 'github_unreachable',
            'snapshot_id': delivery.snapshot_id,
        }

    if status_code != 204:
        return {
            'status': 'failed_to_request',
            'reason': f'github_http_{status_code}',
            'snapshot_id': delivery.snapshot_id,
        }
    return {
        'status': 'requested',
        'snapshot_id': delivery.snapshot_id,
        'sync_run_id': delivery.sync_run_id,
        'data_through': delivery.data_through,
        'publication_source': delivery.publication_source,
        'publication_type': delivery.publication_type,
        'workflow': workflow,
        'ref': ref,
    }
