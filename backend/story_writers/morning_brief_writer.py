"""Morning Brief Writer (COIN).

The morning brief answers a different question than the team story: "what does
yesterday mean for today's bullpen?" It leads with a one-sentence recap of the
game (not the full narrative), then turns to the bullpen itself — the available
arms (named whenever the package provides names, otherwise a count) and where the
relief corps now stands. It does not repeat the team story's observation list.
All of it is present-tense and time-free; nothing implies a schedule the package
has not confirmed. Translation only.
"""

from __future__ import annotations

from story_writers.base_story_writer import BaseStoryWriter


class MorningBriefWriter(BaseStoryWriter):
    writer_name = 'morning_brief'

    def write(self):
        headline = f'Bullpen note: {self.headline_text()}'
        if self.is_low_confidence():
            return self._draft(headline, self.lead_sentence())

        # One-sentence recap, then the bullpen-for-today picture.
        sentences = [self.brief_recap()]

        names = self.available_reliever_names()
        if names:
            sentences.append(f"Available arms: {', '.join(names)}.")
        else:
            available = self.availability_snapshot().get('available_arms_count')
            if isinstance(available, int) and available > 0:
                sentences.append(f'Available arms: {available}.')

        today = self.brief_today_line()
        if today is not None:
            sentences.append(today)

        # The brief proves its read with evidence but leaves the "why" list to the
        # team story, so the two surfaces stay distinct.
        evidence = self.evidence_lines() if self.wants_evidence() else []
        return self._draft(headline, ' '.join(sentences), observations=[], evidence=evidence)
