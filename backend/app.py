from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate

from config import config
from utils.db import db

migrate = Migrate()

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://localhost:3000"]}})

    # Import models so Migrate picks them up
    from models.pitcher import Pitcher
    from models.game_log import GameLog
    from models.prospect import Prospect
    from models.fatigue_score import FatigueScore

    # Register blueprints
    from api.bullpen import bullpen_bp
    from api.prospects import prospects_bp
    from api.portfolio import portfolio_bp

    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(prospects_bp, url_prefix='/api/prospects')
    app.register_blueprint(portfolio_bp, url_prefix='/api/portfolio')

    @app.route('/api/health')
    def health():
        return {'status': 'ok', 'message': 'BaseballOS API is live'}

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
