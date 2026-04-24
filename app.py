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
    
    # Configuration for MySQL
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DB_URI', 'mysql+pymysql://root:harshu123@localhost/smartvoyager')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'smartvoyager_fallback_key')
    
    db.init_app(app)
    
    with app.app_context():
        # Clean architecture dictates standard ORM recreations rather than runtime ALTER queries.
        # Ensure to drop/recreate tables if schema changes.
        db.create_all()

    # Register Blueprints
    from routes import auth_bp, user_bp, authority_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(authority_bp)

    # UI Route
    @app.route('/')
    def index():
        return render_template('index.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
