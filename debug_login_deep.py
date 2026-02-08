import sqlite3
import os

DATABASE = r"C:\Users\roshe\Desktop\attendX\attendance.db"

def inspect_admin():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print(f"Checking Database: {DATABASE}")
    
    # Fetch admin
    user = cursor.execute("SELECT * FROM users WHERE sid = 'admin'").fetchone()
    
    if user:
        print("\n--- Admin User Dump ---")
        print(f"SID (raw): {repr(user['sid'])}")
        print(f"Pass (raw): {repr(user['password'])}")
        print(f"Role (raw): {repr(user['role'])}")
        
        # Simulation
        input_user = "admin"
        input_pass = "admin123"
        input_role = "admin"
        
        print("\n--- Simulation ---")
        print(f"Input User: {repr(input_user)}")
        print(f"Input Pass: {repr(input_pass)}")
        
        if user['sid'] == input_user:
            print("Username Match: YES")
        else:
            print("Username Match: NO")
            
        if user['password'] == input_pass:
            print("Password Match: YES")
        else:
            print("Password Match: NO")
            
        if user['role'] == input_role:
            print("Role Match: YES")
        else:
            print("Role Match: NO")
            
    else:
        print("Admin user not found in DB!")

    conn.close()

if __name__ == "__main__":
    inspect_admin()
