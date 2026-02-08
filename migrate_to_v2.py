"""
Migration script to update database schema to v2
- Adds subjects table
- Adds foreign keys to attendance_sessions and attendance_records
- Adds unique constraint for duplicate prevention
"""

import sqlite3
import os

DATABASE = 'attendance.db'

def migrate():
    if not os.path.exists(DATABASE):
        print("Database not found. Please run the app first to create it.")
        return
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        # Check if subjects table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subjects'")
        if cursor.fetchone():
            print("✓ subjects table already exists")
        else:
            print("Creating subjects table...")
            cursor.execute("""
                CREATE TABLE subjects (
                    subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_name TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    added_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(added_by) REFERENCES users(sid)
                )
            """)
            print("✓ subjects table created")
        
        # Check if attendance_sessions has new columns
        cursor.execute("PRAGMA table_info(attendance_sessions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'teacher_id' not in columns or 'subject_id' not in columns:
            print("Migrating attendance_sessions table...")
            # SQLite doesn't support ALTER TABLE ADD COLUMN with FK directly
            # Need to recreate table
            
            # Backup existing data
            cursor.execute("SELECT * FROM attendance_sessions")
            sessions_data = cursor.fetchall()
            
            # Drop old table
            cursor.execute("DROP TABLE attendance_sessions")
            
            # Create new table
            cursor.execute("""
                CREATE TABLE attendance_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_id TEXT,
                    subject_id INTEGER,
                    subject TEXT NOT NULL,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    active BOOLEAN DEFAULT 1,
                    FOREIGN KEY(teacher_id) REFERENCES users(sid),
                    FOREIGN KEY(subject_id) REFERENCES subjects(subject_id)
                )
            """)
            
            # Restore data (without teacher_id and subject_id, they'll be NULL)
            for row in sessions_data:
                cursor.execute("""
                    INSERT INTO attendance_sessions (session_id, subject, start_time, end_time, active)
                    VALUES (?, ?, ?, ?, ?)
                """, (row[0], row[1], row[2], row[3], row[4]))
            
            print("✓ attendance_sessions table migrated")
        else:
            print("✓ attendance_sessions table already up to date")
        
        # Check if attendance_records has new columns and constraint
        cursor.execute("PRAGMA table_info(attendance_records)")
        columns = [col[1] for col in cursor.fetchall()]
        
        needs_migration = 'subject_id' not in columns
        
        if needs_migration:
            print("Migrating attendance_records table...")
            
            # Backup existing data
            cursor.execute("SELECT * FROM attendance_records")
            records_data = cursor.fetchall()
            
            # Drop old table
            cursor.execute("DROP TABLE attendance_records")
            
            # Create new table with UNIQUE constraint
            cursor.execute("""
                CREATE TABLE attendance_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    sid TEXT NOT NULL,
                    name TEXT NOT NULL,
                    subject_id INTEGER,
                    subject TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES attendance_sessions(session_id),
                    FOREIGN KEY(sid) REFERENCES users(sid),
                    FOREIGN KEY(subject_id) REFERENCES subjects(subject_id),
                    UNIQUE(session_id, sid)
                )
            """)
            
            # Restore data, removing duplicates
            restored = 0
            duplicates = 0
            seen = set()
            
            for row in records_data:
                # row: record_id, session_id, sid, name, subject, date, time
                key = (row[1], row[2])  # (session_id, sid)
                if key not in seen:
                    cursor.execute("""
                        INSERT INTO attendance_records (session_id, sid, name, subject, date, time)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (row[1], row[2], row[3], row[4], row[5], row[6]))
                    seen.add(key)
                    restored += 1
                else:
                    duplicates += 1
            
            print(f"✓ attendance_records table migrated")
            print(f"  - Restored {restored} records")
            if duplicates > 0:
                print(f"  - Removed {duplicates} duplicate records")
        else:
            print("✓ attendance_records table already up to date")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting database migration to v2...")
    print("=" * 50)
    migrate()
