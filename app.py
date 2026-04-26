import os
import logging
import traceback
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.exceptions import HTTPException
from jinja2.exceptions import TemplateNotFound
from db import db
from models import User, Location, GeoZone, Incident
from flask_migrate import Migrate

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    CORS(app)

    # ================= DATABASE CONFIG =================
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('DB_URI') or 'sqlite:///smartvoyager.db'

    # Fix for Render PostgreSQL URL
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # 2. DATABASE CONNECTION STABILITY
    if db_url.startswith('sqlite'):
        # SQLite does not support pool_size or max_overflow
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
        }
    else:
        # PostgreSQL / Production settings
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': 5,
            'max_overflow': 10
        }

    # ================= SECRET KEY =================
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'smartvoyager_fallback_key')

    # ================= INIT DB & MIGRATIONS =================
    db.init_app(app)
    
    # Initialize Flask-Migrate
    migrate = Migrate(app, db)

    with app.app_context():
        # Do not use db.create_all() or raw ALTER TABLE in production with Flask-Migrate
        # We rely on `flask db upgrade` to create/modify tables.
        pass

    # ================= REGISTER ROUTES =================
    from routes import auth_bp, user_bp, authority_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(authority_bp)

    # ================= HEALTH CHECK =================
    @app.route('/health')
    def health_check():
        return jsonify({"status": "healthy"}), 200

    # ================= HOME ROUTE =================
    @app.route('/')
    def index():
        try:
            return render_template('index.html')
        except TemplateNotFound:
            logger.warning("index.html template not found. Returning JSON fallback.")
            return jsonify({
                "status": "success",
                "data": {"message": "SmartVoyager API is running. UI template not found."}
            }), 200
        
    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    # ================= GLOBAL ERROR HANDLING =================
    @app.errorhandler(Exception)
    def handle_global_error(e):
        if isinstance(e, HTTPException):
            logger.warning(f"HTTP Exception {e.code}: {e.description}")
            return jsonify({
                "status": "error",
                "error": str(e.description)
            }), e.code
            
        logger.error(f"Unhandled Exception: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "error": "Internal Server Error. Please contact an administrator."
        }), 500

    return app

# ================= FOR GUNICORN =================
app = create_app()

# ================= LOCAL RUN =================
if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)