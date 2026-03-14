from flask import Blueprint, jsonify

portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route('/', methods=['GET'])
def get_portfolio():
    """Return portfolio/about data."""
    return jsonify({
        'name': 'Nikko',
        'title': 'Baseball Developer & Data Engineer',
        'background': [
            'U.S. Army Veteran. 8 years of service. Discipline, systems thinking, and mission focus are in my DNA.',
            'Coca-Cola Consolidated Merchandiser. Real-world logistics, inventory, and data management.',
            'Self-taught developer with a focus on baseball analytics and full-stack web development.',
        ],
        'goal': 'Break into the baseball industry as a software developer or data engineer; building tools that help teams make better decisions.',
        'stack': ['React', 'TailwindCSS', 'Flask', 'Python', 'PostgreSQL'],
        'projects': [
            {
                'name': 'BaseballOS',
                'description': 'Full-stack baseball analytics platform. Bullpen fatigue scoring engine, prospect pipeline tracker, and portfolio layer.',
                'tech': ['React', 'Flask', 'PostgreSQL', 'MLB Stats API'],
                'status': 'Active',
            },
            {
                'name': 'MLB Bullpen Usage & Fatigue Tracker',
                'description': 'The predecessor to the Bullpen module in BaseballOS. Tracks relief pitcher usage and calculates fatigue risk.',
                'tech': ['React', 'TailwindCSS', 'Flask'],
                'status': 'Merged into BaseballOS',
            },
            {
                'name': 'Last Epoch Build & Analytics Tool',
                'description': 'Build theorycrafting and analytics tool for the ARPG Last Epoch. Mirrors the mindset I bring to baseball analytics; deep system knowledge, optimization, and data-driven decisions.',
                'tech': ['React', 'Python'],
                'status': 'In Progress',
            },
        ],
        'methodology': {
            'fatigue_engine': {
                'title': 'Bullpen Fatigue Scoring Engine',
                'summary': 'A weighted composite model that scores reliever fatigue from 0–100 using five inputs: pitch count load (30%), rest days (25%), appearance frequency (20%), leverage index (15%), and innings load (10%).',
                'components': [
                    {'name': 'Pitch Count Load', 'weight': '30%', 'rationale': 'Raw pitch count is the most direct indicator of arm stress in a rolling 7-day window.'},
                    {'name': 'Rest Days', 'weight': '25%', 'rationale': 'Days since last appearance — the primary recovery signal. Back-to-back use is physiologically different from 3 days of rest.'},
                    {'name': 'Appearance Frequency', 'weight': '20%', 'rationale': 'Cumulative fatigue builds even on low-pitch appearances. 5 appearances in 7 days is a red flag regardless of pitch counts.'},
                    {'name': 'Leverage Index', 'weight': '15%', 'rationale': 'High-leverage situations impose psychological and physiological stress beyond raw pitch counts.'},
                    {'name': 'Innings Load', 'weight': '10%', 'rationale': 'A floor for volume — ensures workload is captured even when pitch counts are unavailable.'},
                ],
                'risk_tiers': [
                    {'level': 'LOW', 'range': '0–25', 'interpretation': 'Fresh and available.'},
                    {'level': 'MODERATE', 'range': '26–50', 'interpretation': 'Some recent use. Monitor.'},
                    {'level': 'HIGH', 'range': '51–75', 'interpretation': 'Fatigued. Use with caution.'},
                    {'level': 'CRITICAL', 'range': '76–100', 'interpretation': 'Rest required.'},
                ],
            }
        },
        'contact': {
            'github': 'https://github.com/NickolisK24',
            'email': 'nickoliskacludis@gmail.com',
            'linkedin': 'https://www.linkedin.com/in/nickolis-kacludis/',
        }
    })
