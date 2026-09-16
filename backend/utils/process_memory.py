"""Small, dependency-free process memory measurements for worker telemetry."""

from __future__ import annotations

import os
from pathlib import Path


def current_process_rss_mib() -> float | None:
    """Return the current Linux resident set in MiB when it is observable."""
    try:
        resident_pages = int(Path('/proc/self/statm').read_text(encoding='ascii').split()[1])
        page_size = os.sysconf('SC_PAGE_SIZE')
    except (IndexError, OSError, TypeError, ValueError):
        return None
    return round((resident_pages * page_size) / (1024 * 1024), 3)
