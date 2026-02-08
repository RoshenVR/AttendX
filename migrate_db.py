import sqlite3
import os

DATABASE = 'attendance.db'
if not os.path.exists(DATABASE) and os.path.exists(os.path.join('..', DATABASE)):
    DATABASE = os.path.join('..', DATABASE)

def migrate():
    if not os.path.exists(DATABASE):
        print("Database not found, running app to init...")
        # App run will handle init, so we just return
        return

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Check for photo_path column
    try:
        cursor.execute("SELECT photo_path FROM users LIMIT 1")
    except sqlite3.OperationalError:
        print("Adding photo_path column...")
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN photo_path TEXT")
            conn.commit()
            print("Column added.")
        except Exception as e:
            print(f"Error adding column: {e}")

    # Check for admin
    cursor.execute("SELECT * FROM users WHERE role = 'admin'")
    if not cursor.fetchone():
        print("Creating default admin...")
        try:
            cursor.execute("INSERT INTO users (sid, name, password, role) VALUES (?, ?, ?, ?)",
                           ('admin', 'Administrator', 'admin123', 'admin'))
            conn.commit()
            print("Default Admin Created.")
        except Exception as e:
            print(f"Error creating admin: {e}")
    else:
        print("Admin account exists.")

    conn.close()

if __name__ == "__main__":
    migrate()
