from flask import Blueprint, jsonify, request
from models.prospect import Prospect
from utils.db import db

prospects_bp = Blueprint('prospects', __name__)

LEVELS_ORDER = ['ROK', 'A', 'A+', 'AA', 'AAA', 'MLB']


@prospects_bp.route('/', methods=['GET'])
def get_prospects():
    """
    Get prospects with optional filters.
    Params: team_id, level, position, min_grade, limit
    """
    team_id = request.args.get('team_id', type=int)
    level = request.args.get('level')
    position = request.args.get('position')
    min_grade = request.args.get('min_grade', type=int)
    limit = request.args.get('limit', 100, type=int)

    query = Prospect.query.filter_by(active=True)

    if team_id:
        query = query.filter_by(team_id=team_id)
    if level:
        query = query.filter_by(current_level=level.upper())
    if position:
        query = query.filter_by(position=position.upper())
    if min_grade:
        query = query.filter(Prospect.overall_grade >= min_grade)

    prospects = query.order_by(
        Prospect.overall_grade.desc().nullslast(),
        Prospect.full_name
    ).limit(limit).all()

    return jsonify([p.to_dict() for p in prospects])


@prospects_bp.route('/<int:prospect_id>', methods=['GET'])
def get_prospect(prospect_id):
    """Get a single prospect with full detail."""
    prospect = Prospect.query.get_or_404(prospect_id)
    return jsonify(prospect.to_dict())


@prospects_bp.route('/by-team', methods=['GET'])
def get_by_team():
    """Group prospects by team."""
    prospects = Prospect.query.filter_by(active=True).all()
    by_team = {}
    for p in prospects:
        key = p.team_abbreviation or 'UNK'
        if key not in by_team:
            by_team[key] = {'team_name': p.team_name, 'team_abbreviation': key, 'prospects': []}
        by_team[key]['prospects'].append(p.to_dict())

    # Sort prospects within each team by overall grade
    for team in by_team.values():
        team['prospects'].sort(key=lambda x: x['grades']['overall'] or 0, reverse=True)

    return jsonify(list(by_team.values()))


@prospects_bp.route('/pipeline', methods=['GET'])
def get_pipeline():
    """
    Return a development pipeline view:
    Prospects grouped by level, sorted by grade within each level.
    """
    prospects = Prospect.query.filter_by(active=True).all()

    pipeline = {level: [] for level in LEVELS_ORDER}
    for p in prospects:
        level = p.current_level
        if level in pipeline:
            pipeline[level].append(p.to_dict())

    for level in pipeline:
        pipeline[level].sort(key=lambda x: x['grades']['overall'] or 0, reverse=True)

    return jsonify({
        'levels': LEVELS_ORDER,
        'pipeline': pipeline,
        'total': len(prospects),
    })


@prospects_bp.route('/compare', methods=['GET'])
def compare_prospects():
    """
    Compare two prospects side by side.
    Params: id1, id2
    """
    id1 = request.args.get('id1', type=int)
    id2 = request.args.get('id2', type=int)

    if not id1 or not id2:
        return jsonify({'error': 'id1 and id2 are required'}), 400

    p1 = Prospect.query.get_or_404(id1)
    p2 = Prospect.query.get_or_404(id2)

    return jsonify({'prospect_1': p1.to_dict(), 'prospect_2': p2.to_dict()})


@prospects_bp.route('/stats/overview', methods=['GET'])
def pipeline_overview():
    """Overview stats for the pipeline dashboard."""
    total = Prospect.query.filter_by(active=True).count()

    by_level = (
        db.session.query(Prospect.current_level, db.func.count(Prospect.id))
        .filter_by(active=True)
        .group_by(Prospect.current_level)
        .all()
    )

    top_10 = (
        Prospect.query.filter_by(active=True)
        .order_by(Prospect.overall_grade.desc().nullslast())
        .limit(10)
        .all()
    )

    return jsonify({
        'total': total,
        'by_level': {level: count for level, count in by_level},
        'top_10': [p.to_dict() for p in top_10],
    })
