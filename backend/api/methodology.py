from flask import Blueprint, jsonify

methodology_bp = Blueprint('methodology', __name__)


@methodology_bp.route('/', methods=['GET'])
def get_methodology():
    """
    Returns the documented methodology behind BaseballOS — the fatigue
    scoring engine, the analytical insights surfaced from the dataset, and
    the data sources we trust. This is the substantive companion to the
    bullpen and pipeline modules: anyone evaluating the tool should be able
    to read this page and understand exactly how every number on the
    dashboard was computed.
    """
    return jsonify({
        'fatigue_engine': {
            'title':   'Bullpen Fatigue Scoring Engine',
            'summary': (
                'A weighted composite model that scores reliever fatigue '
                'from 0 to 100 using four inputs derived from MLB Stats API '
                'game logs: pitch count load (35%), rest days (30%), '
                'appearance frequency (20%), and innings load (15%). '
                'Each component returns a 0-100 sub-score; the final score '
                'is the weighted sum, clamped to the [0, 100] range.'
            ),
            'components': [
                {
                    'name':      'Pitch Count Load',
                    'weight':    '35%',
                    'rationale': (
                        'Raw pitch count is the most direct indicator of '
                        'arm stress in a rolling 7-day window. Sub-score '
                        'scales linearly across thresholds at 50, 90, and '
                        '120 pitches.'
                    ),
                },
                {
                    'name':      'Rest Days',
                    'weight':    '30%',
                    'rationale': (
                        'Days since last appearance — the primary recovery '
                        'signal. Back-to-back use is physiologically '
                        'different from three days of rest. Discrete '
                        'mapping: 0d=100, 1d=80, 2d=55, 3d=30, 4d=10, 5+d=0.'
                    ),
                },
                {
                    'name':      'Appearance Frequency',
                    'weight':    '20%',
                    'rationale': (
                        'Cumulative fatigue builds even on low-pitch '
                        'appearances. Five appearances in seven days is a '
                        'red flag regardless of pitch counts. Blends '
                        '7-day and 14-day windows (70/15 weighted).'
                    ),
                },
                {
                    'name':      'Innings Load',
                    'weight':    '15%',
                    'rationale': (
                        'A volume floor — ensures workload is captured '
                        'even when pitch counts are noisy. Scales linearly '
                        'across 4 IP and 6 IP thresholds in a 7-day window.'
                    ),
                },
            ],
            'risk_tiers': [
                {'level': 'LOW',      'range': '0–24',   'interpretation': 'Fresh and available.'},
                {'level': 'MODERATE', 'range': '25–49',  'interpretation': 'Some recent use. Monitor.'},
                {'level': 'HIGH',     'range': '50–80',  'interpretation': 'Fatigued. Use with caution.'},
                {'level': 'CRITICAL', 'range': '81–100', 'interpretation': 'Rest required.'},
            ],
            'excluded': {
                'name':      'Leverage Index',
                'reason': (
                    'An earlier version of this model included Leverage '
                    'Index as a fifth component (15% weight). The MLB '
                    'Stats API gameLog endpoint does not expose LI — it is '
                    'a Fangraphs / Baseball Savant computed stat derived '
                    'from play-by-play data we do not currently ingest. '
                    'Rather than fake the data with a constant default, '
                    'we removed the component and redistributed its weight '
                    'across the four factors we measure reliably. The '
                    'leverage_score column on the FatigueScore model is '
                    'preserved for schema stability but is no longer used '
                    'in the composite calculation.'
                ),
            },
        },

        'insights': {
            'title':   'Fatigue Costs Runs',
            'summary': (
                'A retrospective analysis across the 2024 and 2025 MLB '
                'seasons measuring whether elevated fatigue scores predict '
                'worse next-appearance ERA. We walked every game log '
                'chronologically per pitcher, reconstructed the fatigue '
                'score they carried into each appearance, and aggregated '
                'their next-outing IP and ER by risk tier.'
            ),
            'finding': (
                'Pitchers throwing at HIGH or CRITICAL fatigue posted a '
                '3.96 ERA in their next outing — roughly 10 percent worse '
                'than the 3.59 ERA they posted when rested (MODERATE '
                'tier). The result holds across more than 30,000 '
                'appearances and ~14,000 in each bucket, so the gap is '
                'not driven by sample noise.'
            ),
            'caveat': (
                'LOW-tier appearances are structurally rare in this '
                'analysis: a pitcher with five-plus days of rest by '
                'definition has not pitched recently enough to have a '
                'next-appearance pair. We use MODERATE as the rested '
                'baseline rather than LOW.'
            ),
        },

        'data_sources': [
            {
                'name': 'MLB Stats API',
                'url':  'https://github.com/toddrob99/MLB-StatsAPI/wiki/Endpoints',
                'use':  'Primary source for rosters, game logs, and box scores. Free, unauthenticated, and well-documented via the linked community wiki.',
            },
        ],

        'stack': ['Flask', 'SQLAlchemy', 'PostgreSQL (Supabase)', 'React', 'Vite', 'TailwindCSS', 'Recharts'],
    })