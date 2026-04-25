import os
from flask import Flask, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from db import db
from models import User, Location, GeoZone, Incident

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

    # ================= SECRET KEY =================
    app.config['SECRET_KEY'] = os.environ.get(
        'SECRET_KEY',
        'smartvoyager_fallback_key'
    )

    # ================= INIT DB =================
    db.init_app(app)

    with app.app_context():
        db.create_all()
        
        # Auto-migrate new AI fields safely
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE geozones ADD COLUMN place_type VARCHAR(50) DEFAULT 'general' NOT NULL;"))
            db.session.execute(text("ALTER TABLE geozones ADD COLUMN description VARCHAR(255);"))
            db.session.execute(text("ALTER TABLE geozones ADD COLUMN avg_response_time INTEGER DEFAULT 15 NOT NULL;"))
            db.session.execute(text("ALTER TABLE incidents ADD COLUMN auto_triggered BOOLEAN DEFAULT FALSE NOT NULL;"))
            db.session.commit()
            print("Successfully migrated new AI fields to the database.")
        except Exception as e:
            db.session.rollback()
            # If it fails, the columns likely already exist, which is fine
            pass

    # ================= REGISTER ROUTES =================
    from routes import auth_bp, user_bp, authority_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(authority_bp)

    # ================= HOME ROUTE =================
    @app.route('/')
    def index():
        return render_template('index.html')
        
    @app.route('/favicon.ico')
    def favicon():
        return '', 204

    @app.errorhandler(Exception)
    def handle_global_error(e):
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

    return app


# ================= FOR GUNICORN =================
app = create_app()

# ================= LOCAL RUN =================
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)