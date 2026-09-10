"""Print the authorized cron slot fulfilled by a GitHub schedule delivery."""

import argparse
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True)
    parser.add_argument('--event-schedule', required=True)
    parser.add_argument('--launched-at', required=True)
    args = parser.parse_args(argv)

    from services.github_schedule_slot import resolve_github_schedule_slot
    slot = resolve_github_schedule_slot(
        mode=args.mode,
        event_schedule=args.event_schedule,
        launched_at=args.launched_at,
    )
    print(slot.isoformat().replace('+00:00', 'Z'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
