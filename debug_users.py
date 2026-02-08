import sqlite3
import os

DATABASE = 'attendance.db'
if not os.path.exists(DATABASE) and os.path.exists(os.path.join('..', DATABASE)):
    DATABASE = os.path.join('..', DATABASE)

def check_users():
    if not os.path.exists(DATABASE):
        print("Database not found!")
        return

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    print("--- Users in DB ---")
    try:
        users = cursor.execute("SELECT sid, name, password, role FROM users").fetchall()
        for u in users:
            print(f"User: {u[0]} | Name: {u[1]} | Pass: {u[2]} | Role: {u[3]}")
    except Exception as e:
        print(f"Error: {e}")

    conn.close()

if __name__ == "__main__":
    check_users()
