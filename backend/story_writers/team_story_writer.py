"""Team Story Writer (COIN Phase 4).

Produces one full team story from a NarrativeFeed: a headline plus a short
paragraph that leads with the game narrative and, when the feed carries a
bullpen-state read, follows with a present-tense status sentence. Translation
only — every decision was made upstream.
"""

from __future__ import annotations

from story_writers.base_story_writer import BaseStoryWriter


class TeamStoryWriter(BaseStoryWriter):
    writer_name = 'team_story'

    def write(self):
        if self.is_low_confidence():
            return self._draft(self.headline_text(), self.lead_sentence())

        sentences = [self.compose_body()]
        # A present-tense bullpen-state read reads as a closing consequence; only
        # the higher-priority stories carry it, keeping MEDIUM stories tight.
        if self.wants_observations():
            state = self.bullpen_state_clause()
            if state is not None:
                sentences.append(state[:1].upper() + state[1:] + '.')
        observations = self.observation_lines() if self.wants_observations() else []
        evidence = self.evidence_lines() if self.wants_evidence() else []
        return self._draft(
            self.headline_text(),
            ' '.join(sentences),
            observations=observations,
            evidence=evidence,
        )
