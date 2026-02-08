import os
import sqlite3
import json
from app import app, init_db, get_db

# Clean up previous DB if exists to test fresh migration
db_path = "c:/Users/roshe/Desktop/attendX/attendance.db"
if os.path.exists(db_path):
    print("Removing existing DB for fresh test...")
    os.remove(db_path)

print("Initializing DB...")
try:
    with app.app_context():
        init_db()
        print("DB Initialized.")
        
        # Check users
        db = get_db()
        users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        print(f"Users in DB: {users_count}")
        
        # Verify specific user
        admin = db.execute("SELECT * FROM users WHERE sid='admin'").fetchone()
        if admin:
            print("Admin user found.")
        else:
            print("ERROR: Admin user not found.")
            
        # Verify dashboards routes
        client = app.test_client()
        
        # Test Login Redirect
        # Mock login session
        with client.session_transaction() as sess:
            sess['user'] = 'admin'
            sess['role'] = 'teacher'
            sess['name'] = 'Administrator'
            
        response = client.get('/teacher_dashboard')
        if response.status_code == 200 and b"Welcome, Administrator" in response.data:
            print("Teacher Dashboard: OK")
        else:
            print(f"Teacher Dashboard: FAILED {response.status_code}")
            
except Exception as e:
    print(f"Verification Failed: {e}")
