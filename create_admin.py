import sys
from app import app
from db import db
from models import User

def create_admin(name, email, password):
    with app.app_context():
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"User with email {email} already exists. Updating role to admin...")
            existing_user.role = 'admin'
            existing_user.set_password(password)
            db.session.commit()
            print("Successfully updated user to admin.")
            return

        new_admin = User(name=name, email=email, role='admin')
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        print(f"Successfully created admin user: {email}")

if __name__ == '__main__':
    print("--- Create Admin User ---")
    name = input("Enter admin name: ")
    email = input("Enter admin email: ")
    password = input("Enter admin password: ")
    
    if name and email and password:
        create_admin(name, email, password)
    else:
        print("All fields are required.")
