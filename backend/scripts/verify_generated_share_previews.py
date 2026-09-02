#!/usr/bin/env python3
"""Fail-closed delivery gate for generated immutable share preview pages."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path


EXIT_OK = 0
EXIT_DELIVERY_VIOLATION = 1
EXIT_CANNOT_VERIFY = 2

META_PATTERN = re.compile(
    r'<meta\s+name="baseballos:(?P<key>[a-z-]+)"\s+content="(?P<value>[^"]*)"\s*/>'
)
OG_PATTERN = re.compile(
    r'<meta\s+property="og:(?P<key>[a-z:]+)"\s+content="(?P<value>[^"]*)"\s*/>'
)
CANONICAL_PATTERN = re.compile(r'<link\s+rel="canonical"\s+href="(?P<value>[^"]*)"\s*/>')
HREF_PATTERN = re.compile(r'<a\s+href="(?P<value>[^"]+)"')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-result', required=True)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--routing-config', required=True)
    parser.add_argument('--digest-out')
    parser.add_argument('--summary-out')
    return parser.parse_args(argv)


def _load(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('export result is not an object')
    return value


def _meta(text):
    return {
        match.group('key'): html.unescape(match.group('value'))
        for match in META_PATTERN.finditer(text)
    }


def _og(text):
    return {
        match.group('key'): html.unescape(match.group('value'))
        for match in OG_PATTERN.finditer(text)
    }


def _verify_routing_config(path):
    violations = []
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f'cannot read share routing config: {exc}']

    redirects = config.get('redirects') or []
    routes = config.get('routes') or []
    required_redirect = {
        'source': '/share/:publicId/',
        'destination': '/share/:publicId',
        'permanent': True,
    }
    if required_redirect not in redirects:
        violations.append('trailing-slash share URL does not redirect to the canonical no-slash URL')

    filesystem = next((row for row in routes if row.get('handle') == 'filesystem'), None)
    if filesystem != {'handle': 'filesystem'}:
        violations.append('generated share pages are not served by the filesystem authority')

    share_source = r'^/share/([A-Za-z0-9._-]{1,64})$'
    invalid_share = next((row for row in routes if row.get('src') == share_source), None)
    if invalid_share != {
        'src': share_source,
        'dest': '/404.html',
        'status': 404,
    }:
        violations.append('unmatched canonical share IDs do not return the static HTTP 404')

    if any(row.get('dest') == '/share/index.html' for row in routes):
        violations.append('invalid share IDs still resolve to the legacy HTTP-200 fallback')

    spa = next((row for row in routes if row.get('dest') == '/index.html'), None)
    if spa is None:
        violations.append('SPA fallback is unavailable for non-share application routes')
    else:
        try:
            pattern = re.compile(spa['src'])
        except (KeyError, re.error):
            violations.append('SPA fallback source is not a valid bounded route pattern')
        else:
            if filesystem is not None and routes.index(filesystem) >= routes.index(spa):
                violations.append('filesystem share authority no longer precedes the SPA fallback')
            if invalid_share is not None and routes.index(invalid_share) >= routes.index(spa):
                violations.append('invalid share 404 no longer precedes the SPA fallback')
            if not pattern.fullmatch('/bullpen'):
                violations.append('share 404 isolation broke the primary bullpen SPA route')
            if not pattern.fullmatch('/dashboard'):
                violations.append('share 404 isolation broke the existing SPA fallback')
    return violations


def verify(result, output_root, routing_config=None):
    violations = []
    facts = {'export_status': result.get('status')}
    if result.get('status') != 'ok':
        return ['share preview exporter did not declare success'], facts
    if routing_config is not None:
        violations.extend(_verify_routing_config(routing_config))

    output = result.get('output')
    if not isinstance(output, dict):
        return ['share preview exporter declared no output'], facts

    artifacts = result.get('artifacts')
    previews = result.get('previews')
    count = output.get('count')
    snapshot_id = result.get('publication_snapshot_id')
    facts.update(
        artifacts=artifacts,
        previews=previews,
        generated_file_count=count,
        snapshot_id=snapshot_id,
        data_through=result.get('publication_data_through'),
    )
    if snapshot_id in (None, ''):
        violations.append('share export names no authorizing publication snapshot')
    if not isinstance(count, int) or count < 1:
        violations.append(f'generated share page count is not positive ({count!r})')
    if artifacts != previews or previews != count:
        violations.append(
            f'export counts disagree: artifacts={artifacts!r}, previews={previews!r}, count={count!r}'
        )

    share_root = Path(output_root) / 'share'
    declared = [Path(path) for path in (output.get('files') or [])]
    fallback = Path(output.get('fallback')) if output.get('fallback') else None
    if fallback is None:
        violations.append('share fallback is not declared')

    expected = {path.resolve() for path in declared}
    if fallback is not None:
        expected.add(fallback.resolve())
    on_disk = {path.resolve() for path in share_root.glob('*/index.html')}
    if fallback is not None and fallback.is_file():
        on_disk.add(fallback.resolve())
    if on_disk != expected:
        for path in sorted(on_disk - expected):
            violations.append(f'unexpected generated share page: {path}')
        for path in sorted(expected - on_disk):
            violations.append(f'declared generated share page is missing: {path}')

    for path in declared:
        if not path.is_file() or path.stat().st_size == 0:
            violations.append(f'generated share page is missing or empty: {path}')
            continue
        text = path.read_text(encoding='utf-8')
        metadata = _meta(text)
        open_graph = _og(text)
        public_id = path.parent.name
        canonical = f'https://baseballos.app/share/{public_id}'
        canonical_match = CANONICAL_PATTERN.search(text)
        required_meta = {
            'representation': 'immutable_share_artifact',
            'public-id': public_id,
        }
        for key, expected_value in required_meta.items():
            if metadata.get(key) != expected_value:
                violations.append(f'{path}: baseballos:{key} is not {expected_value!r}')
        if not metadata.get('data-through'):
            violations.append(f'{path}: missing frozen data-through receipt')
        if open_graph.get('url') != canonical:
            violations.append(f'{path}: og:url does not match its public_id')
        if canonical_match is None or html.unescape(canonical_match.group('value')) != canonical:
            violations.append(f'{path}: canonical URL does not match its public_id')
        live_destination = metadata.get('live-destination')
        hrefs = [html.unescape(match.group('value')) for match in HREF_PATTERN.finditer(text)]
        if not live_destination or live_destination not in hrefs:
            violations.append(f'{path}: ordinary live-app destination is missing')
        if live_destination in {f'/share/{public_id}', f'/share/{public_id}/'}:
            violations.append(f'{path}: live-app destination targets the share page itself')
        if 'window.location' in text:
            violations.append(f'{path}: generated page contains automatic navigation')
        if metadata.get('team') and metadata['team'] not in text:
            violations.append(f'{path}: static body does not preserve team identity')
        if metadata.get('team-state') and metadata['team-state'] not in text:
            violations.append(f'{path}: static body does not preserve Team State identity')
        try:
            evidence_count = int(metadata.get('evidence-count', '0'))
        except ValueError:
            evidence_count = -1
        if evidence_count < 0:
            violations.append(f'{path}: invalid frozen evidence count')
        elif evidence_count and 'Evidence behind the read' not in text:
            violations.append(f'{path}: frozen evidence is absent from static content')
        if open_graph.get('image') != 'https://baseballos.app/og/baseballos-card.png':
            violations.append(f'{path}: social image is not the governed raster card')
        if open_graph.get('image:width') != '1200' or open_graph.get('image:height') != '630':
            violations.append(f'{path}: social image dimensions are not 1200x630')
        if open_graph.get('image:type') != 'image/png':
            violations.append(f'{path}: social image type is not image/png')
        if '<meta name="twitter:card" content="summary_large_image" />' not in text:
            violations.append(f'{path}: twitter card is not summary_large_image')
    if fallback is not None and fallback.is_file():
        text = fallback.read_text(encoding='utf-8')
        metadata = _meta(text)
        if metadata.get('representation') != 'invalid_share_artifact':
            violations.append('invalid share fallback has no governed representation receipt')
        for forbidden in ('baseballos:public-id', 'baseballos:team-state', 'baseballos:data-through'):
            if forbidden in text:
                violations.append(f'invalid share fallback leaks claim metadata: {forbidden}')
        for forbidden in ('rel="canonical"', 'property="og:url"', 'window.location'):
            if forbidden in text:
                violations.append(f'invalid share fallback contains false routing metadata: {forbidden}')
    else:
        violations.append('invalid share fallback is missing')

    return violations, facts


def digest(result):
    output = result.get('output') or {}
    paths = [Path(path) for path in (output.get('files') or [])]
    if output.get('fallback'):
        paths.append(Path(output['fallback']))
    return [
        {'path': path.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(paths, key=lambda value: value.as_posix())
        if path.is_file()
    ]


def main(argv=None):
    args = parse_args(argv)
    try:
        result = _load(args.export_result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'::error title=Generated Share Preview::Cannot read export result: {exc}')
        return EXIT_CANNOT_VERIFY

    violations, facts = verify(result, args.output_root, args.routing_config)
    digest_rows = digest(result)
    if args.digest_out:
        path = Path(args.digest_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(digest_rows, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if args.summary_out:
        path = Path(args.summary_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                'result': 'fail' if violations else 'pass',
                'violations': violations,
                'digest_file_count': len(digest_rows),
                **facts,
            }, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
    if violations:
        for violation in violations:
            print(f'::error title=Generated Share Preview::{violation}')
        return EXIT_DELIVERY_VIOLATION
    print(f'Generated share preview delivery verified: {facts.get("generated_file_count")} artifact page(s).')
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
