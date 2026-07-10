from flask import Blueprint, jsonify

from services.availability_backtest import latest_backtest_payload

methodology_bp = Blueprint('methodology', __name__)


@methodology_bp.route('/availability-backtest', methods=['GET'])
def get_availability_backtest():
    return jsonify(latest_backtest_payload())


@methodology_bp.route('/', methods=['GET'])
def get_methodology():
    """
    Returns the documented methodology behind BaseballOS: the public workload
    read, the data sources we trust, and the limits around what the read does
    and does not claim.
    """
    return jsonify({
        'fatigue_engine': {
            'title':   'Bullpen Recent Workload Read',
            'summary': (
                'BaseballOS combines four recent-workload inputs derived from '
                'MLB Stats API game logs: pitch count load (35%), rest days '
                '(30%), appearance frequency (20%), and innings load (15%). '
                'These inputs help describe whether recent usage is light, '
                'building, heavy, or strongly pointing toward rest. Public '
                'pages show baseball-language availability and workload '
                'context rather than a numeric grade.'
            ),
            'components': [
                {
                    'name':      'Pitch Count Load',
                    'weight':    '35%',
                    'rationale': (
                        'Pitch totals are the most direct indicator of recent '
                        'arm volume in the workload window. More pitches in '
                        'close succession point to heavier recent work.'
                    ),
                },
                {
                    'name':      'Rest Days',
                    'weight':    '30%',
                    'rationale': (
                        'Days since last appearance are the primary recovery '
                        'signal. Back-to-back use creates a different bullpen '
                        'read than several days between outings.'
                    ),
                },
                {
                    'name':      'Appearance Frequency',
                    'weight':    '20%',
                    'rationale': (
                        'Repeated use can narrow bullpen choices even on low-pitch '
                        'appearances. Recent and trailing appearance patterns '
                        'keep one-batter outings and multi-day usage visible.'
                    ),
                },
                {
                    'name':      'Innings Load',
                    'weight':    '15%',
                    'rationale': (
                        'Innings pitched provide a workload floor when pitch '
                        'counts are noisy. Longer recent outings add context '
                        'beyond the raw number of appearances.'
                    ),
                },
            ],
            'interpretation': [
                'More rest and lighter recent work generally support availability.',
                'Repeated appearances, elevated pitch counts, and limited recovery increase workload concern.',
                'The final public read is explained with recent-work evidence rather than a numeric grade.',
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
                    'historical leverage field is preserved for compatibility '
                    'but is no longer used '
                    'in the workload calculation.'
                ),
            },
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
