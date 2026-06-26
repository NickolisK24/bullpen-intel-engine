"""Morning Brief Writer (COIN Phase 4).

Produces daily brief text from a NarrativeFeed: a labeled headline, the game
narrative sentence, and a data-forward availability line drawn straight from the
feed's availability snapshot. The available-arms count is a present-tense read
with no temporal claim, so it never implies a schedule the feed has not
confirmed. Translation only.
"""

from __future__ import annotations

from story_writers.base_story_writer import BaseStoryWriter


class MorningBriefWriter(BaseStoryWriter):
    writer_name = 'morning_brief'

    def write(self):
        headline = f'Bullpen note: {self.headline_text()}'
        if self.is_low_confidence():
            return self._draft(headline, self.lead_sentence())

        sentences = [self.lead_sentence()]
        available = self.availability_snapshot().get('available_arms_count')
        if isinstance(available, int):
            sentences.append(f'Available arms: {available}.')
        return self._draft(headline, ' '.join(sentences))
