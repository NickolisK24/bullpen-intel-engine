from utils.db import db
from utils.time import utc_now_naive


class CompletedGameContext(db.Model):
    """Derived per-team context for one completed MLB game.

    BaseballOS stores *derived* completed-game context, never raw play-by-play.
    Each row captures one team's view of one game: the score the bullpen
    inherited, whether a lead was protected or lost, late damage, and a
    conservative story tag. The running-score fields are only populated when the
    extraction service actually had running-score data (linescore or
    play-by-play); with boxscore-only data they stay null and ``confidence``
    reads LOW so downstream consumers never mistake silence for fact.

    Identity is (team_id, game_pk): one team, one game. ``team_id`` follows the
    project-wide convention of a plain integer (there is no teams table).
    """

    __tablename__ = 'completed_game_contexts'

    __table_args__ = (
        db.UniqueConstraint(
            'team_id', 'game_pk', name='uq_completed_game_contexts_team_game'
        ),
        db.Index('ix_completed_game_contexts_team_date', 'team_id', 'game_date'),
        db.Index('ix_completed_game_contexts_game_pk', 'game_pk'),
    )

    id = db.Column(db.Integer, primary_key=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    team_id = db.Column(db.Integer, nullable=False)
    game_pk = db.Column(db.Integer, nullable=False)
    game_date = db.Column(db.Date, nullable=True)

    # ── Opponent / venue ──────────────────────────────────────────────────────
    opponent_team_id = db.Column(db.Integer, nullable=True)
    opponent_name = db.Column(db.String(100), nullable=True)
    home_away = db.Column(db.String(10), nullable=True)  # 'home' / 'away'

    # ── Final result (this team's perspective) ────────────────────────────────
    final_score_for = db.Column(db.Integer, nullable=True)
    final_score_against = db.Column(db.Integer, nullable=True)

    # ── Starter ───────────────────────────────────────────────────────────────
    starter_player_id = db.Column(db.Integer, nullable=True)
    starter_name = db.Column(db.String(100), nullable=True)
    starter_ip = db.Column(db.Float, nullable=True)
    starter_pitch_count = db.Column(db.Integer, nullable=True)
    starter_exit_inning = db.Column(db.Integer, nullable=True)
    starter_exit_score_for = db.Column(db.Integer, nullable=True)
    starter_exit_score_against = db.Column(db.Integer, nullable=True)

    # ── Bullpen handoff ───────────────────────────────────────────────────────
    bullpen_entry_inning = db.Column(db.Integer, nullable=True)
    bullpen_entry_score_for = db.Column(db.Integer, nullable=True)
    bullpen_entry_score_against = db.Column(db.Integer, nullable=True)
    lead_when_bullpen_entered = db.Column(db.Integer, nullable=True)
    deficit_when_bullpen_entered = db.Column(db.Integer, nullable=True)

    # ── Lead trajectory / late damage ─────────────────────────────────────────
    largest_lead = db.Column(db.Integer, nullable=True)
    largest_deficit = db.Column(db.Integer, nullable=True)
    late_runs_allowed = db.Column(db.Integer, nullable=True)
    runs_allowed_innings_7_to_9 = db.Column(db.Integer, nullable=True)

    # ── Outcome reads (tri-state: null = undetermined) ────────────────────────
    lead_protected = db.Column(db.Boolean, nullable=True)
    lead_lost = db.Column(db.Boolean, nullable=True)
    comeback_completed = db.Column(db.Boolean, nullable=True)
    turning_inning = db.Column(db.Integer, nullable=True)

    # ── Game shape ────────────────────────────────────────────────────────────
    game_shape_created = db.Column(db.String(40), nullable=True)  # game_shape vocab
    game_shape_protected = db.Column(db.Boolean, nullable=True)

    # ── Story selection ───────────────────────────────────────────────────────
    bullpen_story_tag = db.Column(db.String(40), nullable=True)
    confidence = db.Column(db.String(10), nullable=True)  # 'HIGH' / 'MEDIUM' / 'LOW'

    # ── Provenance ────────────────────────────────────────────────────────────
    generated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive
    )

    # Columns the extraction service is allowed to write. Identity columns
    # (team_id, game_pk) and the audit timestamps are managed separately.
    DERIVED_COLUMNS = (
        'game_date',
        'opponent_team_id',
        'opponent_name',
        'home_away',
        'final_score_for',
        'final_score_against',
        'starter_player_id',
        'starter_name',
        'starter_ip',
        'starter_pitch_count',
        'starter_exit_inning',
        'starter_exit_score_for',
        'starter_exit_score_against',
        'bullpen_entry_inning',
        'bullpen_entry_score_for',
        'bullpen_entry_score_against',
        'lead_when_bullpen_entered',
        'deficit_when_bullpen_entered',
        'largest_lead',
        'largest_deficit',
        'late_runs_allowed',
        'runs_allowed_innings_7_to_9',
        'lead_protected',
        'lead_lost',
        'comeback_completed',
        'turning_inning',
        'game_shape_created',
        'game_shape_protected',
        'bullpen_story_tag',
        'confidence',
        'generated_at',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'game_pk': self.game_pk,
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'opponent_team_id': self.opponent_team_id,
            'opponent_name': self.opponent_name,
            'home_away': self.home_away,
            'final_score_for': self.final_score_for,
            'final_score_against': self.final_score_against,
            'starter_player_id': self.starter_player_id,
            'starter_name': self.starter_name,
            'starter_ip': self.starter_ip,
            'starter_pitch_count': self.starter_pitch_count,
            'starter_exit_inning': self.starter_exit_inning,
            'starter_exit_score_for': self.starter_exit_score_for,
            'starter_exit_score_against': self.starter_exit_score_against,
            'bullpen_entry_inning': self.bullpen_entry_inning,
            'bullpen_entry_score_for': self.bullpen_entry_score_for,
            'bullpen_entry_score_against': self.bullpen_entry_score_against,
            'lead_when_bullpen_entered': self.lead_when_bullpen_entered,
            'deficit_when_bullpen_entered': self.deficit_when_bullpen_entered,
            'largest_lead': self.largest_lead,
            'largest_deficit': self.largest_deficit,
            'late_runs_allowed': self.late_runs_allowed,
            'runs_allowed_innings_7_to_9': self.runs_allowed_innings_7_to_9,
            'lead_protected': self.lead_protected,
            'lead_lost': self.lead_lost,
            'comeback_completed': self.comeback_completed,
            'turning_inning': self.turning_inning,
            'game_shape_created': self.game_shape_created,
            'game_shape_protected': self.game_shape_protected,
            'bullpen_story_tag': self.bullpen_story_tag,
            'confidence': self.confidence,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
        }

    def __repr__(self):
        return (
            f'<CompletedGameContext team_id={self.team_id} game_pk={self.game_pk} '
            f'tag={self.bullpen_story_tag} confidence={self.confidence}>'
        )
