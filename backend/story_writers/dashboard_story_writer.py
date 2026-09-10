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
        # Lead with the club so the one-liner never reads generically.
        team = self._team_subject()
        body = f'{team[:1].upper() + team[1:]} {self.short_summary()}.'
        # Stay concise: at most one evidence-backed detail, no observation list.
        evidence = self.evidence_lines()[:1]
        return self._draft(self.headline_text(), body, evidence=evidence)
