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

        sentences = [self.compose_body()]

        # Prefer named rested arms from evidence; fall back to the count.
        names = self.available_reliever_names()
        if names:
            sentences.append(f"Available arms: {', '.join(names)}.")
        else:
            available = self.availability_snapshot().get('available_arms_count')
            if isinstance(available, int):
                sentences.append(f'Available arms: {available}.')

        watch = self.watch_sentence()
        if watch:
            sentences.append(watch)

        observations = self.observation_lines() if self.wants_observations() else []
        evidence = self.evidence_lines() if self.wants_evidence() else []
        return self._draft(
            headline,
            ' '.join(sentences),
            observations=observations,
            evidence=evidence,
        )
