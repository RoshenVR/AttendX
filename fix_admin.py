import sqlite3
import os

DATABASE = r"C:\Users\roshe\Desktop\attendX\attendance.db"

def fix_admin():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    print("Fixing admin user...")
    try:
        # Update existing 'admin' user to have correct role and password
        cursor.execute("""
            UPDATE users 
            SET role = 'admin', password = 'admin123', name = 'Administrator'
            WHERE sid = 'admin'
        """)
        
        if cursor.rowcount == 0:
            print("Admin user not found, creating it...")
            cursor.execute("INSERT INTO users (sid, name, password, role) VALUES (?, ?, ?, ?)",
                       ('admin', 'Administrator', 'admin123', 'admin'))
        else:
            print("Admin user updated successfully.")

        conn.commit()
        
        # Verify
        u = cursor.execute("SELECT * FROM users WHERE sid='admin'").fetchone()
        print(f"Verified Admin: SID={u[0]}, Pass={u[2]}, Role={u[3]}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_admin()
