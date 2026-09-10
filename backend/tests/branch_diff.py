"""Resolve the current branch changeset for repository freeze guards."""

from __future__ import annotations

import os
import subprocess


class ComparisonBaseUnavailable(RuntimeError):
    """Raised when the current changeset cannot be resolved safely."""


def _git(repo_root, *args, check=True):
    return subprocess.run(
        ['git', *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=check,
    )


def _remote_ref(base_name):
    value = str(base_name or '').strip()
    if value.startswith('refs/remotes/'):
        return value.removeprefix('refs/remotes/')
    if value.startswith('refs/heads/'):
        value = value.removeprefix('refs/heads/')
    if value.startswith('origin/'):
        return value
    return f'origin/{value}' if value else None


def _verify_ref(repo_root, ref):
    try:
        _git(repo_root, 'rev-parse', '--verify', f'{ref}^{{commit}}')
    except Exception as exc:
        raise ComparisonBaseUnavailable(
            f'comparison ref is unavailable: {ref}'
        ) from exc
    return ref


def _nearest_remote_ancestor(repo_root):
    """Find one unambiguous remote ancestor when CI supplies no PR base."""
    try:
        head = _git(repo_root, 'rev-parse', 'HEAD').stdout.strip()
        branch = _git(repo_root, 'branch', '--show-current').stdout.strip()
        refs = _git(
            repo_root,
            'for-each-ref',
            '--format=%(refname:short)',
            'refs/remotes/origin',
        ).stdout.splitlines()
    except Exception as exc:
        raise ComparisonBaseUnavailable(
            'remote comparison refs are unavailable'
        ) from exc

    current_remote = f'origin/{branch}' if branch else None
    candidates = []
    for ref in (value.strip() for value in refs if value.strip()):
        if ref == 'origin/HEAD' or ref == current_remote:
            continue
        try:
            sha = _git(repo_root, 'rev-parse', ref).stdout.strip()
        except Exception:
            continue
        if sha == head:
            continue
        ancestor = _git(
            repo_root,
            'merge-base',
            '--is-ancestor',
            ref,
            'HEAD',
            check=False,
        )
        if ancestor.returncode == 1:
            continue
        if ancestor.returncode != 0:
            raise ComparisonBaseUnavailable(
                f'could not evaluate comparison candidate: {ref}'
            )
        try:
            distance = int(
                _git(repo_root, 'rev-list', '--count', f'{ref}..HEAD')
                .stdout.strip()
            )
        except (TypeError, ValueError, subprocess.SubprocessError) as exc:
            raise ComparisonBaseUnavailable(
                f'could not measure comparison candidate: {ref}'
            ) from exc
        candidates.append((distance, sha, ref))

    if not candidates:
        raise ComparisonBaseUnavailable('no remote ancestor is available')

    nearest_distance = min(distance for distance, _sha, _ref in candidates)
    nearest = [item for item in candidates if item[0] == nearest_distance]
    if len({sha for _distance, sha, _ref in nearest}) != 1:
        raise ComparisonBaseUnavailable('nearest remote ancestor is ambiguous')
    return sorted(ref for _distance, _sha, ref in nearest)[0]


def resolve_comparison_ref(repo_root, environ=None):
    """Prefer the pull-request base, with a fail-closed local/push fallback."""
    environment = os.environ if environ is None else environ
    ci_base = _remote_ref(environment.get('GITHUB_BASE_REF'))
    if ci_base:
        return _verify_ref(repo_root, ci_base)
    return _nearest_remote_ancestor(repo_root)


def changed_files_for_current_change(repo_root, environ=None):
    """Return committed, staged, and unstaged tracked paths from the fork point."""
    base_ref = resolve_comparison_ref(repo_root, environ=environ)
    try:
        merge_base = _git(
            repo_root, 'merge-base', base_ref, 'HEAD'
        ).stdout.strip()
        if not merge_base:
            raise ComparisonBaseUnavailable('comparison merge base is empty')
        output = _git(
            repo_root, 'diff', '--name-only', merge_base, '--'
        ).stdout
    except ComparisonBaseUnavailable:
        raise
    except Exception as exc:
        raise ComparisonBaseUnavailable(
            f'git diff against {base_ref} is unavailable'
        ) from exc
    return [
        line.strip().replace('\\', '/')
        for line in output.splitlines()
        if line.strip()
    ]
