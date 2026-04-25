from app import app
from db import db
from sqlalchemy import text

def migrate():
    """
    ONE-TIME MIGRATION SCRIPT.
    Run this script once to add the new AI fields (place_type, description, avg_response_time) 
    to GeoZones and the 'auto_triggered' field to Incidents using raw SQL.
    Do not use complex Alembic migrations for this student project.
    """
    with app.app_context():
        print("Starting one-time database migration...")
        
        # Alter geozones
        try:
            db.session.execute(text("ALTER TABLE geozones ADD COLUMN place_type VARCHAR(50) DEFAULT 'general' NOT NULL;"))
            print("Added place_type to geozones")
        except Exception as e:
            print("place_type may already exist or error:", str(e))
            
        try:
            db.session.execute(text("ALTER TABLE geozones ADD COLUMN description VARCHAR(255);"))
            print("Added description to geozones")
        except Exception as e:
            print("description may already exist or error:", str(e))
            
        try:
            db.session.execute(text("ALTER TABLE geozones ADD COLUMN avg_response_time INTEGER DEFAULT 15 NOT NULL;"))
            print("Added avg_response_time to geozones")
        except Exception as e:
            print("avg_response_time may already exist or error:", str(e))
            
        # Alter incidents
        try:
            db.session.execute(text("ALTER TABLE incidents ADD COLUMN auto_triggered BOOLEAN DEFAULT FALSE NOT NULL;"))
            print("Added auto_triggered to incidents")
        except Exception as e:
            print("auto_triggered may already exist or error:", str(e))
            
        db.session.commit()
        print("Migration finished.")

if __name__ == '__main__':
    migrate()
