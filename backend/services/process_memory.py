"""Process memory telemetry and allocator policy for production sync jobs.

The Daily Primary runs as a 512 MiB Render cron. Its publication phase writes
a multi-megabyte Dashboard payload (serialized twice inside the publication
transaction) and the database driver builds several transient full-size
buffers per write. glibc's default dynamic mmap threshold moves those buffers
onto the main heap after the first one is freed, where the freed space stays
resident and fragments, so each serialization stacked on the last
(daily-primary-memory-incident-2026-09-29).

``configure_allocator_for_large_buffers`` pins glibc's mmap threshold so
multi-megabyte allocations are mapped individually and returned to the OS on
free. It is a process-wide allocator policy only: no data, ordering or result
changes. It is a no-op off glibc, and ``BASEBALLOS_MALLOC_MMAP_THRESHOLD=off``
disables it.

``log_memory_checkpoint`` emits one concise line per phase boundary so a
natural production run can be compared with the local stress harness.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os

logger = logging.getLogger(__name__)

# glibc mallopt parameter number for M_MMAP_THRESHOLD (malloc.h).
_M_MMAP_THRESHOLD = -3
DEFAULT_MMAP_THRESHOLD_BYTES = 256 * 1024
MMAP_THRESHOLD_ENV = 'BASEBALLOS_MALLOC_MMAP_THRESHOLD'
_DISABLED_VALUES = frozenset({'0', 'off', 'false', 'no', 'disabled'})

_allocator_state = {'configured': False, 'threshold_bytes': None, 'reason': None}


def _status_kb(field):
    try:
        with open('/proc/self/status', encoding='ascii') as handle:
            for line in handle:
                if line.startswith(field + ':'):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def rss_mb():
    """Current resident set size in MiB, or None where /proc is unavailable."""
    value = _status_kb('VmRSS')
    return None if value is None else round(value / 1024, 1)


def peak_rss_mb():
    """Process high-water resident set size in MiB, or None if unknown."""
    value = _status_kb('VmHWM')
    if value is not None:
        return round(value / 1024, 1)
    try:
        import resource
        # ru_maxrss is KiB on Linux.
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except (ImportError, OSError, ValueError):
        return None


def _requested_threshold():
    raw = os.environ.get(MMAP_THRESHOLD_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_MMAP_THRESHOLD_BYTES, None
    value = raw.strip().lower()
    if value in _DISABLED_VALUES:
        return None, 'disabled_by_environment'
    try:
        threshold = int(value)
    except ValueError:
        return None, 'invalid_environment_value'
    if threshold <= 0:
        return None, 'disabled_by_environment'
    return threshold, None


def configure_allocator_for_large_buffers():
    """Pin glibc's mmap threshold once per process; never raises.

    Returns a small result dict describing what was applied.
    """
    if _allocator_state['configured']:
        return dict(_allocator_state)
    threshold, reason = _requested_threshold()
    applied = False
    if threshold is not None:
        try:
            libc_name = ctypes.util.find_library('c')
            libc = ctypes.CDLL(libc_name) if libc_name else None
            mallopt = getattr(libc, 'mallopt', None) if libc is not None else None
            if mallopt is None:
                reason = 'mallopt_unavailable'
            else:
                mallopt.argtypes = (ctypes.c_int, ctypes.c_int)
                mallopt.restype = ctypes.c_int
                applied = mallopt(_M_MMAP_THRESHOLD, int(threshold)) == 1
                reason = None if applied else 'mallopt_rejected'
        except (OSError, AttributeError, TypeError, ValueError):
            reason = 'mallopt_unavailable'
    _allocator_state.update(
        configured=True,
        threshold_bytes=threshold if applied else None,
        reason=reason,
    )
    logger.info(
        'process memory allocator policy mmap_threshold_bytes=%s applied=%s reason=%s',
        threshold if applied else None, applied, reason or 'none',
    )
    return dict(_allocator_state)


def log_memory_checkpoint(phase, *, job='daily_sync', **context):
    """Log one memory checkpoint line; never raises."""
    try:
        details = ''.join(
            f' {key}={value}' for key, value in context.items() if value is not None
        )
        logger.info(
            '%s memory checkpoint phase=%s rss_mb=%s peak_rss_mb=%s%s',
            job, phase, rss_mb(), peak_rss_mb(), details,
        )
    except Exception:  # noqa: BLE001 - telemetry must never affect the run
        pass
