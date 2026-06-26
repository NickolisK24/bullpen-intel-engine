"""Dashboard Story Writer (COIN Phase 4).

Produces concise dashboard copy from a NarrativeFeed: a headline plus a single
terse clause. No paragraph, no snapshot prose — the compact surface gets only
the one-line read. Translation only.
"""

from __future__ import annotations

from story_writers.base_story_writer import BaseStoryWriter


class DashboardStoryWriter(BaseStoryWriter):
    writer_name = 'dashboard'

    def write(self):
        if self.is_low_confidence():
            return self._draft(self.headline_text(), 'No completed-game read yet.')
        summary = self.short_summary()
        body = summary[:1].upper() + summary[1:] + '.'
        return self._draft(self.headline_text(), body)
