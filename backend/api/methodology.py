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
                'BaseballOS combines four recent-workload inputs: pitch count '
                'load, rest days, appearance frequency, and innings load. '
                'Together, they help describe whether an arm\'s recent work '
                'has been light, building, heavy, or strongly pointing toward '
                'rest. Public pages show the resulting availability and '
                'workload context in baseball language, supported by '
                'recent-work evidence rather than a numeric grade.'
            ),
            'components': [
                {
                    'name':      'Pitch Count Load',
                    'weight':    '35%',
                    'rationale': (
                        'Recent pitch volume is the most direct workload '
                        'signal. Higher totals across the recent window add '
                        'more concern.'
                    ),
                },
                {
                    'name':      'Rest Days',
                    'weight':    '30%',
                    'rationale': (
                        'Time since the most recent appearance is the primary '
                        'recovery signal. Back-to-back use carries a different '
                        'workload context than several days of rest.'
                    ),
                },
                {
                    'name':      'Appearance Frequency',
                    'weight':    '20%',
                    'rationale': (
                        'Repeated use can narrow bullpen flexibility even when '
                        'individual outings are short.'
                    ),
                },
                {
                    'name':      'Innings Load',
                    'weight':    '15%',
                    'rationale': (
                        'Recent innings provide a second volume check when '
                        'pitch-count information is incomplete or noisy.'
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
