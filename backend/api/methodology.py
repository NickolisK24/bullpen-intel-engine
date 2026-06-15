from flask import Blueprint, jsonify

from services.availability_backtest import latest_backtest_payload

methodology_bp = Blueprint('methodology', __name__)


@methodology_bp.route('/availability-backtest', methods=['GET'])
def get_availability_backtest():
    return jsonify(latest_backtest_payload())


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
            'title':   'Fatigue Score vs. Next-Outing ERA (Exploratory, Secondary)',
            'summary': (
                'A retrospective, exploratory look across the 2024 and 2025 '
                'MLB seasons at whether a higher fatigue score going into an '
                'appearance is associated with a worse next-appearance ERA. '
                'We walked every game log chronologically per pitcher, '
                'reconstructed the fatigue score they carried into each '
                'appearance, and aggregated their next-outing IP and ER by '
                'risk tier. This is a simple association — not a controlled '
                'or causal study.'
            ),
            'finding': (
                'Appearances made at HIGH or CRITICAL fatigue were followed '
                'by a 3.96 next-outing ERA, versus 3.59 after MODERATE-tier '
                '(rested-baseline) appearances — about a 10% difference. '
                'This is an observed association across the seasons studied, '
                'not evidence that fatigue causes runs: the comparison is '
                'not adjusted for the factors listed below, and higher-'
                'fatigue outings skew toward higher-workload (starter-style) '
                'appearances.'
            ),
            'caveat': (
                'LOW-tier appearances are structurally rare here: a pitcher '
                'with five-plus days of rest has, by definition, not pitched '
                'recently enough to form a next-appearance pair, so MODERATE '
                'is used as the rested baseline. CRITICAL is also very sparse '
                '(see sample sizes). Treat the result as a preliminary, '
                'directional finding worth deeper study, not a settled '
                'conclusion.'
            ),
            # n per tier mirrors the current generated artifact
            # (analysis/fatigue_era_results.json). Regenerating the analysis
            # would update these counts.
            'samples': {'LOW': 0, 'MODERATE': 16385, 'HIGH': 14495, 'CRITICAL': 6},
            'measured': [
                'Fatigue-score tier carried into an appearance',
                'Next-appearance ERA (earned runs × 9 / innings pitched)',
                'Number of appearances in each tier (sample size)',
            ],
            'not_measured': [
                'Pitcher role (starters vs. relievers are not separated)',
                'Opponent quality',
                'Park factors',
                'Game state / score',
                'Leverage',
                'Defense behind the pitcher',
            ],
        },

        'role_authority': {
            'title': 'Bullpen Role Authority (Starter / Reliever / Ambiguous / Unknown)',
            'summary': (
                'Whether a pitcher appears on bullpen surfaces is decided from '
                'the authoritative MLB gamesStarted signal — did the pitcher '
                'start the games he appeared in — not from innings-pitched '
                'guessing. Role is deterministic and explainable: starters are '
                'excluded, relievers are included, swing/opener profiles are '
                'shown as Ambiguous with a caveat, and pitchers without enough '
                'start evidence are Unknown and withheld rather than guessed.'
            ),
            'categories': {
                'Starter': 'Starts the games he appears in; excluded from bullpen counts.',
                'Reliever': 'Appears out of the bullpen; included.',
                'Ambiguous': 'Conflicting evidence (swingman/opener); included with a caveat.',
                'Unknown': 'Evidence absent; withheld from default counts (not assumed a reliever).',
            },
            'signals': {
                'primary': 'gamesStarted pattern over recent appearances',
                'secondary': 'save / hold relief confirmation',
                'supporting': 'innings length, used only as an opener tie-breaker — never as the primary signal',
            },
            'note': (
                'Role is separate from roster status (active/IL) and from '
                'workload availability. Confidence (high/medium/low/none) is '
                'shown alongside the role.'
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
