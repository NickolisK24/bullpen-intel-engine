"""Prepare the current trusted Daily Edition artifact before web traffic starts."""

import json

from app import app
from services.intelligence_surface_snapshot import (
    ensure_snapshot_for_current_publication,
)


def main():
    with app.app_context():
        result = ensure_snapshot_for_current_publication()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
