"""Identity / auth API (Phase D1B scaffolding).

Only GET /api/auth/me exists, and only its anonymous branch is live: there is no
sign-in, magic link, token issuance, or session yet (those arrive in D1C). The
endpoint is safe to ship now — it never requires authentication and never mutates
data — and it gives the frontend a stable identity contract to read.
"""

from flask import Blueprint, jsonify

from utils.identity import identity_for, resolve_current_user


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/me', methods=['GET'])
def get_me():
    """Return the current identity. Anonymous until D1C wires authentication."""
    return jsonify(identity_for(resolve_current_user()))
